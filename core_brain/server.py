"""
Servidor FastAPI con WebSockets para Aethelgard
Gestiona múltiples conexiones simultáneas y diferencia entre conectores
"""
import json
import logging
import asyncio
from typing import Dict, Set, Any, AsyncGenerator, Optional
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models.signal import Signal, ConnectorType, SignalResult, MarketRegime
from core_brain.regime import RegimeClassifier
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier
from core_brain.module_manager import get_module_manager, MembershipLevel
from fastapi.staticfiles import StaticFiles
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestiona las conexiones WebSocket activas"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connector_types: Dict[str, ConnectorType] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, connector: ConnectorType) -> None:
        """Acepta una nueva conexión WebSocket"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connector_types[client_id] = connector
        logger.info(f"Conexión establecida: {client_id} ({connector.value})")
    
    def disconnect(self, client_id: str) -> None:
        """Elimina una conexión"""
        if client_id in self.active_connections:
            connector = self.connector_types.get(client_id, "Unknown")
            del self.active_connections[client_id]
            del self.connector_types[client_id]
            logger.info(f"Conexión cerrada: {client_id} ({connector})")
    
    async def send_personal_message(self, message: dict, client_id: str) -> None:
        """Envía un mensaje a un cliente específico"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error enviando mensaje a {client_id}: {e}")
                self.disconnect(client_id)
    
    async def broadcast(self, message: dict, exclude: Set[str] = None) -> None:
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

    async def emit_event(self, event_type: str, payload: dict) -> None:
        """Envía un evento formateado a todos los clientes (especialmente UIs)"""
        await self.broadcast({
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        })


# Instancias globales
manager = ConnectionManager()
regime_classifier = RegimeClassifier()
storage = StorageManager()

# MT5 Connector reference (lazy-loaded when needed)
_mt5_connector_instance = None

def _get_mt5_connector() -> Optional[Any]:
    """Lazy-load MT5 connector for balance queries"""
    global _mt5_connector_instance
    if _mt5_connector_instance is None:
        try:
            from connectors.mt5_connector import MT5Connector
            _mt5_connector_instance = MT5Connector()
            # Connect immediately after creation
            if not _mt5_connector_instance.connect():
                logger.warning("MT5Connector created but connection failed")
                _mt5_connector_instance = None
                return None
        except Exception as e:
            logger.warning(f"Could not load MT5Connector: {e}")
            return None
    
    # Verify connection is still active
    if _mt5_connector_instance and not _mt5_connector_instance.is_connected:
        try:
            _mt5_connector_instance.connect()
        except Exception as e:
            logger.debug(f"Reconnection attempt failed: {e}")
    
    return _mt5_connector_instance

def _get_account_balance() -> float:
    """
    Get real account balance from MT5 or cached value.
    
    Returns:
        Account balance (USD) from MT5 if connected, otherwise cached or default
    """
    # Try to get from MT5 directly
    mt5 = _get_mt5_connector()
    if mt5:
        try:
            balance = mt5.get_account_balance()
            # Cache balance in system_state for future queries
            storage.update_system_state({
                "account_balance": balance,
                "balance_source": "MT5_LIVE",
                "balance_last_update": datetime.now().isoformat()
            })
            return balance
        except Exception as e:
            logger.debug(f"Could not get MT5 balance: {e}")
    
    # Fallback to cached balance in DB
    try:
        state = storage.get_system_state()
        cached_balance = state.get("account_balance")
        if cached_balance:
            return float(cached_balance)
    except Exception as e:
        logger.debug(f"Could not get cached balance: {e}")
    
    # Final fallback (initial capital)
    logger.warning("Using default balance 10000.0 - MT5 not connected")
    storage.update_system_state({
        "account_balance": 10000.0,
        "balance_source": "DEFAULT",
        "balance_last_update": datetime.now().isoformat()
    })
    return 10000.0

def _get_balance_metadata() -> Dict[str, Any]:
    """
    Get balance metadata (source, last update timestamp).
    
    Returns:
        Dict with source ('MT5_LIVE' | 'CACHED' | 'DEFAULT') and last_update timestamp
    """
    try:
        state = storage.get_system_state()
        return {
            "source": state.get("balance_source", "UNKNOWN"),
            "last_update": state.get("balance_last_update", datetime.now().isoformat()),
            "is_live": state.get("balance_source") == "MT5_LIVE"
        }
    except Exception as e:
        logger.debug(f"Could not get balance metadata: {e}")
        return {
            "source": "UNKNOWN",
            "last_update": datetime.now().isoformat(),
            "is_live": False
        }

# Estado para detectar cambios de régimen
_last_regime_by_symbol: Dict[str, MarketRegime] = {}

async def broadcast_thought(message: str, module: str = "CORE", level: str = "info") -> None:
    """Difunde un 'pensamiento' del cerebro a todas las interfaces conectadas"""
    await manager.emit_event("BREIN_THOUGHT", {
        "message": message,
        "module": module,
        "level": level
    })

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: Iniciar bucle de heartbeat y pensamientos iniciales
    asyncio.create_task(heartbeat_loop())
    await broadcast_thought("Cerebro Aethelgard inicializado. Sistema listo para operaciones.")
    
    # Migración/Semilla de configuración inicial
    try:
        await seed_config_to_db()
    except Exception as e:
        logger.error(f"Error en semilla de configuración: {e}")
        
    yield
    # Shutdown (opcional)
    logger.info("Servidor Aethelgard deteniéndose.")

async def seed_config_to_db() -> None:
    """Migra configuraciones de archivos JSON a la base de datos si no existen."""
    config_dir = os.path.join(os.getcwd(), "config")
    mapping = {
        "trading": "dynamic_params.json",
        "risk": "risk_settings.json",
        "system": "config.json"
    }
    
    current_state = storage.get_system_state()
    
    for category, filename in mapping.items():
        db_key = f"config_{category}"
        if db_key not in current_state:
            file_path = os.path.join(config_dir, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    storage.update_system_state({db_key: data})
                    logger.info(f"✅ Configuración '{category}' migrada del archivo {filename} a la DB.")
                except Exception as e:
                    logger.error(f"❌ No se pudo migrar {filename}: {e}")


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI"""
    app = FastAPI(
        title="Aethelgard Trading System",
        description="Sistema de trading algorítmico agnóstico",
        version="1.0.0",
        lifespan=lifespan
    )
    
    @app.get("/api/system/status")
    async def system_status() -> Dict[str, Any]:
        """Endpoint de estado del sistema"""
        return {
            "name": "Aethelgard",
            "version": "1.0.0",
            "status": "running",
            "active_connections": len(manager.active_connections),
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/health")
    async def health() -> Dict[str, Any]:
        """Health check endpoint"""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    @app.websocket("/ws/{connector}/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, connector: str, client_id: str) -> None:
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
    async def receive_signal_http(signal_data: dict) -> JSONResponse:
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
    async def get_regime(symbol: str) -> Dict[str, Any]:
        """Obtiene el régimen de mercado actual para un símbolo"""
        regime = regime_classifier.classify()
        return {
            "symbol": symbol,
            "regime": regime.value,
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/api/signals")
    async def get_signals(limit: int = 100) -> Dict[str, Any]:
        """Obtiene las últimas señales registradas"""
        signals = storage.get_recent_signals(limit=limit)
        return {"signals": signals, "count": len(signals)}

    @app.get("/api/config/{category}")
    async def get_config(category: str) -> Dict[str, Any]:
        """Obtiene una categoría de configuración de la DB"""
        db_key = f"config_{category}"
        state = storage.get_system_state()
        config_data = state.get(db_key)
        
        if config_data is None:
            # Intentar fallback a archivo si no está en DB
            seed_mapping = {
                "trading": "dynamic_params.json",
                "risk": "risk_settings.json",
                "system": "config.json"
            }
            filename = seed_mapping.get(category)
            if filename:
                file_path = os.path.join(os.getcwd(), "config", filename)
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                        # Auto-persistir para la próxima vez
                        storage.update_system_state({db_key: config_data})
            
        if config_data is None:
            raise HTTPException(status_code=404, detail=f"Categoría de configuración '{category}' no encontrada.")
            
        return {"category": category, "data": config_data}

    @app.post("/api/config/{category}")
    async def update_config(category: str, new_data: dict) -> Dict[str, Any]:
        """Actualiza una categoría de configuración en la DB"""
        db_key = f"config_{category}"
        try:
            storage.update_system_state({db_key: new_data})
            await broadcast_thought(f"Configuración '{category}' actualizada por el usuario.", module="CORE")
            return {"status": "success", "message": f"Configuración '{category}' guardada correctamente."}
        except Exception as e:
            logger.error(f"Error guardando configuración {category}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # === TELEGRAM ENDPOINTS ===
    from connectors.telegram_provisioner import TelegramProvisioner
    telegram_provisioner = TelegramProvisioner()
    
    @app.post("/api/telegram/validate")
    async def validate_telegram_token(data: dict) -> Dict[str, Any]:
        """Validates Telegram bot token"""
        bot_token = data.get("bot_token", "")
        is_valid, result = await telegram_provisioner.validate_bot_token(bot_token)
        
        if is_valid:
            return {"status": "success", "bot_info": result}
        else:
            return {"status": "error", "error": result.get("error")}
    
    @app.post("/api/telegram/get-chat-id")
    async def get_telegram_chat_id(data: dict) -> Dict[str, Any]:
        """Auto-detects user's chat_id from bot updates"""
        bot_token = data.get("bot_token", "")
        success, result = await telegram_provisioner.get_chat_id_from_updates(bot_token)
        
        if success:
            return {"status": "success", "chat_info": result}
        else:
            if result.get("error") == "no_messages":
                return {
                    "status": "waiting",
                    "message": result.get("hint")
                }
            return {"status": "error", "error": result.get("error")}
    
    @app.post("/api/telegram/test")
    async def test_telegram_message(data: dict) -> Dict[str, Any]:
        """Sends test message to verify configuration"""
        bot_token = data.get("bot_token", "")
        chat_id = data.get("chat_id", "")
        
        success, result = await telegram_provisioner.send_test_message(bot_token, chat_id)
        
        if success:
            return {"status": "success", "message_id": result.get("message_id")}
        else:
            return {"status": "error", "error": result.get("error")}
    
    @app.post("/api/telegram/save")
    async def save_telegram_config(data: dict) -> Dict[str, Any]:
        """Saves Telegram configuration to database and initializes notifier"""
        bot_token = data.get("bot_token", "")
        chat_id = data.get("chat_id", "")
        enabled = data.get("enabled", True)
        
        # Save to database
        telegram_config = {
            "bot_token": bot_token,
            "basic_chat_id": chat_id,
            "premium_chat_id": chat_id,  # Same chat for now, can be different later
            "enabled": enabled
        }
        
        storage.update_system_state({"config_notifications": telegram_config})
        
        # Re-initialize notifier with new config
        from core_brain.notificator import initialize_notifier
        initialize_notifier(
            bot_token=bot_token,
            basic_chat_id=chat_id,
            premium_chat_id=chat_id,
            enabled=enabled
        )
        
        await broadcast_thought("Notificaciones de Telegram configuradas correctamente.", module="CORE")
        logger.info(f"✅ Telegram configurado: Chat ID {chat_id}")
        
        return {
            "status": "success",
            "message": "Configuración guardada correctamente"
        }
    
    @app.get("/api/telegram/instructions")
    async def get_telegram_instructions() -> Dict[str, Any]:
        """Returns setup instructions in Spanish"""
        return telegram_provisioner.get_setup_instructions()
    
    # === PORTFOLIO & RISK ENDPOINTS ===
    
    @app.get("/api/positions/open")
    async def get_open_positions() -> Dict[str, Any]:
        """
        Get open positions with risk metadata.
        Returns positions with initial_risk_usd, r_multiple, asset_type.
        """
        try:
            # Get MT5 connector to get real-time positions
            from connectors.mt5_connector import MT5Connector
            
            positions_list = []
            total_risk = 0.0
            
            mt5 = MT5Connector()
            if mt5.connect():
                # Update cached balance when we connect to MT5
                try:
                    current_balance = mt5.get_account_balance()
                    storage.update_system_state({
                        "account_balance": current_balance,
                        "balance_source": "MT5_LIVE",
                        "balance_last_update": datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.debug(f"Could not update cached balance: {e}")
                
                # Get open positions from MT5
                mt5_positions = mt5.get_open_positions()
                
                if mt5_positions:
                    conn = storage._get_conn()
                    
                    for mt5_pos in mt5_positions:
                        ticket = mt5_pos['ticket']
                        
                        # Get metadata from DB
                        cursor = conn.execute("""
                            SELECT initial_risk_usd, entry_regime, entry_time, timeframe, strategy
                            FROM position_metadata
                            WHERE ticket = ?
                        """, (ticket,))
                        
                        row = cursor.fetchone()
                        if row:
                            risk, regime, entry_time, timeframe, strategy = row
                        else:
                            # No metadata - calculate on the fly
                            risk = 0.0
                            regime = "NEUTRAL"
                            entry_time = mt5_pos.get('time', '')
                            timeframe = None
                            strategy = None
                        
                        symbol = mt5_pos['symbol']
                        
                        # Classify asset type based on symbol
                        asset_type = "forex"
                        if symbol.startswith("XAU") or symbol.startswith("XAG"):
                            asset_type = "metal"
                        elif symbol.startswith("BTC") or symbol.startswith("ETH"):
                            asset_type = "crypto"
                        elif any(idx in symbol for idx in ["US30", "NAS100", "SPX500", "DJ30"]):
                            asset_type = "index"
                        
                        current_profit = mt5_pos.get('profit', 0.0)
                        
                        # Calculate R-multiple
                        r_multiple = (current_profit / risk) if risk > 0 else 0.0
                        
                        position_data = {
                            "ticket": ticket,
                            "symbol": symbol,
                            "entry_price": mt5_pos.get('price_open', 0.0),
                            "sl": mt5_pos.get('sl', 0.0),
                            "tp": mt5_pos.get('tp', 0.0),
                            "volume": mt5_pos.get('volume', 0.0),
                            "profit_usd": current_profit,
                            "initial_risk_usd": risk,
                            "r_multiple": round(r_multiple, 2),
                            "entry_regime": regime or "NEUTRAL",
                            "entry_time": str(entry_time),
                            "asset_type": asset_type,
                            "timeframe": timeframe,
                            "strategy": strategy
                        }
                        
                        positions_list.append(position_data)
                        total_risk += risk
                    
                    storage._close_conn(conn)
            
            return {
                "positions": positions_list,
                "total_risk_usd": round(total_risk, 2),
                "count": len(positions_list)
            }
            
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return {"positions": [], "total_risk_usd": 0.0, "count": 0}
    
    @app.get("/api/risk/summary")
    async def get_risk_summary() -> Dict[str, Any]:
        """
        Get account risk summary with distribution by asset type.
        Uses real MT5 balance if connected, otherwise cached or default value.
        Includes metadata about balance source (MT5_LIVE, CACHED, DEFAULT).
        """
        try:
            # Get open positions
            positions_response = await get_open_positions()
            positions = positions_response.get("positions", [])
            total_risk = positions_response.get("total_risk_usd", 0.0)
            
            # Get REAL account balance from MT5 (or cached/default)
            account_balance = _get_account_balance()
            balance_metadata = _get_balance_metadata()
            
            # Calculate risk percentage
            risk_percentage = (total_risk / account_balance * 100) if account_balance > 0 else 0.0
            max_allowed_risk = 5.0  # From risk_settings.json
            
            # Distribution by asset type
            by_asset = {}
            for pos in positions:
                asset = pos["asset_type"]
                if asset not in by_asset:
                    by_asset[asset] = {"count": 0, "risk": 0.0}
                by_asset[asset]["count"] += 1
                by_asset[asset]["risk"] += pos["initial_risk_usd"]
            
            # Round risk values
            for asset in by_asset:
                by_asset[asset]["risk"] = round(by_asset[asset]["risk"], 2)
            
            # Generate warnings
            warnings = []
            if risk_percentage > max_allowed_risk * 0.9:
                warnings.append(f"Total risk ({risk_percentage:.1f}%) approaching limit ({max_allowed_risk}%)")
            if risk_percentage > max_allowed_risk:
                warnings.append(f"⚠ CRITICAL: Risk ({risk_percentage:.1f}%) exceeds maximum ({max_allowed_risk}%)")
            
            return {
                "total_risk_usd": round(total_risk, 2),
                "account_balance": account_balance,
                "balance_metadata": balance_metadata,
                "risk_percentage": round(risk_percentage, 2),
                "max_allowed_risk_pct": max_allowed_risk,
                "positions_by_asset": by_asset,
                "warnings": warnings
            }
            
        except Exception as e:
            logger.error(f"Error getting risk summary: {e}")
            return {
                "total_risk_usd": 0.0,
                "account_balance": 0.0,
                "balance_metadata": {"source": "ERROR", "last_update": datetime.now().isoformat(), "is_live": False},
                "risk_percentage": 0.0,
                "max_allowed_risk_pct": 5.0,
                "positions_by_asset": {},
                "warnings": [f"Error: {str(e)}"]
            }
    
    @app.get("/api/modules/status")
    async def get_modules_status() -> Dict[str, Any]:
        """
        Get current status of system modules (feature flags).
        """
        try:
            modules_enabled = storage.get_global_modules_enabled()
            
            return {
                "modules": modules_enabled,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting modules status: {e}")
            # Return defaults
            return {
                "modules": {
                    "scanner": True,
                    "executor": True,
                    "position_manager": True,
                    "risk_manager": True,
                    "monitor": True,
                    "notificator": True
                },
                "timestamp": datetime.now().isoformat()
            }
    
    @app.post("/api/modules/toggle")
    async def toggle_module(data: dict) -> Dict[str, Any]:
        """
        Toggle a system module on/off.
        
        Body: {
            "module": "scanner",
            "enabled": true
        }
        """
        try:
            module_name = data.get("module", "")
            enabled = data.get("enabled", True)
            
            # Validate module name
            valid_modules = ["scanner", "executor", "position_manager", "risk_manager", "monitor", "notificator"]
            if module_name not in valid_modules:
                raise HTTPException(status_code=400, detail=f"Invalid module: {module_name}")
            
            # Risk manager cannot be disabled (safety critical)
            if module_name == "risk_manager" and not enabled:
                raise HTTPException(
                    status_code=403, 
                    detail="Risk Manager cannot be disabled (safety critical)"
                )
            
            # Update in database
            storage.set_global_module_enabled(module_name, enabled)
            
            # Broadcast update
            status = "enabled" if enabled else "disabled"
            await broadcast_thought(
                f"Module '{module_name}' {status} by user. Changes apply in next cycle (~1-10s)", 
                module="CORE"
            )
            
            logger.info(f"Module {module_name} {status} - Hot-reload in next cycle")
            
            return {
                "status": "success",
                "module": module_name,
                "enabled": enabled,
                "message": f"Module '{module_name}' {status} successfully. Changes apply in next cycle (~1-10s)",
                "hot_reload": True,
                "latency_seconds": "1-10"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error toggling module: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Montar archivos estáticos de la nueva UI si existen
    ui_dist_path = os.path.join(os.getcwd(), "ui", "dist")
    if os.path.exists(ui_dist_path):
        app.mount("/", StaticFiles(directory=ui_dist_path, html=True), name="ui")
        logger.info(f"UI Next-Gen montada desde: {ui_dist_path}")
    else:
        logger.warning(f"No se encontró la carpeta dist de la UI en: {ui_dist_path}. Corre 'npm run build' en ui_v2.")

    return app

async def heartbeat_loop() -> None:
    """Bucle infinito para enviar el pulso del sistema a la UI"""
    while True:
        try:
            # Recopilar métricas de salud (simplificado por ahora)
            metrics = {
                "core": "ACTIVE",
                "storage": "STABLE",
                "notificator": "CONFIGURED",
                "timestamp": datetime.now().isoformat()
            }
            
            # Obtener métricas de régimen para el radar
            # TODO: Idealmente esto vendría de un GlobalMonitor
            regime = regime_classifier.classify()
            metrics_edge = regime_classifier.get_metrics()
            
            await manager.emit_event("SYSTEM_HEARTBEAT", metrics)
            await manager.emit_event("REGIME_UPDATE", {
                "regime": regime.value,
                "metrics": {
                    "adx_strength": metrics_edge.get('adx', 0),
                    "volatility": "High" if metrics_edge.get('volatility_shock_detected') else "Normal",
                    "global_bias": metrics_edge.get('bias', 'Neutral'),
                    "confidence": 85, # Mock por ahora
                    "active_agents": 4, # Mock
                    "optimization_rate": 99.1 # Mock
                }
            })
            
        except Exception as e:
            logger.error(f"Error en bucle de heartbeat: {e}")
            
        await asyncio.sleep(5)


async def process_signal(message: dict, client_id: str, connector_type: ConnectorType) -> None:
    """
    Procesa una señal recibida:
    1. Valida y crea el modelo Signal
    2. Clasifica el régimen de mercado
    3. Detecta cambios de régimen y registra estado completo
    4. Guarda en la base de datos
    5. Envía respuesta al cliente
    """
    try:
        # Pensamiento inicial
        await broadcast_thought(f"Analizando nueva señal para {message.get('symbol', 'Unknown')}...", module="SCANNER")
        
        # Asegurar que el conector esté en el mensaje
        message["connector_type"] = connector_type
        
        # Crear modelo Signal
        signal = Signal(**message)
        
        # Obtener régimen anterior para este símbolo
        previous_regime = _last_regime_by_symbol.get(signal.symbol)
        
        # Clasificar régimen de mercado
        regime = regime_classifier.classify(signal.price)
        signal.regime = regime
        await broadcast_thought(f"Régimen detectado: {regime.value} para {signal.symbol}", module="REGIME")
        
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
        
        if is_oliver_velez:
            await broadcast_thought(f"Validando parámetros de Oliver Vélez para {signal.symbol}...", module="STRATEGY")
        
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
