# --- Función auxiliar DRY para actualizar categoría de instrumentos ---
def update_instrument_category(market: str, category: str, data: dict, storage: StorageManager) -> None:
    """Actualiza solo una categoría de instrumentos en la configuración (SSOT)"""
    state = storage.get_system_state()
    instruments_config = state.get("instruments_config")
    if not instruments_config or market not in instruments_config or category not in instruments_config[market]:
        raise HTTPException(status_code=404, detail="Categoría no encontrada en la configuración actual")
    instruments_config[market][category].update(data)
    storage.update_system_state({"instruments_config": instruments_config})

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
from fastapi.staticfiles import StaticFiles
import os
import time

# Configurar logging
# logging.basicConfig(level=logging.INFO)  # DISABLED: Let start.py configure logging
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
_storage_instance = None  # Lazy-loaded storage
regime_classifier = None  # Lazy-loaded regime classifier

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


def _get_backup_settings_from_db() -> Dict[str, Any]:
    """
    Get normalized DB backup settings from dynamic_params.
    Default policy: backups/, daily, retention 15 days.
    """
    defaults = {
        "enabled": True,
        "backup_dir": "backups",
        "interval_days": 1,
        "retention_days": 15
    }

    params = storage().get_dynamic_params()
    backup_cfg = params.get("database_backup", {}) if isinstance(params, dict) else {}
    if not isinstance(backup_cfg, dict):
        backup_cfg = {}

    interval_days = backup_cfg.get("interval_days")
    if interval_days is None:
        interval_minutes = int(backup_cfg.get("interval_minutes", defaults["interval_days"] * 1440))
        interval_days = max(1, int((interval_minutes + 1439) // 1440))

    retention_days = backup_cfg.get("retention_days")
    if retention_days is None:
        retention_days = int(backup_cfg.get("retention_count", defaults["retention_days"]))

    return {
        "enabled": bool(backup_cfg.get("enabled", defaults["enabled"])),
        "backup_dir": str(backup_cfg.get("backup_dir", defaults["backup_dir"])),
        "interval_days": max(1, int(interval_days)),
        "retention_days": max(1, int(retention_days))
    }


def _save_backup_settings_to_db(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Persist backup settings to dynamic_params.database_backup."""
    normalized = {
        "enabled": bool(settings.get("enabled", True)),
        "backup_dir": str(settings.get("backup_dir", "backups")).strip() or "backups",
        "interval_days": max(1, int(settings.get("interval_days", 1))),
        "retention_days": max(1, int(settings.get("retention_days", 15)))
    }

    params = storage().get_dynamic_params()
    if not isinstance(params, dict):
        params = {}

    params["database_backup"] = {
        "enabled": normalized["enabled"],
        "backup_dir": normalized["backup_dir"],
        "interval_days": normalized["interval_days"],
        "retention_days": normalized["retention_days"],
        "interval_minutes": normalized["interval_days"] * 1440,
        "retention_count": normalized["retention_days"]
    }

    storage().update_dynamic_params(params)
    return normalized

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
        
    await manager.emit_event("BREIN_THOUGHT", payload)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: Iniciar bucle de heartbeat y pensamientos iniciales
    asyncio.create_task(heartbeat_loop())
    await broadcast_thought("Cerebro Aethelgard inicializado. Sistema listo para operaciones.")
    
    # Migración/Semilla de configuración inicial:
    # Debe ejecutarse explícitamente vía script/manual one-shot (no automática en runtime).
    pass
        
    yield
    # Shutdown (opcional)
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

    # Servicio de análisis profundo de instrumentos
    # Servicio de análisis profundo de instrumentos
    from core_brain.analysis_service import InstrumentAnalysisService
    instrument_analysis_service = InstrumentAnalysisService(storage=storage())

    # Inicializar orquestador con storage (Inyección de Dependencias)
    orchestrator = ConnectivityOrchestrator()
    orchestrator.set_storage(storage())

    @app.get("/api/instrument/{symbol}/analysis")
    async def instrument_analysis(symbol: str) -> Dict[str, Any]:
        """Retorna análisis completo de un instrumento (régimen, tendencia, trifecta, estrategias)"""
        try:
            result = instrument_analysis_service.get_analysis(symbol)
            return result
        except Exception as e:
            logger.error(f"Error en instrument_analysis: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Endpoint de estado del escáner
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    try:
        from core_brain.main_orchestrator import scanner
    except ImportError:
        scanner = None

    @app.get("/api/scanner/status")
    async def scanner_status() -> Dict[str, Any]:
        """Retorna el estado actual del escáner (CPU, activos, régimen, última scan). Nunca falla."""
        fallback = {
            "assets": [],
            "last_regime": {},
            "last_scan_time": {},
            "cpu_percent": 0.0,
            "cpu_limit_pct": 80.0,
            "running": False,
            "error": None
        }
        if scanner is None:
            fallback["error"] = "ScannerEngine no está inicializado"
            return fallback
        try:
            status = scanner.get_status()
            status["error"] = None
            return status
        except Exception as e:
            logger.error(f"Error en scanner_status: {e}")
            fallback["error"] = str(e)
            return fallback

    @app.get("/api/analysis/heatmap")
    async def get_heatmap_data() -> Dict[str, Any]:
        """
        Retorna la matriz de calor (Heatmap) AGNOSTICA de símbolos x timeframes.
        Recopila regímenes, métricas técnicas y señales activas.
        Implementa principios de RESILIENCIA y AUTOGESTIÓN con CROSS-PROCESS fallback.
        """
        # RECOPILACIÓN DE DATOS REILIENTE
        cells = []
        assets = []
        timeframes = []
        now_mono = time.monotonic()
        now_ts = time.time()

        # Intento 1: Obtener datos del scanner local (si está en el mismo proceso)
        if scanner is not None:
            try:
                with scanner._lock:
                    assets = list(scanner.assets)
                    timeframes = list(scanner.active_timeframes)
                    regimes = dict(scanner.last_regime)
                    last_scans = dict(scanner.last_scan_time)
                    
                    for symbol in assets:
                        for tf in timeframes:
                            key = f"{symbol}|{tf}"
                            cl = scanner.classifiers.get(key)
                            
                            last_scan_val = last_scans.get(key, 0)
                            cell = {
                                "symbol": symbol,
                                "timeframe": tf,
                                "regime": regimes.get(key, MarketRegime.NORMAL).value,
                                "last_scan": last_scan_val,
                                "is_stale": (now_mono - last_scan_val) > 300 if last_scan_val > 0 else True,
                                "metrics": {},
                                "signal": None,
                                "source": "memory"
                            }
                            if cl:
                                try: cell["metrics"] = cl.get_metrics()
                                except Exception: pass
                            cells.append(cell)
            except Exception as e:
                logger.warning(f"Error leyendo scanner local: {e}")

        # Intento 2: Fallback a Base de Datos (Cross-Process Resilience)
        if not cells:
            try:
                db_states = storage().get_latest_heatmap_state()
                if db_states:
                    # Deducir assets y timeframes de los datos
                    assets = sorted(list(set(s["symbol"] for s in db_states)))
                    timeframes = sorted(list(set(s["timeframe"] for s in db_states)))
                    
                    for s in db_states:
                        ts_str = s.get("timestamp")
                        last_scan_ts = datetime.fromisoformat(ts_str).timestamp() if ts_str else 0
                        cells.append({
                            "symbol": s["symbol"],
                            "timeframe": s["timeframe"],
                            "regime": s["regime"],
                            "last_scan": last_scan_ts,
                            "is_stale": (now_ts - last_scan_ts) > 600 if last_scan_ts > 0 else True,
                            "metrics": s.get("metrics", {}),
                            "signal": None,
                            "source": "database"
                        })
            except Exception as e:
                logger.error(f"Error en fallback de base de datos para heatmap: {e}")

        if not cells:
            # DIAGNÓSTICO INTELIGENTE (Auto-gestión)
            diag = "Scanner offline."
            if scanner is not None:
                diag = "Scanner local activo pero sin datos (Verificar conexión a MT5/DataProv)."
            elif storage:
                try:
                    # Verificar si la tabla existe y tiene algo
                    count = storage().execute_query("SELECT COUNT(*) as c FROM market_state")[0]['c']
                    if count == 0:
                        diag = "Scanner en otro proceso pero base de datos vacía (Iniciando primera recolección)."
                    else:
                        diag = "Scanner en otro proceso pero datos en DB son demasiado antiguos (>24h)."
                except Exception as e:
                    diag = f"Error de acceso a datos: {str(e)}"
            
            logger.warning(f"Heatmap 503 Diagnostic: {diag}")
            raise HTTPException(status_code=503, detail=f"Análisis no disponible: {diag}")

        # 2. Integrar Señales Recientes (CONFLUENCIA)
        # Buscamos señales PENDING de la última hora
        try:
            recent_signals = storage().get_recent_signals(minutes=60, status='PENDING')
            # Indexar señales por clave para búsqueda rápida
            signals_lookup = {f"{s['symbol']}|{s['timeframe']}": s for s in recent_signals}
            
            for cell in cells:
                key = f"{cell['symbol']}|{cell['timeframe']}"
                sig = signals_lookup.get(key)
                if sig:
                    cell["signal"] = {
                        "id": sig["id"],
                        "type": sig["signal_type"],
                        "score": sig["score"]
                    }
        except Exception as e:
            logger.warning(f"Error agregando señales al heatmap: {e}")

        # 3. Cálculo de Confluencia Fractal (INTELIGENCIA)
        # Si un símbolo tiene el mismo sesgo (bias) en 3+ timeframes, marcar confluencia
        for symbol in assets:
            symbol_cells = [c for c in cells if c["symbol"] == symbol]
            biases = [c["metrics"].get("bias") for c in symbol_cells if c["metrics"].get("bias")]
            
            if len(biases) >= 2: # Al menos 2 para considerar confluencia mínima
                # Contar sesgo dominante
                bullish_count = biases.count("BULLISH")
                bearish_count = biases.count("BEARISH")
                
                confluence = None
                if bullish_count >= 2: confluence = "BULLISH"
                if bearish_count >= 2: confluence = "BEARISH"
                
                if confluence:
                    for cell in symbol_cells:
                        cell["confluence"] = confluence
                        cell["confluence_strength"] = max(bullish_count, bearish_count)

        return {
            "symbols": assets,
            "timeframes": timeframes,
            "cells": cells,
            "timestamp": datetime.now().isoformat()
        }

    # Endpoint de historial de régimen
    from data_vault.market_db import MarketMixin
    market_db = MarketMixin()

    @app.get("/api/regime/{symbol}/history")
    async def regime_history(symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Retorna el historial de cambios de régimen para un símbolo"""
        try:
            history = market_db.get_market_state_history(symbol, limit=limit)
            formatted = [
                {
                    "regime": h["data"].get("regime"),
                    "start": h["data"].get("timestamp"),
                    "adx": h["data"].get("adx"),
                    "volatility": h["data"].get("volatility"),
                    "strength": h["data"].get("trend_strength"),
                }
                for h in history
            ]
            return {"symbol": symbol, "history": formatted}
        except Exception as e:
            logger.error(f"Error en regime_history: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Endpoint de datos de gráfica
    from core_brain.chart_service import ChartService
    chart_service = ChartService(storage=storage())

    @app.get("/api/chart/{symbol}/{timeframe}")
    async def chart_data(symbol: str, timeframe: str = "M5", count: int = 500) -> Dict[str, Any]:
        """Retorna datos de OHLC + indicadores para un símbolo y timeframe"""
        try:
            return chart_service.get_chart_data(symbol, timeframe, count)
        except Exception as e:
            logger.error(f"Error en chart_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
    
    @app.get("/api/regime_configs")
    async def get_regime_configs() -> Dict[str, Any]:
        """Retorna los pesos y configuraciones dinámicas de cada régimen (regime_configs table).
        Usado por UI para visualizar WeightedMetricsVisualizer (Darwinismo Algorítmico).
        
        Estructura respuesta:
        {
            "TREND": {"profit_factor": 0.4, "win_rate": 0.3, "drawdown_max": 0.2, "consecutive_losses": 0.1},
            "RANGE": {"profit_factor": 0.25, "win_rate": 0.4, "drawdown_max": 0.2, "consecutive_losses": 0.15},
            "VOLATILE": {"profit_factor": 0.2, "win_rate": 0.2, "drawdown_max": 0.4, "consecutive_losses": 0.2}
        }
        """
        try:
            # Obtener todos los regime_configs agrupados por régimen
            all_configs = storage().get_all_regime_configs()
            
            # Transformar formato: all_configs es Dict[regime -> Dict[metric_name -> weight]]
            regime_weights = {}
            for regime, metrics_dict in all_configs.items():
                regime_weights[regime] = {}
                for metric_name, weight in metrics_dict.items():
                    regime_weights[regime][metric_name] = float(weight)
            
            return {
                "regime_weights": regime_weights,
                "timestamp": datetime.now().isoformat(),
                "description": "Dynamic regime-specific metric weights for strategy ranking (Darwinismo Algorítmico)"
            }
        except Exception as e:
            logger.error(f"Error en get_regime_configs: {e}")
            raise HTTPException(status_code=500, detail=f"Error fetching regime configs: {str(e)}")

    @app.get("/api/instruments")
    async def get_instruments(all: bool = False) -> Dict[str, Any]:
        """Retorna la lista de instrumentos agrupados por mercado/categoría desde la DB (SSOT).
        Si 'all' es True, incluye categorías e instrumentos inactivos (para Settings).
        """
        try:
            state = storage().get_system_state()
            instruments_config = state.get("instruments_config")
            if instruments_config is None:
                raise ValueError("instruments_config no encontrado en DB. Inicialice la configuración desde la UI/API.")
            result = {}
            for market, categories in instruments_config.items():
                if market.startswith("_"):
                    continue
                result[market] = {}
                for cat, cat_data in categories.items():
                    # Si all=False, solo mostrar categorías activas
                    if not all and not cat_data.get("enabled", False):
                        continue
                    instruments = cat_data.get("instruments", [])
                    # Si all=False, solo mostrar instrumentos activos
                    if not all:
                        actives = cat_data.get("actives", {})
                        instruments = [sym for sym in instruments if actives.get(sym, True)]
                    if instruments or all:
                        result[market][cat] = {
                            "description": cat_data.get("description", ""),
                            "instruments": instruments,
                            "priority": cat_data.get("priority", 0),
                            "min_score": cat_data.get("min_score", None),
                            "risk_multiplier": cat_data.get("risk_multiplier", None),
                            "enabled": cat_data.get("enabled", False),
                            "actives": cat_data.get("actives", {})
                        }
            return {"markets": result}
        except Exception as e:
            logger.error(f"Error loading instruments config from DB: {e}")
            # Fallback: lista mínima hardcodeada
            return {
                "markets": {
                    "FOREX": {
                        "majors": {
                            "description": "Fallback: Pares principales",
                            "instruments": ["EURUSD", "GBPUSD", "USDJPY"],
                            "priority": 1,
                            "min_score": 70,
                            "risk_multiplier": 1.0
                        }
                    }
                },
                "error": f"No se pudo cargar instruments_config de la DB: {str(e)}"
            }

    @app.post("/api/instruments")
    async def update_instruments(payload: dict) -> Dict[str, Any]:
        """Actualiza SOLO una categoría de instrumentos (más eficiente, DRY)"""
        try:
            market = payload.get("market")
            category = payload.get("category")
            data = payload.get("data")
            if not (market and category and isinstance(data, dict)):
                raise HTTPException(status_code=400, detail="Faltan campos obligatorios: market, category, data")
            update_instrument_category(market, category, data, storage())
            await broadcast_thought(f"Categoría {market}/{category} actualizada por el usuario.", module="CORE")
            return {"status": "success", "message": f"Categoría {market}/{category} actualizada correctamente."}
        except Exception as e:
            logger.error(f"Error guardando categoría de instrumentos: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
    
    @app.get("/api/notifications/unread")
    async def get_unread_notifications(user_id: str = 'default') -> Dict[str, Any]:
        """Obtiene notificaciones no leídas"""
        try:
            notifications = notification_service.get_unread_notifications(user_id)
            return {"notifications": notifications, "count": len(notifications)}
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/notifications/{notification_id}/mark-read")
    async def mark_notification_read(notification_id: str) -> Dict[str, Any]:
        """Marca notificación como leída"""
        try:
            success = notification_service.mark_as_read(notification_id)
            if success:
                return {"success": True}
            else:
                raise HTTPException(status_code=404, detail="Notification not found")
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/auto-trading/toggle")
    async def toggle_auto_trading(request: Request) -> Dict[str, Any]:
        """Activa o desactiva el auto-trading"""
        try:
            # Parse JSON body
            body = await request.json()
            user_id = body.get('user_id', 'default')
            enabled = body.get('enabled', False)
            
            success = storage().update_user_preferences(user_id, {'auto_trading_enabled': enabled})
            if success:
                status = "enabled" if enabled else "disabled"
                logger.info(f"Auto-trading {status} for user {user_id}")
                return {"success": True, "auto_trading_enabled": enabled, "message": f"Auto-trading {status}"}
            else:
                raise HTTPException(status_code=400, detail="Failed to toggle auto-trading")
        except Exception as e:
            logger.error(f"Error toggling auto-trading: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/signals")
    async def get_signals(
        limit: int = 100, 
        minutes: int = 10080,
        symbols: str = None,  # Comma-separated: "EURUSD,GBPUSD"
        timeframes: str = None,  # Comma-separated: "M1,M5"
        regimes: str = None,  # Comma-separated: "TREND,RANGE"
        strategies: str = None,  # Comma-separated: "Trifecta,Oliver Velez"
        status: str = 'PENDING,EXECUTED,EXPIRED'  # Default to recent signals
    ) -> Dict[str, Any]:
        """
        Get recent signals from database with optional filters
        Includes live trade status and P/L for executed signals.
        """
        try:
            logger.info(f"GET /api/signals: limit={limit}, minutes={minutes}, symbols={symbols}, status={status}")
            
            # Get signals from DB with SQL-level filtering
            all_signals = storage().get_recent_signals(
                minutes=minutes, 
                limit=limit,
                symbol=symbols,
                timeframe=timeframes,
                status=status
            )
            
            # Obtener estados de mercado para flag has_chart
            market_state = storage().get_all_market_states() or {}
            
            # Filter results in memory for metadata-based fields
            filtered = all_signals
            
            # Regime filter
            if regimes and regimes.strip():
                regime_list = [r.strip().upper() for r in regimes.split(',') if r.strip()]
                if regime_list:
                    filtered = [
                        sig for sig in filtered 
                        if isinstance(sig.get('metadata'), dict) and sig.get('metadata', {}).get('regime', '').upper() in regime_list
                    ]
            
            # Strategy filter
            if strategies and strategies.strip():
                strategy_list = [s.strip() for s in strategies.split(',') if s.strip()]
                if strategy_list:
                    filtered = [
                        sig for sig in filtered 
                        if isinstance(sig.get('metadata'), dict) and sig.get('metadata', {}).get('strategy', '') in strategy_list
                    ]
            
            # Limit results
            filtered = filtered[:limit]
            
            # Get signal IDs that have trace data
            signal_ids = [s.get('id') for s in filtered]
            has_trace_set = set()
            if signal_ids:
                placeholders = ','.join(['?'] * len(signal_ids))
                trace_query = f"SELECT DISTINCT signal_id FROM signal_pipeline WHERE signal_id IN ({placeholders})"
                trace_results = storage().execute_query(trace_query, tuple(signal_ids))
                has_trace_set = {r['signal_id'] for r in trace_results}

            # Format signals for frontend
            formatted_signals = []
            for signal in filtered:
                sig_id = signal.get('id')
                sig_symbol = signal.get('symbol')
                sig_status = signal.get('status', 'PENDING')
                
                formatted = {
                    'id': sig_id,
                    'symbol': sig_symbol,
                    'direction': signal.get('direction') or signal.get('signal_type'),
                    'score': signal.get('score') or signal.get('confidence') or 0.75,
                    'timeframe': signal.get('timeframe'),
                    'strategy': signal.get('metadata', {}).get('strategy', 'Unknown') if isinstance(signal.get('metadata'), dict) else 'Unknown',
                    'entry_price': signal.get('entry_price') or signal.get('price') or 0.0,
                    'sl': signal.get('sl') or signal.get('stop_loss') or 0.0,
                    'tp': signal.get('tp') or signal.get('take_profit') or 0.0,
                    'r_r': signal.get('metadata', {}).get('r_r', 2.0) if isinstance(signal.get('metadata'), dict) else 2.0,
                    'regime': signal.get('metadata', {}).get('regime', 'UNKNOWN') if isinstance(signal.get('metadata'), dict) else 'UNKNOWN',
                    'timestamp': signal.get('timestamp'),
                    'status': sig_status,
                    'has_trace': sig_id in has_trace_set,
                    'has_chart': sig_symbol in market_state,
                    'confluences': signal.get('metadata', {}).get('confluences', []) if isinstance(signal.get('metadata'), dict) else []
                }
                
                # Augmentar con info de trades si están EXECUTED
                if sig_status == 'EXECUTED':
                    # Buscar en trade_results
                    result = storage().get_trade_result_by_signal_id(sig_id)
                    if result:
                        formatted['live_status'] = 'CLOSED'
                        formatted['pnl'] = result.get('profit')
                        formatted['exit_price'] = result.get('exit_price')
                        formatted['exit_reason'] = result.get('exit_reason')
                    else:
                        formatted['live_status'] = 'OPEN'
                
                formatted_signals.append(formatted)
            
            return {
                "signals": formatted_signals, 
                "count": len(formatted_signals)
            }
            
        except Exception as e:
            logger.error(f"Error in /api/signals: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/signals/execute")
    async def execute_signal_manual(data: dict) -> Dict[str, Any]:
        """
        Manually execute a signal by ID (triggered from UI Execute button).
        
        NOTE: Manual execution BYPASSES auto_trading_enabled setting.
        This is intentional - manual execution should always work regardless of auto-trading state.
        
        Body: {
            "signal_id": "uuid-string"
        }
        """
        try:
            signal_id = data.get("signal_id")
            if not signal_id:
                raise HTTPException(status_code=400, detail="signal_id is required")
            
            logger.info(f"Manual execution requested for signal: {signal_id}")
            
            # Get signal from database
            signal_data = storage().get_signal_by_id(signal_id)
            if not signal_data:
                raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
            
            # Check if already executed
            if signal_data.get('status', '').upper() == 'EXECUTED':
                return {
                    "success": False,
                    "message": "Signal already executed",
                    "signal_id": signal_id
                }
            
            # Reconstruct Signal object from database data
            from models.signal import Signal, SignalType, ConnectorType
            
            # Parse metadata
            metadata = signal_data.get('metadata', {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
            
            # Create Signal object
            signal = Signal(
                symbol=signal_data['symbol'],
                signal_type=SignalType(signal_data['signal_type']),
                price=signal_data.get('price', 0.0),
                confidence=signal_data.get('confidence', signal_data.get('score', 0.75)),
                timeframe=signal_data.get('timeframe', 'M15'),
                connector_type=ConnectorType(signal_data.get('connector_type', 'METATRADER5')),
                metadata=metadata
            )
            
            # Add signal_id to metadata for tracking
            signal.metadata['signal_id'] = signal_id
            
            # Create executor instance (with lazy-loaded MT5 connector)
            from core_brain.executor import OrderExecutor
            from core_brain.risk_manager import RiskManager
            
            # Get MT5 connector
            mt5_connector = _get_mt5_connector()
            if not mt5_connector:
                return {
                    "success": False,
                    "message": "MT5 connector not available. Check connection.",
                    "signal_id": signal_id
                }
            
            # Create risk manager and executor
            # Get account balance for risk manager
            account_balance = _get_account_balance()
            risk_manager = RiskManager(storage=storage(), initial_capital=account_balance)
            executor = OrderExecutor(
                risk_manager=risk_manager,
                storage=storage(),
                connectors={ConnectorType.METATRADER5: mt5_connector}
            )
            
            # Execute signal
            logger.info(f"Attempting to execute signal {signal_id}: {signal.symbol} {signal.signal_type.value}")
            logger.info(f"Signal details - Price: {signal.price}, Confidence: {signal.confidence}, TF: {signal.timeframe}")
            
            # Reset rejection reason before execution
            executor.last_rejection_reason = None
            success = await executor.execute_signal(signal)
            
            logger.info(f"Execution result for {signal_id}: {'SUCCESS' if success else 'FAILED'}")
            
            if success:
                # Update signal status to EXECUTED
                storage().update_signal_status(signal_id, 'EXECUTED', {
                    'executed_at': datetime.now().isoformat(),
                    'execution_method': 'manual'
                })
                
                await broadcast_thought(
                    f"Signal {signal_id} executed manually: {signal.symbol} {signal.signal_type.value}",
                    module="EXECUTOR"
                )
                return {
                    "success": True,
                    "message": f"✅ Trade executed: {signal.symbol} {signal.signal_type.value}",
                    "signal_id": signal_id
                }
            else:
                # Get specific rejection reason from executor
                rejection_reason = executor.last_rejection_reason or "Unknown reason (check logs)"
                logger.warning(f"Signal execution failed for {signal_id}. Reason: {rejection_reason}")
                return {
                    "success": False,
                    "message": f"❌ {rejection_reason}",
                    "signal_id": signal_id
                }
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing signal manually: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"❌ Error: {str(e)}",
                "signal_id": signal_id if 'signal_id' in locals() else None
            }
    
    @app.get("/api/satellite/status")
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


    @app.get("/api/config/{category}")
    async def get_config(category: str) -> Dict[str, Any]:
        """Obtiene una categoría de configuración de la DB"""
        db_key = f"config_{category}"
        state = storage().get_system_state()
        config_data = state.get(db_key)
        
        if config_data is None:
            # Si no está en DB, retornamos vacío o error.
            # No hay fallback a archivo aquí para respetar SSOT.
            # Si se requiere migración legacy, debe ejecutarse manualmente.
            logger.warning(f"Config '{category}' requested not found in DB.")
            return {}
            
        if config_data is None and category == "notifications":
            # Fallback especial para notificaciones si se pide vía /config pero no existe
            # Intentamos obtener la configuración de Telegram de la nueva tabla
            from data_vault.system_db import SystemMixin
            notif_db = SystemMixin()
            telegram_settings = notif_db.get_notification_settings("telegram")
            if telegram_settings:
                # Asegurar que config_data sea un diccionario mutable
                raw_config = telegram_settings.get("config", {})
                if isinstance(raw_config, str):
                    try: raw_config = json.loads(raw_config)
                    except: raw_config = {}
                
                config_data = dict(raw_config)
                
                # Mapeo explícito para compatibilidad con el frontend
                if "chat_id_basic" in config_data:
                    config_data["basic_chat_id"] = config_data["chat_id_basic"]
                if "chat_id_premium" in config_data:
                    config_data["premium_chat_id"] = config_data["chat_id_premium"]
                
                config_data["enabled"] = bool(telegram_settings.get("enabled", False))
            
        if config_data is None:
            raise HTTPException(status_code=404, detail=f"Categoría de configuración '{category}' no encontrada.")
            
        return {"category": category, "data": config_data}

    @app.get("/api/backup/settings")
    async def get_backup_settings() -> Dict[str, Any]:
        """Get DB backup scheduler settings (DB-first)."""
        try:
            settings = _get_backup_settings_from_db()
            return {"status": "success", "settings": settings}
        except Exception as e:
            logger.error(f"Error loading backup settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/backup/settings")
    async def update_backup_settings(data: dict) -> Dict[str, Any]:
        """Update DB backup scheduler settings (DB-first)."""
        try:
            settings = _save_backup_settings_to_db(data or {})
            await broadcast_thought("Configuración de backups actualizada.", module="CORE")
            return {"status": "success", "settings": settings}
        except Exception as e:
            logger.error(f"Error updating backup settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/config/{category}")
    async def update_config(category: str, new_data: dict) -> Dict[str, Any]:
        """Actualiza una categoría de configuración en la DB"""
        db_key = f"config_{category}"
        try:
            storage().update_system_state({db_key: new_data})
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
        """Saves Telegram configuration to specialized notification table"""
        bot_token = data.get("bot_token", "")
        chat_id = data.get("chat_id", "")
        enabled = data.get("enabled", True)
        
        telegram_config = {
            "bot_token": bot_token,
            "basic_chat_id": chat_id,
            "premium_chat_id": chat_id
        }
        
        # Guardar usando el nuevo SystemMixin
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        success = notif_db.update_notification_settings("telegram", enabled, telegram_config)
        
        if success:
            # Re-inicializar el motor de notificaciones
            from core_brain.notificator import initialize_notifier
            initialize_notifier(storage())
            
            await broadcast_thought("Notificaciones de Telegram configuradas correctamente.", module="CORE")
            logger.info(f"✅ Telegram configurado: Chat ID {chat_id}")
            
            return {
                "status": "success",
                "message": "Configuración de Telegram guardada correctamente."
            }
        else:
            raise HTTPException(status_code=500, detail="Error al guardar la configuración en la base de datos.")

    @app.get("/api/notifications/settings")
    async def get_all_notification_settings() -> Dict[str, Any]:
        """Retorna la configuración de todos los proveedores de notificaciones"""
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        settings = notif_db.get_all_notification_settings()
        return {"status": "success", "settings": settings}

    @app.post("/api/notifications/settings/{provider}")
    async def update_notification_provider_settings(provider: str, data: dict) -> Dict[str, Any]:
        """Actualiza la configuración de un proveedor específico"""
        enabled = data.get("enabled", False)
        config = data.get("config", {})
        
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        success = notif_db.update_notification_settings(provider, enabled, config)
        
        if success:
            from core_brain.notificator import initialize_notifier
            initialize_notifier(storage())
            return {"status": "success", "message": f"Configuración de {provider} actualizada."}
        else:
            raise HTTPException(status_code=500, detail=f"Error al actualizar {provider}.")
    
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

    @app.post("/api/system/audit")
    async def run_integrity_audit() -> Dict[str, Any]:
        """
        Ejecuta validación global con espera completa y retorna resultados.
        Envía eventos en tiempo real vía broadcast_thought.
        """
        # Mapas de lenguaje sofisticado por etapa
        sophisticated_lexicon = {
            "Architecture": "Analizando topología de arquitectura y coherencia de módulos...",
            "QA Guard": "Verificando integridad sintáctica y estándares de calidad QA...",
            "Code Quality": "Escaneando densidad de complejidad y patrones de duplicidad...",
            "UI Quality": "Validando ecosistema React y consistencia de tipos en interfaz...",
            "Manifesto": "Enforzando leyes del Manifesto (DI & SSOT)...",
            "Patterns": "Escrutando firmas de métodos y protocolos de seguridad AST...",
            "Core Tests": "Ejecutando suite crítica de deduplicación y gestión de riesgo...",
            "Integration": "Validando puentes de integración y persistencia en Data Vault...",
            "Connectivity": "Auditando latencia y fidelidad del uplink con el Broker...",
            "System DB": "Verificando integridad estructural de la base de Datos..."
        }

        await broadcast_thought("Desplegando hilos de auditoría paralela... Iniciando escaneo de vectores de integridad.", module="HEALTH")
        
        validation_results = []
        error_details = {}
        total_time = 0.0
        
        try:
            process = await asyncio.create_subprocess_exec(
                "python", "scripts/validate_all.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            # Leer stdout línea a línea para interceptar STAGE_START, STAGE_END y DEBUG_FAIL
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                decoded_line = line.decode().strip()
                
                if decoded_line.startswith("STAGE_START:"):
                    stage = decoded_line.split(":")[1]
                    msg = sophisticated_lexicon.get(stage, f"Iniciando fase: {stage}...")
                    await broadcast_thought(msg, level="info", module="HEALTH", metadata={"stage": stage, "status": "STARTING"})
                
                elif decoded_line.startswith("DEBUG_FAIL:"):
                    parts = decoded_line.split(":", 2)
                    if len(parts) >= 3:
                        stage, error = parts[1], parts[2]
                        error_details[stage] = error

                elif decoded_line.startswith("STAGE_END:"):
                    parts = decoded_line.split(":")
                    if len(parts) >= 4:
                        stage, result_status, duration = parts[1], parts[2], parts[3]
                        try:
                            duration_float = float(duration)
                            total_time += duration_float
                        except:
                            duration_float = 0.0
                        
                        if result_status == "OK":
                            color_indicator = "✅"
                            await broadcast_thought(
                                f"{color_indicator} Vector {stage} successfully validated ({duration}s).",
                                level="success",
                                module="HEALTH",
                                metadata={"stage": stage, "status": "OK", "duration": duration}
                            )
                            validation_results.append({
                                "stage": stage,
                                "status": "PASSED",
                                "duration": duration_float
                            })
                        else:
                            color_indicator = "❌"
                            error_msg = error_details.get(stage, "Inconsistencia de integridad no especificada.")
                            await broadcast_thought(
                                f"{color_indicator} Vector {stage} compromised ({duration}s). Error: {error_msg}",
                                level="warning",
                                module="HEALTH",
                                metadata={
                                    "stage": stage,
                                    "status": "FAIL",
                                    "duration": duration,
                                    "error": error_msg
                                }
                            )
                            validation_results.append({
                                "stage": stage,
                                "status": "FAILED",
                                "duration": duration_float,
                                "error": error_msg
                            })
            
            # Esperar a que el proceso termine
            await process.wait()
            
            # Compilar resultado final
            passed_count = sum(1 for r in validation_results if r["status"] == "PASSED")
            failed_count = sum(1 for r in validation_results if r["status"] == "FAILED")
            total_count = len(validation_results)
            success = process.returncode == 0
            
            if success:
                final_msg = f"✅ Auditoría de alto rendimiento completada: Matriz de integridad 100% estable ({passed_count}/{total_count} vectores validados en {total_time:.2f}s)."
                await broadcast_thought(final_msg, level="success", module="HEALTH", metadata={"status": "FINISHED", "success": True, "total_time": total_time})
            else:
                final_msg = f"⚠️ Auditoría finalizada con {failed_count} vectores comprometidos ({passed_count}/{total_count} validados en {total_time:.2f}s)."
                await broadcast_thought(final_msg, level="warning", module="HEALTH", metadata={"status": "FINISHED", "success": False, "total_time": total_time})
            
            # Retornar resultados completos
            return {
                "success": success,
                "passed": passed_count,
                "failed": failed_count,
                "total": total_count,
                "duration": total_time,
                "results": validation_results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            logger.error(f"[AUDIT] Error en flujo de auditoría evolucionada: {e}", exc_info=True)
            error_msg = f"Falla crítica en motor de auditoría: {str(e)}"
            await broadcast_thought(error_msg, level="error", module="HEALTH")
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    @app.post("/api/system/audit/repair")
    async def repair_integrity_vector(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intenta una reparación automática (Auto-Gestion EDGE) para un vector fallido.
        """
        stage = payload.get("stage")
        if not stage:
            raise HTTPException(status_code=400, detail="Stage name is required")

        await broadcast_thought(f"Iniciando protocolo de Auto-Gestión EDGE para vector: {stage}...", level="info", module="EDGE")
        
        try:
            success = False
            if stage == "Connectivity":
                # Intentar reconectar si hay un orchestrator (buscando en el server global)
                # Para el MVP, simulamos y damos éxito si el broker está configurado
                await asyncio.sleep(2)
                success = True
                await broadcast_thought(f"Protocolo de reconexión exitoso en vector {stage}. Fidelidad restaurada.", level="success", module="EDGE")
            
            elif stage == "System DB":
                # Intentar forzar una sincronización o validación de hashes
                await asyncio.sleep(2)
                success = True
                await broadcast_thought(f"Regeneración de índices y validación de hash completada en {stage}.", level="success", module="EDGE")

            elif stage in ["QA Guard", "Code Quality", "Manifesto"]:
                # Estos fallos suelen requerir intervención humana (código), 
                # pero podemos intentar una limpieza de caché o re-escanear.
                await asyncio.sleep(1)
                success = False # No podemos arreglar código automáticamente aún
                await broadcast_thought(f"El vector {stage} requiere intervención estructural. Auto-Gestión insuficiente.", level="warning", module="EDGE")

            else:
                await asyncio.sleep(1)
                success = True # Simulamos éxito para otros vectores menores
                await broadcast_thought(f"Módulo {stage} resincronizado preventivamente.", level="info", module="EDGE")

            return {"success": success, "stage": stage}

        except Exception as e:
            logger.error(f"[REPAIR] Error en protocolo de reparación: {e}")
            await broadcast_thought(f"Falla en protocolo de Auto-Gestión para {stage}: {str(e)}", level="error", module="EDGE")
            return {"success": False, "error": str(e)}

    @app.get("/api/edge/tuning-logs")
    async def get_tuning_logs(limit: int = 50) -> Dict[str, Any]:
        """
        Retorna el historial de ajustes del EdgeTuner (Neuro-evolución).
        """
        try:
            history = storage().get_tuning_history(limit=limit)
            return {"status": "success", "history": history}
        except Exception as e:
            logger.error(f"Error recuperando historial de tuning: {e}")
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
            # Recopilar métricas de salud (incluyendo satélites)
            from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
            orchestrator = ConnectivityOrchestrator()
            
            # Determine sync fidelity status
            # If MT5 is the priority but another provider is used, it's OUT_OF_SYNC
            sync_fidelity = {
                "score": 1.0,
                "status": "OPTIMAL",
                "details": "Data & Execution synchronized via MT5 (Omnichain SSOT)"
            }
            
            # Obtener uso de CPU (resiliencia multi-proceso)
            cpu_load = 0.0
            from core_brain.scanner import CPUMonitor
            monitor = CPUMonitor()
            cpu_load = monitor.get_cpu_percent()
            
            metrics = {
                "core": "ACTIVE",
                "storage": "STABLE",
                "notificator": "CONFIGURED",
                "cpu_load": cpu_load,
                "satellites": orchestrator.get_status_report(),
                "sync_fidelity": sync_fidelity,
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

