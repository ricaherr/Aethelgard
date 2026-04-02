"""
Servidor FastAPI con WebSockets para Aethelgard
Gestiona múltiples conexiones simultáneas y diferencia entre conectores

Micro-ETI 3.1: Purged duplicate endpoints and extracted business logic
to TradingService. This file now only contains:
- FastAPI app factory (create_app)
- Lifespan management (startup/shutdown)
- WebSocket endpoint (delegates to TradingService)
- Router mounting
- Lazy-loading singletons
"""
import json
import logging
import asyncio
from typing import Dict, Set, Any, AsyncGenerator, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from models.signal import Signal, ConnectorType, SignalResult, MarketRegime
from core_brain.regime import RegimeClassifier
from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
from data_vault.storage import StorageManager
from core_brain.services.socket_service import get_socket_service, SocketService
from core_brain.services.system_service import get_system_service, SystemService
from fastapi.staticfiles import StaticFiles
import os
import time

# logging.basicConfig(level=logging.INFO)  # DISABLED: Let start.py configure logging
logger = logging.getLogger(__name__)

# ============ Service Instances (Lazy-loaded) ============
_socket_service_instance = None
_system_service_instance = None
_storage_instance = None  # Lazy-loaded storage
_regime_classifier_instance = None  # Lazy-loaded regime classifier
_trading_service_instance = None  # Lazy-loaded trading service
_oem_instance = None  # OperationalEdgeMonitor — set by start.py after boot
_resilience_manager_instance = None  # ResilienceManager — set by MainOrchestrator on init


def set_oem_instance(oem: "Optional[Any]") -> None:
    """Register the running OperationalEdgeMonitor instance for API access."""
    global _oem_instance
    _oem_instance = oem


def get_oem_instance() -> "Optional[Any]":
    """Return the running OperationalEdgeMonitor instance, or None if not started."""
    return _oem_instance


def set_resilience_manager(manager: "Optional[Any]") -> None:
    """Register the live ResilienceManager instance so API routes can read it."""
    global _resilience_manager_instance
    _resilience_manager_instance = manager


def get_resilience_manager() -> "Optional[Any]":
    """Return the live ResilienceManager, or None if the engine is still booting."""
    return _resilience_manager_instance

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
    global _regime_classifier_instance
    if _regime_classifier_instance is None:
        _regime_classifier_instance = RegimeClassifier(storage=_get_storage())
    return _regime_classifier_instance

def _get_trading_service() -> 'TradingService':
    """Lazy-load TradingService singleton."""
    global _trading_service_instance
    if _trading_service_instance is None:
        from core_brain.services.trading_service import TradingService
        _trading_service_instance = TradingService(
            storage=_get_storage(),
            regime_classifier=_get_regime_classifier(),
            socket_service=_get_socket_service()
        )
    return _trading_service_instance

# Backward compatibility: expose storage at module level
def storage() -> 'StorageManager':
    """Access StorageManager instance."""
    return _get_storage()


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

    # ============ CORS Middleware ============
    # CRITICAL: Allow credentials (cookies) for cross-origin requests (5173 -> 8000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,  # CRITICAL: Allow cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("[CORS] Middleware configured for localhost development")

    # Inicializar orquestador con storage (Inyección de Dependencias)
    orchestrator = ConnectivityOrchestrator()
    orchestrator.set_storage(storage())

    @app.websocket("/ws/terminal/{connector}/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, connector: str, client_id: str) -> None:
        """
        Endpoint WebSocket principal (Terminal)
        Formato: /ws/terminal/{connector}/{client_id}
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
                    
                    # Procesar señal via TradingService
                    if message.get("type") == "signal":
                        trading_service = _get_trading_service()
                        await trading_service.process_signal(message, client_id, connector_type)
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
            
            trading_service = _get_trading_service()
            await trading_service.process_signal(signal_data, client_id, connector_type)
            
            return JSONResponse(
                status_code=200,
                content={"status": "received", "message": "Señal procesada correctamente"}
            )
        
        except Exception as e:
            logger.error(f"Error procesando señal HTTP: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/test-ws")
    async def serve_websocket_test() -> HTMLResponse:
        """Serve WebSocket debug test page"""
        return HTMLResponse("""<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Debug Test</title>
    <style>
        body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 20px; }
        #logs { 
            border: 1px solid #666; 
            padding: 10px; 
            height: 400px; 
            overflow-y: auto; 
            background: #252526;
            margin: 10px 0;
        }
        .log-line { margin: 2px 0; }
        .error { color: #ce9178; }
        .success { color: #6a9955; }
        .info { color: #569cd6; }
    </style>
</head>
<body>
<h1>WebSocket Debug Test</h1>
<button onclick="testWebSocket()">Connect to /ws/shadow</button>
<button onclick="clearLogs()">Clear Logs</button>

<div id="logs"></div>

<script>
let ws = null;

function log(msg, type = 'info') {
    const logsDiv = document.getElementById('logs');
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    const timestamp = new Date().toLocaleTimeString();
    line.textContent = `[${timestamp}] ${msg}`;
    logsDiv.appendChild(line);
    logsDiv.scrollTop = logsDiv.scrollHeight;
    console.log(`[${type}] ${msg}`);
}

function clearLogs() {
    document.getElementById('logs').innerHTML = '';
}

function testWebSocket() {
    log('Starting WebSocket test...', 'info');
    const url = 'ws://localhost:8000/ws/shadow';
    log(`Attempting to connect to: ${url}`, 'info');
    
    try {
        ws = new WebSocket(url);
        
        ws.onopen = function(event) {
            log('✓ WebSocket OPEN event fired', 'success');
            log(`readyState: ${ws.readyState} (OPEN)`, 'success');
        };
        
        ws.onmessage = function(event) {
            log('✓ onmessage fired!', 'success');
            log(`Raw data: ${event.data}`, 'success');
            try {
                const msg = JSON.parse(event.data);
                log(`Parsed JSON - event_type: ${msg.event_type}`, 'success');
                log(`Full message: ${JSON.stringify(msg)}`, 'success');
            } catch (e) {
                log(`Failed to parse JSON: ${e}`, 'error');
            }
        };
        
        ws.onerror = function(event) {
            log(`✗ WebSocket ERROR: ${event.type}`, 'error');
            log(`readyState: ${ws.readyState}`, 'error');
        };
        
        ws.onclose = function(event) {
            log(`✗ WebSocket CLOSE event fired`, 'error');
            log(`Code: ${event.code}, Reason: ${event.reason}`, 'error');
            log(`readyState: ${ws.readyState} (CLOSED)`, 'error');
            log(`wasClean: ${event.wasClean}`, 'error');
        };
        
        log('WebSocket object created, waiting for onopen...', 'info');
        
    } catch (error) {
        log(`Error creating WebSocket: ${error.message}`, 'error');
    }
}

window.addEventListener('load', function() {
    log('Page loaded. Click "Connect" button to test.', 'info');
});
</script>
</body>
</html>""")

    # ============ Micro-ETI 2 & 3: Include modular routers ============
    from core_brain.api.routers.trading import router as trading_router
    from core_brain.api.routers.risk import router as risk_router
    from core_brain.api.routers.market import router as market_router
    from core_brain.api.routers.system import router as system_router
    from core_brain.api.routers.notifications import router as notifications_router
    from core_brain.api.routers.auth import router as auth_router
    from core_brain.api.routers.admin import router as admin_router
    from core_brain.api.routers.anomalies import router as anomalies_router
    from core_brain.api.routers.strategy_ws import router as strategy_ws_router
    from core_brain.api.routers.telemetry import router as telemetry_router
    from core_brain.api.routers.shadow import router as shadow_router
    from core_brain.api.routers.shadow_ws import router as shadow_ws_router
    from core_brain.api.routers.resilience import router as resilience_router

    # Mount modular routers (Trading, Risk, Market, System, Notifications, Auth, Admin, Anomalies, Strategy WS, Telemetry, SHADOW, Resilience)
    app.include_router(trading_router, prefix="/api")
    app.include_router(risk_router, prefix="/api")
    app.include_router(market_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(shadow_router, prefix="/api")  # SHADOW REST endpoints
    app.include_router(resilience_router, prefix="/api")  # Resilience Control (HU 10.17b)
    app.include_router(anomalies_router)
    app.include_router(strategy_ws_router)  # WebSocket doesn't need /api prefix
    app.include_router(telemetry_router)  # WebSocket doesn't need /api prefix (Fractal V3)
    app.include_router(shadow_ws_router)  # WebSocket doesn't need /api prefix (SHADOW)
    logger.info("[OK] Micro-ETI 3.1+ Admin Management Router: User CRUD endpoints mounted (/api/admin/users). Trading logic delegated to TradingService.")

    # Montar archivos estáticos de la nueva UI si existen
    ui_dist_path = os.path.join(os.getcwd(), "ui", "dist")
    if os.path.exists(ui_dist_path):
        app.mount("/", StaticFiles(directory=ui_dist_path, html=True), name="ui")
        logger.info(f"UI Next-Gen montada desde: {ui_dist_path}")
    else:
        logger.warning(f"No se encontró la carpeta dist de la UI en: {ui_dist_path}. Corre 'npm run build' en ui_v2.")

    return app


# Lazy-load app to avoid initialization during module imports
_app_instance = None

def get_app() -> FastAPI:
    """Lazy-load FastAPI app."""
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance

# CRITICAL: For uvicorn compatibility, provide 'app' at module level
# BUT: Avoid initialization during pytest imports via environment check
import os
import sys

# Check if we're in pytest context
_is_testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None

if not _is_testing:
    # Production/development mode: initialize app immediately for uvicorn
    app = get_app()
else:
    # Test mode: delay initialization to prevent DB contention during conftest
    # The app will be created on first access via get_app()
    class LazyApp:
        """Lazy proxy for FastAPI app (for test compatibility)."""
        def __getattr__(self, name: str) -> Any:
            return getattr(get_app(), name)

    app = LazyApp()  # type: ignore

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(get_app(), host="0.0.0.0", port=8000)
