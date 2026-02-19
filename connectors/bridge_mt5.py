"""
Bridge para MetaTrader 5
Conecta estrategias de MT5 con Aethelgard via WebSocket
Ahora incluye capacidad de ejecutar señales automáticamente en cuenta Demo
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
import websockets
from websockets.exceptions import ConnectionClosed

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 no está instalado. Instala con: pip install MetaTrader5")
    mt5 = None

logging.basicConfig(level=logging.INFO)
logger: logging.Logger = logging.getLogger(__name__)


class MT5Bridge:
    """Bridge para conectar MetaTrader 5 con Aethelgard y ejecutar señales automáticamente"""
    
    def __init__(self, 
                 server_url: str = "ws://localhost:8000/ws/MT5/",
                 client_id: Optional[str] = None,
                 symbol: str = "EURUSD",
                 auto_execute: bool = True,
                 demo_mode: bool = True,
                 default_volume: float = 0.01,
                 magic_number: int = 234000) -> None:
        """
        Args:
            server_url: URL del servidor Aethelgard
            client_id: ID único del cliente (por defecto usa nombre de máquina)
            symbol: Símbolo a monitorear
            auto_execute: Si True, ejecuta señales automáticamente
            demo_mode: Si True, verifica que estemos en cuenta demo antes de ejecutar
            default_volume: Volumen por defecto para operaciones
            magic_number: Número mágico para identificar operaciones de Aethelgard
        """
        self.server_url: str = server_url
        self.client_id: str = client_id or f"MT5_{symbol}"
        self.symbol: str = symbol
        self.websocket: Optional[websockets.ClientConnection] = None
        self.is_connected = False
        self.running = False
        self.auto_execute: bool = auto_execute
        self.demo_mode: bool = demo_mode
        self.default_volume: float = default_volume
        self.magic_number: int = magic_number
        
        # Tracking de operaciones
        self.active_positions: Dict[int, Dict] = {}  # ticket -> position_info
        self.signal_results: List[Dict] = []  # Historial de resultados
        
        # Inicializar MT5
        if mt5 is None:
            raise ImportError("MetaTrader5 no está disponible")
        
        if not mt5.initialize():  # type: ignore
            raise RuntimeError(f"Error inicializando MT5: {mt5.last_error()}")  # type: ignore
        
        # Verificar modo demo
        account_info = mt5.account_info()  # type: ignore
        if account_info is None:
            raise RuntimeError("No se pudo obtener información de la cuenta")
        
        is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO  # type: ignore
        
        if self.demo_mode and not is_demo:
            logger.warning("⚠️  ADVERTENCIA: demo_mode=True pero conectado a cuenta REAL")
            logger.warning("⚠️  Auto-ejecución deshabilitada por seguridad")
            self.auto_execute = False
        
        logger.info(f"MT5 inicializado. Versión: {mt5.version()}")  # type: ignore
        logger.info(f"Cuenta: {account_info.login} | Demo: {is_demo} | Auto-Execute: {self.auto_execute}")
    
    async def connect(self) -> None:
        """Conecta al servidor Aethelgard"""
        try:
            full_url: str = f"{self.server_url}{self.client_id}"
            logger.info(f"Conectando a Aethelgard: {full_url}")
            
            self.websocket = await websockets.connect(full_url)
            self.is_connected = True
            
            logger.info("Conectado a Aethelgard exitosamente")
            
            # Enviar mensaje de inicialización
            await self.send_message({
                "type": "init",
                "client_id": self.client_id,
                "symbol": self.symbol,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error conectando a Aethelgard: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self) -> None:
        """Desconecta del servidor"""
        try:
            self.running = False
            self.is_connected = False
            
            if self.websocket:
                await self.websocket.close()
            
            logger.info("Desconectado de Aethelgard")
        except Exception as e:
            logger.error(f"Error desconectando: {e}")
        finally:
            if mt5:
                mt5.shutdown()  # type: ignore
    
    async def send_message(self, data: dict) -> None:
        """Envía un mensaje al servidor"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            message: str = json.dumps(data)
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            self.is_connected = False
    
    async def receive_messages(self) -> None:
        """Recibe mensajes del servidor"""
        try:
            while self.running and self.is_connected:
                try:
                    if self.websocket is None:
                        break
                    message = await self.websocket.recv()
                    await self.process_message(str(message))
                except ConnectionClosed:
                    logger.warning("Conexión cerrada por el servidor")
                    self.is_connected = False
                    break
                except Exception as e:
                    logger.error(f"Error recibiendo mensaje: {e}")
                    break
        except Exception as e:
            logger.error(f"Error en receive_messages: {e}")
    
    async def process_message(self, message: str) -> None:
        """Procesa un mensaje recibido del servidor"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "signal":
                # Nueva señal recibida desde Aethelgard
                await self.handle_signal(data)
            elif message_type == "signal_processed":
                logger.info(
                    f"Señal procesada. ID: {data.get('signal_id')}, "
                    f"Régimen: {data.get('regime')}"
                )
            elif message_type == "pong":
                # Heartbeat response
                pass
            elif message_type == "error":
                logger.error(f"Error de Aethelgard: {data.get('message')}")
            else:
                logger.warning(f"Mensaje desconocido: {message_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Error decodificando JSON: {message}")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    async def handle_signal(self, signal_data: dict) -> None:
        """
        Procesa una señal recibida desde Aethelgard Signal Factory
        
        Args:
            signal_data: Datos de la señal en formato JSON
        """
        try:
            signal_type = signal_data.get("signal_type")
            symbol = signal_data.get("symbol", self.symbol)
            price = signal_data.get("price")
            volume = signal_data.get("volume", self.default_volume)
            stop_loss = signal_data.get("stop_loss")
            take_profit = signal_data.get("take_profit")
            score = signal_data.get("score", 0)
            membership_tier = signal_data.get("membership_tier", "FREE")
            
            logger.info(
                f"📊 Señal recibida: {symbol} {signal_type} @ {price} | "
                f"Score: {score} | Tier: {membership_tier}"
            )
            
            if not self.auto_execute:
                logger.info("Auto-ejecución deshabilitada. Señal registrada pero no ejecutada.")
                return
            
            # Obtener precio si no está especificado
            if price is None:
                tick = mt5.symbol_info_tick(symbol)  # type: ignore
                if tick is None:
                    logger.error(f"No se pudo obtener precio para {symbol}")
                    return
                price = tick.ask if signal_type == "BUY" else tick.bid
            
            # Ejecutar señal según tipo
            if signal_type == "BUY":
                result = await self.execute_buy(
                    symbol, volume, price, stop_loss, take_profit, signal_data
                )
            elif signal_type == "SELL":
                result = await self.execute_sell(
                    symbol, volume, price, stop_loss, take_profit, signal_data
                )
            elif signal_type == "CLOSE":
                result = await self.close_positions(symbol)
            else:
                logger.warning(f"Tipo de señal desconocido: {signal_type}")
                return
            
            # Registrar resultado
            if result:
                self.signal_results.append(result)
                logger.info(f"✅ Señal ejecutada exitosamente: Ticket {result.get('ticket')}")
            
        except Exception as e:
            logger.error(f"Error manejando señal: {e}", exc_info=True)
    
    async def execute_buy(
        self,
        symbol: str,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        signal_data: Optional[dict] = None
    ) -> Optional[Dict]:
        """
        Ejecuta una orden de compra en MT5
        
        Args:
            symbol: Símbolo del instrumento
            volume: Volumen a operar
            price: Precio de referencia
            stop_loss: Stop loss
            take_profit: Take profit
            signal_data: Datos completos de la señal
        
        Returns:
            Diccionario con resultado de la operación
        """
        try:
            # Preparar la orden
            signal_id = signal_data.get('signal_id') if signal_data else None
            strategy_id = signal_data.get('strategy_id', 'unknown') if signal_data else 'unknown'
            comment = f"Aethelgard_signal_{signal_id}_{strategy_id}" if signal_id else f"Aethelgard_{strategy_id}"
            request = {
                "action": mt5.TRADE_ACTION_DEAL,  # type: ignore
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY,  # type: ignore
                "price": mt5.symbol_info_tick(symbol).ask,  # type: ignore
                "sl": stop_loss if stop_loss else 0.0,
                "tp": take_profit if take_profit else 0.0,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,  # type: ignore
                "type_filling": mt5.ORDER_FILLING_IOC,  # type: ignore
            }
            
            # Enviar orden
            result = mt5.order_send(request)  # type: ignore
            
            if result is None:
                logger.error(f"Error enviando orden BUY: {mt5.last_error()}")  # type: ignore
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:  # type: ignore
                logger.error(f"Orden BUY rechazada: {result.retcode} - {result.comment}")
                return None
            
            # Registrar posición
            position_info = {
                "ticket": result.order,
                "symbol": symbol,
                "type": "BUY",
                "volume": volume,
                "open_price": result.price,
                "open_time": datetime.now(),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "signal_data": signal_data
            }
            
            self.active_positions[result.order] = position_info
            
            logger.info(
                f"🟢 BUY ejecutado: {symbol} | Vol: {volume} | "
                f"Precio: {result.price} | Ticket: {result.order}"
            )
            
            return {
                "executed": True,
                "ticket": result.order,
                "execution_price": result.price,
                "execution_time": datetime.now().isoformat(),
                "signal_data": signal_data
            }
        
        except Exception as e:
            logger.error(f"Error ejecutando BUY: {e}", exc_info=True)
            return None
    
    async def execute_sell(
        self,
        symbol: str,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        signal_data: Optional[dict] = None
    ) -> Optional[Dict]:
        """
        Ejecuta una orden de venta en MT5
        
        Args:
            symbol: Símbolo del instrumento
            volume: Volumen a operar
            price: Precio de referencia
            stop_loss: Stop loss
            take_profit: Take profit
            signal_data: Datos completos de la señal
        
        Returns:
            Diccionario con resultado de la operación
        """
        try:
            # Preparar la orden
            signal_id = signal_data.get('signal_id') if signal_data else None
            strategy_id = signal_data.get('strategy_id', 'unknown') if signal_data else 'unknown'
            comment = f"Aethelgard_signal_{signal_id}_{strategy_id}" if signal_id else f"Aethelgard_{strategy_id}"
            request = {
                "action": mt5.TRADE_ACTION_DEAL,  # type: ignore
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_SELL,  # type: ignore
                "price": mt5.symbol_info_tick(symbol).bid,  # type: ignore
                "sl": stop_loss if stop_loss else 0.0,
                "tp": take_profit if take_profit else 0.0,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,  # type: ignore
                "type_filling": mt5.ORDER_FILLING_IOC,  # type: ignore
            }
            
            # Enviar orden
            result = mt5.order_send(request)  # type: ignore
            
            if result is None:
                logger.error(f"Error enviando orden SELL: {mt5.last_error()}")  # type: ignore
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:  # type: ignore
                logger.error(f"Orden SELL rechazada: {result.retcode} - {result.comment}")
                return None
            
            # Registrar posición
            position_info = {
                "ticket": result.order,
                "symbol": symbol,
                "type": "SELL",
                "volume": volume,
                "open_price": result.price,
                "open_time": datetime.now(),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "signal_data": signal_data
            }
            
            self.active_positions[result.order] = position_info
            
            logger.info(
                f"🔴 SELL ejecutado: {symbol} | Vol: {volume} | "
                f"Precio: {result.price} | Ticket: {result.order}"
            )
            
            return {
                "executed": True,
                "ticket": result.order,
                "execution_price": result.price,
                "execution_time": datetime.now().isoformat(),
                "signal_data": signal_data
            }
        
        except Exception as e:
            logger.error(f"Error ejecutando SELL: {e}", exc_info=True)
            return None
    
    async def close_positions(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """
        Cierra posiciones abiertas
        
        Args:
            symbol: Si se especifica, cierra solo posiciones de ese símbolo
        
        Returns:
            Diccionario con resumen de cierres
        """
        try:
            positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()  # type: ignore
            
            if positions is None or len(positions) == 0:
                logger.info("No hay posiciones abiertas para cerrar")
                return {"closed": 0, "failed": 0}
            
            closed = 0
            failed = 0
            
            for position in positions:
                # Solo cerrar posiciones de Aethelgard (magic number)
                if position.magic != self.magic_number:
                    continue
                
                # Preparar orden de cierre
                # Extraer signal_id del comentario original si existe
                signal_id = None
                if hasattr(position, 'comment') and position.comment:
                    import re
                    match = re.search(r'signal_(\w+)', position.comment)
                    if match:
                        signal_id = match.group(1)
                comment = f"Aethelgard_Close_signal_{signal_id}" if signal_id else "Aethelgard_Close"
                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,  # type: ignore
                    "symbol": position.symbol,
                    "volume": position.volume,
                    "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,  # type: ignore
                    "position": position.ticket,
                    "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,  # type: ignore
                    "deviation": 20,
                    "magic": self.magic_number,
                    "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC,  # type: ignore
                    "type_filling": mt5.ORDER_FILLING_IOC,  # type: ignore
                }
                
                result = mt5.order_send(close_request)  # type: ignore
                
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:  # type: ignore
                    closed += 1
                    logger.info(f"✅ Posición cerrada: Ticket {position.ticket}")
                    
                    # Eliminar de tracking
                    if position.ticket in self.active_positions:
                        del self.active_positions[position.ticket]
                else:
                    failed += 1
                    logger.error(f"❌ Error cerrando posición {position.ticket}")
            
            return {"closed": closed, "failed": failed}
        
        except Exception as e:
            logger.error(f"Error cerrando posiciones: {e}", exc_info=True)
            return {"closed": 0, "failed": 0}
    
    def get_position_pnl(self, ticket: int) -> Optional[float]:
        """
        Obtiene el P&L actual de una posición
        
        Args:
            ticket: Ticket de la posición
        
        Returns:
            P&L en la moneda de la cuenta
        """
        try:
            positions = mt5.positions_get(ticket=ticket)  # type: ignore
            if positions and len(positions) > 0:
                return positions[0].profit
            return None
        except Exception as e:
            logger.error(f"Error obteniendo P&L: {e}")
            return None
    
    def get_closed_positions(self, hours: int = 24) -> List[Dict]:
        """
        Get closed positions from MT5 history (for feedback loop).
        
        Args:
            hours: Look back this many hours (default: 24)
        
        Returns:
            List of closed position dicts with trade results
        """
        try:
            from datetime import timedelta
            
            # Calculate time range
            now: datetime = datetime.now()
            from_date: datetime = now - timedelta(hours=hours)
            
            # Get history deals
            deals = mt5.history_deals_get(from_date, now)  # type: ignore
            
            if deals is None:
                logger.warning("No history deals found")
                return []
            
            closed_positions = []
            
            # Process deals - filter only our magic number and exits
            for deal in deals:
                # Only process our trades
                if deal.magic != self.magic_number:
                    continue
                
                # Only process exits (DEAL_ENTRY_OUT)
                if deal.entry != mt5.DEAL_ENTRY_OUT:  # type: ignore
                    continue
                
                # Build position info
                position_info = {
                    'ticket': deal.position_id,
                    'symbol': deal.symbol,
                    'entry_price': None,  # Will need to find entry deal
                    'exit_price': deal.price,
                    'profit': deal.profit,
                    'volume': deal.volume,
                    'close_time': datetime.fromtimestamp(deal.time),
                    'exit_reason': self._detect_exit_reason(deal),
                    'signal_id': self._extract_signal_id(deal.comment)
                }
                
                # Try to find entry price from position history
                entry_deal = self._find_entry_deal(deal.position_id, from_date, now)
                if entry_deal:
                    position_info['entry_price'] = entry_deal.price
                
                closed_positions.append(position_info)
            
            logger.info(f"Found {len(closed_positions)} closed positions in last {hours}h")
            return closed_positions
        
        except Exception as e:
            logger.error(f"Error getting closed positions: {e}")
            return []
    
    def _find_entry_deal(self, position_id: int, from_date: datetime, to_date: datetime) -> None:
        """Find the entry deal for a position"""
        try:
            deals = mt5.history_deals_get(from_date, to_date, position=position_id)  # type: ignore
            if deals:
                # Find DEAL_ENTRY_IN
                for deal in deals:
                    if deal.entry == mt5.DEAL_ENTRY_IN:  # type: ignore
                        return deal
            return None
        except Exception as e:
            logger.error(f"Error finding entry deal: {e}")
            return None
    
    def _detect_exit_reason(self, deal: Any) -> str:
        """Detect why a position was closed"""
        comment = deal.comment.lower()
        
        if 'tp' in comment or 'take profit' in comment:
            return 'TAKE_PROFIT'
        elif 'sl' in comment or 'stop loss' in comment:
            return 'STOP_LOSS'
        elif 'close' in comment or 'aethelgard_close' in comment:
            return 'MANUAL'
        else:
            return 'CLOSED'
    
    def _extract_signal_id(self, comment: str) -> Optional[str]:
        """Extract signal ID from deal comment if present"""
        try:
            # Comment format: "Aethelgard_strategy_id" or custom format
            if 'signal_' in comment:
                parts: List[str] = comment.split('signal_')
                if len(parts) > 1:
                    return f"signal_{parts[1].split('_')[0]}"
            return None
        except Exception:
            return None
    
    async def send_market_data(self) -> None:
        """Envía datos de mercado actuales"""
        try:
            tick = mt5.symbol_info_tick(self.symbol)  # type: ignore
            if tick is None:
                logger.warning(f"No se pudo obtener tick para {self.symbol}")
                return
            
            await self.send_message({
                "type": "market_data",
                "symbol": self.symbol,
                "price": tick.last,
                "bid": tick.bid,
                "ask": tick.ask,
                "volume": tick.volume,
                "timestamp": datetime.fromtimestamp(tick.time).isoformat()
            })
        
        except Exception as e:
            logger.error(f"Error enviando market data: {e}")
    
    async def send_signal(self, 
                         signal_type: str,
                         price: float,
                         volume: float = 0.01,
                         stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None,
                         strategy_id: Optional[str] = None) -> None:
        """
        Envía una señal de trading a Aethelgard
        
        Args:
            signal_type: 'BUY', 'SELL', 'CLOSE', 'MODIFY'
            price: Precio de la señal
            volume: Volumen/lotes
            stop_loss: Stop loss opcional
            take_profit: Take profit opcional
            strategy_id: ID de la estrategia que genera la señal
        """
        await self.send_message({
            "type": "signal",
            "connector": "MT5",
            "symbol": self.symbol,
            "signal_type": signal_type,
            "price": price,
            "timestamp": datetime.utcnow().isoformat(),
            "volume": volume,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_id": strategy_id,
            "metadata": {
                "account": mt5.account_info().login if mt5.account_info() else None,  # type: ignore
                "terminal": "MT5"
            }
        })
    
    async def monitor_ticks(self, interval: float = 1.0) -> None:
        """
        Monitorea ticks y envía datos periódicamente
        
        Args:
            interval: Intervalo en segundos entre envíos
        """
        self.running = True
        
        while self.running:
            try:
                if self.is_connected:
                    await self.send_market_data()
                
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"Error en monitor_ticks: {e}")
                break
    
    async def run(self, tick_interval: float = 1.0) -> None:
        """
        Ejecuta el bridge (conecta y monitorea)
        
        Args:
            tick_interval: Intervalo en segundos para enviar ticks
        """
        try:
            await self.connect()
            
            # Iniciar tareas en paralelo
            receive_task: asyncio.Task[None] = asyncio.create_task(self.receive_messages())
            monitor_task: asyncio.Task[None] = asyncio.create_task(self.monitor_ticks(tick_interval))
            
            # Esperar a que terminen
            await asyncio.gather(receive_task, monitor_task)
        
        except KeyboardInterrupt:
            logger.info("Interrupción recibida")
        except Exception as e:
            logger.error(f"Error en run: {e}")
        finally:
            await self.disconnect()


async def main() -> None:
    """Función principal para ejecutar el bridge"""
    bridge = MT5Bridge(
        server_url="ws://localhost:8000/ws/MT5/",
        symbol="EURUSD"
    )
    
    try:
        await bridge.run(tick_interval=1.0)
    except Exception as e:
        logger.error(f"Error en main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
