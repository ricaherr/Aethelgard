"""
Bridge para MetaTrader 5
Conecta estrategias de MT5 con Aethelgard via WebSocket
Ahora incluye capacidad de ejecutar señales automáticamente en cuenta Demo
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List
import websockets
from websockets.exceptions import ConnectionClosed

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 no está instalado. Instala con: pip install MetaTrader5")
    mt5 = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5Bridge:
    """Bridge para conectar MetaTrader 5 con Aethelgard y ejecutar señales automáticamente"""
    
    def __init__(self, 
                 server_url: str = "ws://localhost:8000/ws/MT5/",
                 client_id: str = None,
                 symbol: str = "EURUSD",
                 auto_execute: bool = True,
                 demo_mode: bool = True,
                 default_volume: float = 0.01,
                 magic_number: int = 234000):
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
        self.server_url = server_url
        self.client_id = client_id or f"MT5_{symbol}"
        self.symbol = symbol
        self.websocket = None
        self.is_connected = False
        self.running = False
        self.auto_execute = auto_execute
        self.demo_mode = demo_mode
        self.default_volume = default_volume
        self.magic_number = magic_number
        
        # Tracking de operaciones
        self.active_positions: Dict[int, Dict] = {}  # ticket -> position_info
        self.signal_results: List[Dict] = []  # Historial de resultados
        
        # Inicializar MT5
        if mt5 is None:
            raise ImportError("MetaTrader5 no está disponible")
        
        if not mt5.initialize():
            raise RuntimeError(f"Error inicializando MT5: {mt5.last_error()}")
        
        # Verificar modo demo
        account_info = mt5.account_info()
        if account_info is None:
            raise RuntimeError("No se pudo obtener información de la cuenta")
        
        is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        
        if self.demo_mode and not is_demo:
            logger.warning("⚠️  ADVERTENCIA: demo_mode=True pero conectado a cuenta REAL")
            logger.warning("⚠️  Auto-ejecución deshabilitada por seguridad")
            self.auto_execute = False
        
        logger.info(f"MT5 inicializado. Versión: {mt5.version()}")
        logger.info(f"Cuenta: {account_info.login} | Demo: {is_demo} | Auto-Execute: {self.auto_execute}")
    
    async def connect(self):
        """Conecta al servidor Aethelgard"""
        try:
            full_url = f"{self.server_url}{self.client_id}"
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
    
    async def disconnect(self):
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
                mt5.shutdown()
    
    async def send_message(self, data: dict):
        """Envía un mensaje al servidor"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            message = json.dumps(data)
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            self.is_connected = False
    
    async def receive_messages(self):
        """Recibe mensajes del servidor"""
        try:
            while self.running and self.is_connected:
                try:
                    message = await self.websocket.recv()
                    await self.process_message(message)
                except ConnectionClosed:
                    logger.warning("Conexión cerrada por el servidor")
                    self.is_connected = False
                    break
                except Exception as e:
                    logger.error(f"Error recibiendo mensaje: {e}")
                    break
        except Exception as e:
            logger.error(f"Error en receive_messages: {e}")
    
    async def process_message(self, message: str):
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
    
    async def handle_signal(self, signal_data: dict):
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
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY,
                "price": mt5.symbol_info_tick(symbol).ask,
                "sl": stop_loss if stop_loss else 0.0,
                "tp": take_profit if take_profit else 0.0,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"Aethelgard_{signal_data.get('strategy_id', 'unknown')}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Enviar orden
            result = mt5.order_send(request)
            
            if result is None:
                logger.error(f"Error enviando orden BUY: {mt5.last_error()}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
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
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_SELL,
                "price": mt5.symbol_info_tick(symbol).bid,
                "sl": stop_loss if stop_loss else 0.0,
                "tp": take_profit if take_profit else 0.0,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"Aethelgard_{signal_data.get('strategy_id', 'unknown')}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Enviar orden
            result = mt5.order_send(request)
            
            if result is None:
                logger.error(f"Error enviando orden SELL: {mt5.last_error()}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
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
            positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            
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
                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": position.symbol,
                    "volume": position.volume,
                    "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                    "position": position.ticket,
                    "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
                    "deviation": 20,
                    "magic": self.magic_number,
                    "comment": "Aethelgard_Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(close_request)
                
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
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
            positions = mt5.positions_get(ticket=ticket)
            if positions and len(positions) > 0:
                return positions[0].profit
            return None
        except Exception as e:
            logger.error(f"Error obteniendo P&L: {e}")
            return None
    
    async def send_market_data(self):
        """Envía datos de mercado actuales"""
        try:
            tick = mt5.symbol_info_tick(self.symbol)
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
                         strategy_id: Optional[str] = None):
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
                "account": mt5.account_info().login if mt5.account_info() else None,
                "terminal": "MT5"
            }
        })
    
    async def monitor_ticks(self, interval: float = 1.0):
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
    
    async def run(self, tick_interval: float = 1.0):
        """
        Ejecuta el bridge (conecta y monitorea)
        
        Args:
            tick_interval: Intervalo en segundos para enviar ticks
        """
        try:
            await self.connect()
            
            # Iniciar tareas en paralelo
            receive_task = asyncio.create_task(self.receive_messages())
            monitor_task = asyncio.create_task(self.monitor_ticks(tick_interval))
            
            # Esperar a que terminen
            await asyncio.gather(receive_task, monitor_task)
        
        except KeyboardInterrupt:
            logger.info("Interrupción recibida")
        except Exception as e:
            logger.error(f"Error en run: {e}")
        finally:
            await self.disconnect()


async def main():
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
