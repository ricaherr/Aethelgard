"""
Servidor FastAPI con WebSockets para Aethelgard
Gestiona múltiples conexiones simultáneas y diferencia entre conectores
"""
import json
import logging
import asyncio
from typing import Dict, Set, Any, AsyncGenerator, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models.signal import Signal, ConnectorType, SignalResult, MarketRegime
from core_brain.regime import RegimeClassifier
from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier
from core_brain.module_manager import get_module_manager, MembershipLevel
from core_brain.services.socket_service import get_socket_service, SocketService
from core_brain.services.system_service import get_system_service, SystemService
from fastapi.staticfiles import StaticFiles
import os
import time

# Configurar logging
# logging.basicConfig(level=logging.INFO)  # DISABLED: Let start.py configure logging
logger = logging.getLogger(__name__)

# ============ Service Instances (Lazy-loaded) ============
_socket_service_instance = None
_system_service_instance = None
_storage_instance = None  # Lazy-loaded storage
regime_classifier = None  # Lazy-loaded regime classifier

def _get_socket_service() -> SocketService:
    """Lazy-load SocketService singleton."""
    global _socket_service_instance
    if _socket_service_instance is None:
        _socket_service_instance = get_socket_service()
    return _socket_service_instance

def _get_system_service() -> SystemService:
    """Lazy-load SystemService singleton."""
    global _system_service_instance
    if _system_service_instance is None:
        _system_service_instance = get_system_service(
            storage=_get_storage(),
            regime_classifier=_get_regime_classifier()
        )
    return _system_service_instance

def _get_storage() -> 'StorageManager':
    """Lazy-load StorageManager to avoid import-time initialization."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageManager()
    return _storage_instance

def _get_regime_classifier() -> 'RegimeClassifier':
    """Lazy-load RegimeClassifier."""
    global regime_classifier
    if regime_classifier is None:
        regime_classifier = RegimeClassifier(storage=_get_storage())
    return regime_classifier

# Backward compatibility: expose storage at module level
def storage() -> 'StorageManager':
    """Access StorageManager instance."""
    return _get_storage()

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
            storage().update_system_state({
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
    storage().update_system_state({
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
        state = storage().get_system_state()
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

def _get_max_account_risk_pct() -> float:
    """
    Load max_account_risk_pct from StorageManager (SSOT).
    
    Returns:
        float: Max account risk percentage (default 5.0%)
    """
    settings = storage().get_risk_settings()
    return settings.get('max_account_risk_pct', 5.0)


# Backup settings utility functions have been migrated to core_brain/api/routers/system.py


# Estado para detectar cambios de régimen
_last_regime_by_symbol: Dict[str, MarketRegime] = {}

async def broadcast_thought(message: str, module: str = "CORE", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Difunde un 'pensamiento' del cerebro a todas las interfaces conectadas"""
    payload = {
        "message": message,
        "module": module,
        "level": level
    }
    if metadata:
        payload["metadata"] = metadata
        
    await _get_socket_service().emit_event("BREIN_THOUGHT", payload)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: Iniciar bucle de heartbeat y pensamientos iniciales
    system_service = _get_system_service()
    await system_service.start_heartbeat()
    await broadcast_thought("Cerebro Aethelgard inicializado. Sistema listo para operaciones.")
    
    # Migración/Semilla de configuración inicial:
    # Debe ejecutarse explícitamente vía script/manual one-shot (no automática en runtime).
    pass
        
    yield
    # Shutdown: Detener heartbeat
    await system_service.stop_heartbeat()
    logger.info("Servidor Aethelgard deteniéndose.")

    # Config loading handled by StorageManager on init
    pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aethelgard Trading System",
        description="Sistema de trading algorítmico agnóstico",
        version="1.0.0",
        lifespan=lifespan
    )

    # Inicializar orquestador con storage (Inyección de Dependencias)
    orchestrator = ConnectivityOrchestrator()
    orchestrator.set_storage(storage())

    # System endpoints have been migrated to core_brain/api/routers/system.py
    
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
        
        await _get_socket_service().connect(websocket, client_id, connector_type)
        
        # Enviar pensamiento de bienvenida para activar la consola en la UI
        await broadcast_thought(f"Enlace establecido con {client_id}. Sincronizando flujos cerebrales...", module="CORE")
        
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
                        await _get_socket_service().send_personal_message(
                            {"type": "pong", "timestamp": datetime.now().isoformat()},
                            client_id
                        )
                    else:
                        logger.warning(f"Mensaje desconocido de {client_id}: {message.get('type')}")
                
                except json.JSONDecodeError:
                    logger.error(f"JSON inválido de {client_id}: {data}")
                    await _get_socket_service().send_personal_message(
                        {"type": "error", "message": "JSON inválido"},
                        client_id
                    )
                except ValidationError as e:
                    logger.error(f"Error de validación de {client_id}: {e}")
                    await _get_socket_service().send_personal_message(
                        {"type": "error", "message": f"Error de validación: {str(e)}"},
                        client_id
                    )
                except Exception as e:
                    logger.error(f"Error procesando mensaje de {client_id}: {e}")
                    await _get_socket_service().send_personal_message(
                        {"type": "error", "message": f"Error interno: {str(e)}"},
                        client_id
                    )
        
        except WebSocketDisconnect:
            _get_socket_service().disconnect(client_id)
        except Exception as e:
            logger.error(f"Error en WebSocket {client_id}: {e}")
            _get_socket_service().disconnect(client_id)
    
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
    


    # ...existing code...

    @app.get("/api/strategies/library")
    async def get_strategies_library() -> Dict[str, Any]:
        """Retorna la biblioteca de estrategias (registradas + educativas)"""
        try:
            registered_strategies = []
            # Leer estrategias registradas desde modules.json
            # Leer estrategias registradas desde StorageManager (SSOT)
            modules = storage().get_modules_config()
            
            if modules:
                # with open(modules_path, "r", encoding="utf-8") as f:
                #     modules = json.load(f)
                
                for name, mod in modules.get("active_modules", {}).items():
                    if mod.get("type") == "strategy":
                        registered_strategies.append({
                            "name": name,
                            "description": mod.get("description", ""),
                            "enabled": mod.get("enabled", False),
                            "membership_required": mod.get("membership_required", "basic"),
                            "required_regime": mod.get("required_regime", []),
                            "timeframes": mod.get("timeframes", [])
                        })
            
            # Biblioteca educativa (hardcoded por ahora - puede venir de un archivo JSON)
            educational_library = [
                {
                    "name": "Oliver Velez 90% Sniper",
                    "category": "Trend Following",
                    "description": "Estrategia de seguimiento de tendencia con confirmación multi-timeframe",
                    "timeframes": ["M1", "M5", "M15"],
                    "regimes": ["TREND", "NORMAL"],
                    "difficulty": "Intermediate",
                    "risk_level": "Medium"
                },
                {
                    "name": "Trifecta Analyzer",
                    "category": "Multi-Timeframe Confirmation",
                    "description": "Análisis de alineación fractal en 3 timeframes con filtros de ubicación y estado estrecho",
                    "timeframes": ["M1", "M5", "M15"],
                    "regimes": ["TREND"],
                    "difficulty": "Advanced",
                    "risk_level": "Medium-High"
                }
            ]
            
            return {
                "registered": registered_strategies,
                "educational": educational_library,
                "total_registered": len(registered_strategies),
                "total_educational": len(educational_library)
            }
            
        except Exception as e:
            logger.error(f"Error loading strategies library: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/signal/{signal_id}/trace")
    async def get_signal_trace(signal_id: str) -> Dict[str, Any]:
        """Retorna la trazabilidad completa de una señal (pipeline tracking)"""
        try:
            trace = storage().get_signal_pipeline_trace(signal_id)
            
            if not trace:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No trace found for signal {signal_id}"
                )
            
            # Obtener información básica de la señal
            signals = storage().get_recent_signals(limit=1000)  # TODO: Optimizar con query directo
            signal_info = next((s for s in signals if s.get("id") == signal_id), None)
            
            return {
                "signal_id": signal_id,
                "signal_info": signal_info,
                "trace": trace,
                "stages_count": len(trace),
                "final_decision": trace[-1].get("decision") if trace else None
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting signal trace: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ============================================================
    # USER PREFERENCES & NOTIFICATIONS ENDPOINTS
    # ============================================================
    
    # Inicializar NotificationService
    from core_brain.notification_service import NotificationService
    notification_service = NotificationService(storage())
    
    @app.get("/api/user/preferences")
    async def get_user_preferences(user_id: str = 'default') -> Dict[str, Any]:
        """Obtiene las preferencias del usuario"""
        try:
            prefs = storage().get_user_preferences(user_id)
            if not prefs:
                prefs = storage().get_default_profile('active_trader')
                prefs['user_id'] = user_id
            # Wrap in preferences object for frontend compatibility
            return {"preferences": prefs}
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/user/preferences")
    async def update_user_preferences(request: Request) -> Dict[str, Any]:
        """Actualiza las preferencias del usuario"""
        try:
            body = await request.json()
            user_id = body.pop('user_id', 'default')
            preferences = body  # El resto del body son las preferences
            
            success = storage().update_user_preferences(user_id, preferences)
            if success:
                return {"success": True, "message": "Preferences updated successfully"}
            else:
                raise HTTPException(status_code=400, detail="Failed to update preferences")
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/user/profiles")
    async def get_available_profiles() -> Dict[str, Any]:
        """Retorna los perfiles disponibles"""
        profiles = {
            'explorer': storage().get_default_profile('explorer'),
            'active_trader': storage().get_default_profile('active_trader'),
            'analyst': storage().get_default_profile('analyst'),
            'scalper': storage().get_default_profile('scalper'),
            'custom': storage().get_default_profile('custom'),
        }
        return {"profiles": profiles}
    
    # Notification endpoints have been migrated to core_brain/api/routers/notifications.py
    
    # Trading endpoints have been migrated to core_brain/api/routers/trading.py
    # These endpoints are now served via:
    #   app.include_router(trading_router, prefix="/api")
    
    async def get_satellite_status() -> Any:
        """
        Returns the status of all registered connectors from ConnectivityOrchestrator.
        """
        orchestrator = ConnectivityOrchestrator()
        return orchestrator.get_status_report()

    @app.post("/api/satellite/toggle")
    async def toggle_satellite(data: Dict[str, Any]) -> Any:
        """
        Manually enable or disable a satellite connector.
        """
        provider_id = data.get("provider_id")
        enabled = data.get("enabled", True)
        
        if not provider_id:
            raise HTTPException(status_code=400, detail="provider_id is required")
        
        orchestrator = ConnectivityOrchestrator()
        if enabled:
            orchestrator.enable_connector(provider_id)
            broadcast_thought(f"[USER ACTION] Conector {provider_id} habilitado manualmente.", module="CONNECTIVITY")
        else:
            orchestrator.disable_connector(provider_id)
            broadcast_thought(f"[USER ACTION] Conector {provider_id} deshabilitado manualmente. Conmutando a proveedor de respaldo si es necesario...", module="CONNECTIVITY")
            
        return {"success": True, "provider_id": provider_id, "enabled": enabled}

    @app.get("/api/risk/status")
    async def get_risk_status() -> Dict[str, Any]:
        """
        Obtiene el estado de riesgo en tiempo real y el modo de operación.
        Se apoya puramente en la base de datos para máxima resiliencia.
        """
        try:
            # 1. Obtener stats de EdgeTuner desde la DB (SSOT)
            risk_mode = "NORMAL"
            last_adjustment = None
            
            # Intentar obtener el último ajuste de la DB (SSOT)
            adjustments = storage().get_tuning_history(limit=1)
            if adjustments:
                last_adjustment = adjustments[0]
                factor = last_adjustment.get("adjustment_factor", 1.0)
                if factor >= 1.5:
                    risk_mode = "DEFENSIVE"
                elif factor <= 0.7:
                    risk_mode = "AGGRESSIVE"
            
            # 2. Resumen de riesgos (Single Source of Truth)
            dynamic_params = {}
            state = storage().get_system_state()
            dynamic_params = state.get("config_trading", {})
            
            if not dynamic_params:
                # Fallback deshabilitado: StorageManager es la única fuente de verdad
                logger.warning("[SSOT] dynamic_params no encontrado en DB. Inicialice la configuración desde la UI/API.")

            # 3. Sanity Check Status (Rechazos recientes)
            rejections_today = 0
            last_rejection_reason = None
            
            try:
                pipeline_events = storage().get_signal_pipeline_history(limit=50)
                today = datetime.now().date()
                for event in pipeline_events:
                    event_time = event.get('timestamp')
                    if isinstance(event_time, str):
                        event_time = datetime.fromisoformat(event_time.replace(' ', 'T')).date()
                    
                    if event_time == today and event.get('decision') == 'REJECTED':
                        rejections_today += 1
                        if not last_rejection_reason:
                            last_rejection_reason = event.get('reason')
            except Exception as e:
                logger.warning(f"Error calculating sanity stats: {e}")

            return {
                "risk_mode": risk_mode,
                "current_risk_pct": dynamic_params.get("risk_per_trade", 0.01) * 100,
                "last_adjustment": last_adjustment,
                "sanity": {
                    "rejections_today": rejections_today,
                    "last_rejection_reason": last_rejection_reason,
                    "status": "HEALTHY" if rejections_today < 5 else "CAUTIOUS"
                },
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in /api/risk/status: {e}")
            return {"status": "error", "message": str(e)}

    @app.get("/api/instruments/available")
    async def get_available_instruments() -> Dict[str, Any]:
        """
        Retorna la lista de símbolos que tienen datos de mercado recientes.
        """
        try:
            # Símbolos configurados
            config = storage().get_system_config()
            configured_symbols = config.get("trading", {}).get("symbols", [])
            
            # Símbolos con estado de mercado (visto en los últimos 5 min)
            market_state = storage().get_all_market_states() or {}
            available_symbols = []
            
            for sym in configured_symbols:
                has_data = sym in market_state
                available_symbols.append({
                    "symbol": sym,
                    "has_chart": has_data,
                    "last_update": market_state.get(sym, {}).get("timestamp") if has_data else None
                })
                
            return {
                "instruments": available_symbols,
                "count": len(available_symbols),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in /api/instruments/available: {e}")
            return {"instruments": [], "error": str(e)}

    # System and Notification endpoints have been migrated to modular routers
    # (core_brain/api/routers/system.py and core_brain/api/routers/notifications.py)


    
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
                    storage().update_system_state({
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
                    
                    storage()._close_conn(conn)
            
            return {
                "positions": positions_list,
                "total_risk_usd": round(total_risk, 2),
                "count": len(positions_list)
            }
            
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return {"positions": [], "total_risk_usd": 0.0, "count": 0}
    
    @app.get("/api/edge/history")
    async def get_edge_history(limit: int = 50) -> Dict[str, Any]:
        """
        Retorna el historial unificado de aprendizaje y tunning.
        Combina:
        1. Ajustes paramétricos (vía EdgeTuner.adjust_parameters).
        2. Aprendizaje autónomo (vía EdgeTuner - Delta Feedback).
        """
        try:
            # 1. Obtener historial de tuning (legacy)
            tuning_history = storage().get_tuning_history(limit=limit)
            
            # 2. Obtener historial de aprendizaje autónomo (Edge)
            edge_history = storage().get_edge_learning_history(limit=limit)
            
            # 3. Formatear y unificar
            unified_events = []
            
            # Formatear Tuning logs (Legacy format)
            for log in tuning_history:
                # adjustment_data puede llegar como string o como dict
                ad = log['adjustment_data']
                if isinstance(ad, str):
                    try:
                        ad = json.loads(ad)
                    except Exception:
                        ad = {}
                unified_events.append({
                    "id": f"tuning_{log['id']}",
                    "timestamp": log['timestamp'],
                    "type": "PARAMETRIC_TUNING",
                    "trigger": ad.get('trigger', 'periodic'),
                    "adjustment_factor": ad.get('adjustment_factor', 1.0),
                    "old_params": ad.get('old_params', {}),
                    "new_params": ad.get('new_params', {}),
                    "stats": ad.get('stats', {}),
                    "details": "Adjustment of technical thresholds for volatility/trend."
                })
            
            # Formatear Edge logs (New Autonomous learning)
            for log in edge_history:
                details_json = {}
                if log.get('details'):
                    try:
                        details_json = json.loads(log['details'])
                    except:
                        pass
                
                unified_events.append({
                    "id": f"edge_{log['id']}",
                    "timestamp": log['timestamp'],
                    "type": "AUTONOMOUS_LEARNING",
                    "trigger": "TRADE_FEEDBACK",
                    "detection": log.get('detection'),
                    "action_taken": log.get('action_taken'),
                    "learning": log.get('learning'),
                    "delta": details_json.get('delta', 0.0),
                    "regime": details_json.get('regime', 'UNKNOWN'),
                    "adjustment_made": details_json.get('adjustment_made', False),
                    "details": log.get('learning')
                })
            
            # Ordenar por timestamp descendente
            unified_events.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return {
                "history": unified_events[:limit],
                "count": len(unified_events)
            }
        except Exception as e:
            logger.error(f"Error fetching edge history: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
            max_allowed_risk = _get_max_account_risk_pct()  # Load from risk_settings.json
            
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
            modules_enabled = storage().get_global_modules_enabled()
            
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
            storage().set_global_module_enabled(module_name, enabled)
            
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

    # System audit and tuning endpoints have been migrated to core_brain/api/routers/system.py

    # ============ Micro-ETI 2 & 2.3: Include modular routers ============
    from core_brain.api.routers.trading import router as trading_router
    from core_brain.api.routers.risk import router as risk_router
    from core_brain.api.routers.market import router as market_router
    from core_brain.api.routers.system import router as system_router
    from core_brain.api.routers.notifications import router as notifications_router
    
    # Mount modular routers (Trading, Risk, Market, System, Notifications)
    app.include_router(trading_router, prefix="/api")
    app.include_router(risk_router, prefix="/api")
    app.include_router(market_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    logger.info("✅ Micro-ETI 2.1: Routers de Trading y Riesgo montados exitosamente.")
    logger.info("✅ Micro-ETI 2.2: Router de Market Data montado exitosamente.")
    logger.info("✅ Micro-ETI 2.3: Routers de Sistema y Notificaciones montados exitosamente.")

    # Montar archivos estáticos de la nueva UI si existen
    ui_dist_path = os.path.join(os.getcwd(), "ui", "dist")
    if os.path.exists(ui_dist_path):
        app.mount("/", StaticFiles(directory=ui_dist_path, html=True), name="ui")
        logger.info(f"UI Next-Gen montada desde: {ui_dist_path}")
    else:
        logger.warning(f"No se encontró la carpeta dist de la UI en: {ui_dist_path}. Corre 'npm run build' en ui_v2.")

    return app


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
                storage().log_market_state(state_data)
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
        signal_id = storage().save_signal(signal)
        
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
        
        await _get_socket_service().send_personal_message(response, client_id)
        
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


# Lazy-load app to avoid initialization during module imports
_app_instance = None

def get_app() -> FastAPI:
    """Lazy-load FastAPI app."""
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance

# CRITICAL: Initialize app for uvicorn at module level
# This MUST be a FastAPI instance that Uvicorn can find and use
app = get_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

