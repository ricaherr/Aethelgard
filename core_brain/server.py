"""
Servidor FastAPI con WebSockets para Aethelgard
Gestiona múltiples conexiones simultáneas y diferencia entre conectores
"""
import json
import logging
from typing import Dict, Set
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models.signal import Signal, ConnectorType, SignalResult, MarketRegime
from core_brain.regime import RegimeClassifier
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier
from core_brain.module_manager import get_module_manager, MembershipLevel

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestiona las conexiones WebSocket activas"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connector_types: Dict[str, ConnectorType] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, connector: ConnectorType):
        """Acepta una nueva conexión WebSocket"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connector_types[client_id] = connector
        logger.info(f"Conexión establecida: {client_id} ({connector.value})")
    
    def disconnect(self, client_id: str):
        """Elimina una conexión"""
        if client_id in self.active_connections:
            connector = self.connector_types.get(client_id, "Unknown")
            del self.active_connections[client_id]
            del self.connector_types[client_id]
            logger.info(f"Conexión cerrada: {client_id} ({connector})")
    
    async def send_personal_message(self, message: dict, client_id: str):
        """Envía un mensaje a un cliente específico"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error enviando mensaje a {client_id}: {e}")
                self.disconnect(client_id)
    
    async def broadcast(self, message: dict, exclude: Set[str] = None):
        """Envía un mensaje a todos los clientes conectados"""
        if exclude is None:
            exclude = set()
        
        disconnected = []
        for client_id, websocket in self.active_connections.items():
            if client_id not in exclude:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error en broadcast a {client_id}: {e}")
                    disconnected.append(client_id)
        
        for client_id in disconnected:
            self.disconnect(client_id)


# Instancias globales
manager = ConnectionManager()
regime_classifier = RegimeClassifier()
storage = StorageManager()

# Estado para detectar cambios de régimen
_last_regime_by_symbol: Dict[str, MarketRegime] = {}


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI"""
    app = FastAPI(
        title="Aethelgard Trading System",
        description="Sistema de trading algorítmico agnóstico",
        version="1.0.0"
    )
    
    @app.get("/")
    async def root():
        """Endpoint raíz"""
        return {
            "name": "Aethelgard",
            "version": "1.0.0",
            "status": "running",
            "active_connections": len(manager.active_connections)
        }
    
    @app.get("/health")
    async def health():
        """Health check endpoint"""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    @app.websocket("/ws/{connector}/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, connector: str, client_id: str):
        """
        Endpoint WebSocket principal
        Formato: /ws/{connector}/{client_id}
        Connector puede ser: NT, MT5, TV
        """
        # Validar tipo de conector
        try:
            connector_type = ConnectorType(connector.upper())
        except ValueError:
            await websocket.close(code=1008, reason=f"Conector inválido: {connector}")
            return
        
        await manager.connect(websocket, client_id, connector_type)
        
        try:
            while True:
                # Recibir mensaje del cliente
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    
                    # Procesar señal
                    if message.get("type") == "signal":
                        await process_signal(message, client_id, connector_type)
                    elif message.get("type") == "ping":
                        # Heartbeat
                        await manager.send_personal_message(
                            {"type": "pong", "timestamp": datetime.now().isoformat()},
                            client_id
                        )
                    else:
                        logger.warning(f"Mensaje desconocido de {client_id}: {message.get('type')}")
                
                except json.JSONDecodeError:
                    logger.error(f"JSON inválido de {client_id}: {data}")
                    await manager.send_personal_message(
                        {"type": "error", "message": "JSON inválido"},
                        client_id
                    )
                except ValidationError as e:
                    logger.error(f"Error de validación de {client_id}: {e}")
                    await manager.send_personal_message(
                        {"type": "error", "message": f"Error de validación: {str(e)}"},
                        client_id
                    )
                except Exception as e:
                    logger.error(f"Error procesando mensaje de {client_id}: {e}")
                    await manager.send_personal_message(
                        {"type": "error", "message": f"Error interno: {str(e)}"},
                        client_id
                    )
        
        except WebSocketDisconnect:
            manager.disconnect(client_id)
        except Exception as e:
            logger.error(f"Error en WebSocket {client_id}: {e}")
            manager.disconnect(client_id)
    
    @app.post("/api/signal")
    async def receive_signal_http(signal_data: dict):
        """
        Endpoint HTTP alternativo para recibir señales
        Útil para webhooks (TradingView)
        """
        try:
            # Determinar conector desde metadata o header
            connector_str = signal_data.get("connector", "TV")
            try:
                connector_type = ConnectorType(connector_str.upper())
            except ValueError:
                connector_type = ConnectorType.TRADINGVIEW
            
            client_id = signal_data.get("client_id", "http_client")
            
            await process_signal(signal_data, client_id, connector_type)
            
            return JSONResponse(
                status_code=200,
                content={"status": "received", "message": "Señal procesada correctamente"}
            )
        
        except Exception as e:
            logger.error(f"Error procesando señal HTTP: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/regime/{symbol}")
    async def get_regime(symbol: str):
        """Obtiene el régimen de mercado actual para un símbolo"""
        regime = regime_classifier.classify()
        return {
            "symbol": symbol,
            "regime": regime.value,
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/api/signals")
    async def get_signals(limit: int = 100):
        """Obtiene las últimas señales registradas"""
        signals = storage.get_recent_signals(limit)
        return {"signals": signals, "count": len(signals)}
    
    return app


async def process_signal(message: dict, client_id: str, connector_type: ConnectorType):
    """
    Procesa una señal recibida:
    1. Valida y crea el modelo Signal
    2. Clasifica el régimen de mercado
    3. Detecta cambios de régimen y registra estado completo
    4. Guarda en la base de datos
    5. Envía respuesta al cliente
    """
    try:
        # Asegurar que el conector esté en el mensaje
        message["connector_type"] = connector_type
        
        # Crear modelo Signal
        signal = Signal(**message)
        
        # Obtener régimen anterior para este símbolo
        previous_regime = _last_regime_by_symbol.get(signal.symbol)
        
        # Clasificar régimen de mercado
        regime = regime_classifier.classify(signal.price)
        signal.regime = regime
        
        # Detectar cambio de régimen y registrar estado completo
        if previous_regime is None or regime != previous_regime:
            # Obtener todas las métricas del clasificador
            metrics = regime_classifier.get_metrics()
            
            # Preparar datos del estado de mercado
            state_data = {
                'symbol': signal.symbol,
                'timestamp': signal.timestamp.isoformat(),
                'regime': regime.value,
                'previous_regime': previous_regime.value if previous_regime else None,
                'price': signal.price,
                'adx': metrics.get('adx'),
                'volatility': metrics.get('volatility'),
                'sma_distance': metrics.get('sma_distance'),
                'bias': metrics.get('bias'),
                'atr_pct': metrics.get('atr_pct'),
                'volatility_shock_detected': metrics.get('volatility_shock_detected', False),
                'adx_period': regime_classifier.adx_period,
                'sma_period': regime_classifier.sma_period,
                'adx_trend_threshold': regime_classifier.adx_trend_threshold,
                'adx_range_threshold': regime_classifier.adx_range_threshold,
                'adx_range_exit_threshold': regime_classifier.adx_range_exit_threshold,
                'volatility_shock_multiplier': regime_classifier.volatility_shock_multiplier,
                'shock_lookback': regime_classifier.shock_lookback,
                'min_volatility_atr_period': regime_classifier.min_volatility_atr_period,
                'persistence_candles': regime_classifier.persistence_candles
            }
            
            # Guardar estado de mercado
            try:
                storage.log_market_state(state_data)
                logger.info(
                    f"Cambio de régimen detectado: {signal.symbol} "
                    f"{previous_regime.value if previous_regime else 'N/A'} -> {regime.value}"
                )
            except Exception as e:
                logger.error(f"Error guardando estado de mercado: {e}")
            
            # Enviar notificación de cambio de régimen
            notifier = get_notifier()
            if notifier:
                # Por defecto usar membresía básica, en producción esto debería venir del usuario
                membership = MembershipLevel.BASIC
                try:
                    await notifier.notify_regime_change(
                        symbol=signal.symbol,
                        previous_regime=previous_regime,
                        new_regime=regime,
                        price=signal.price,
                        membership=membership,
                        metrics=metrics
                    )
                except Exception as e:
                    logger.error(f"Error enviando notificación de cambio de régimen: {e}")
            
            # Actualizar régimen anterior
            _last_regime_by_symbol[signal.symbol] = regime
        
        # Guardar en base de datos
        signal_id = storage.save_signal(signal)
        
        logger.info(
            f"Señal procesada: {signal.symbol} {signal.signal_type.value} "
            f"@ {signal.price} - Régimen: {regime.value} (ID: {signal_id})"
        )
        
        # Enviar confirmación al cliente
        response = {
            "type": "signal_processed",
            "signal_id": signal_id,
            "regime": regime.value,
            "timestamp": datetime.now().isoformat()
        }
        
        await manager.send_personal_message(response, client_id)
        
        # Verificar si es una señal de Oliver Vélez y enviar notificación
        module_manager = get_module_manager()
        notifier = get_notifier()
        
        # Una señal es de Oliver Vélez si:
        # 1. El strategy_id contiene "oliver_velez" o
        # 2. El módulo oliver_velez está activo y el régimen es compatible
        is_oliver_velez = (
            signal.strategy_id and "oliver_velez" in signal.strategy_id.lower()
        ) or (
            module_manager.is_module_enabled("oliver_velez") and
            regime in [MarketRegime.TREND, MarketRegime.RANGE]
        )
        
        if is_oliver_velez and notifier:
            # Por defecto usar membresía básica, en producción esto debería venir del usuario
            membership = MembershipLevel.BASIC
            try:
                strategy_details = {
                    "Régimen": regime.value,
                    "ADX": f"{metrics.get('adx', 0):.2f}" if metrics else "N/A",
                    "Volatilidad": f"{metrics.get('volatility', 0):.4f}" if metrics else "N/A"
                }
                await notifier.notify_oliver_velez_signal(
                    signal=signal,
                    membership=membership,
                    strategy_details=strategy_details
                )
            except Exception as e:
                logger.error(f"Error enviando notificación de señal Oliver Vélez: {e}")
        
        # Aquí se podría añadir lógica para ejecutar estrategias
        # basadas en el régimen detectado y módulos activos
        
    except Exception as e:
        logger.error(f"Error procesando señal de {client_id}: {e}")
        raise


# Crear instancia de la app
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
