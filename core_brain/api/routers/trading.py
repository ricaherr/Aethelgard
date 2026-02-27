"""
Router de Trading - Endpoints de gestión de señales y posiciones.
Micro-ETI 2.1: Oleada 2 de migración de operaciones.
Micro-ETI 3.1: Refactored to delegate business logic to TradingService.
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends

from data_vault.storage import StorageManager
from core_brain.api.dependencies.auth import get_current_active_user
from models.auth import TokenPayload
from models.signal import Signal, SignalType, ConnectorType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trading"])


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager to avoid import-time initialization."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_trading_service() -> 'TradingService':
    """Lazy-load TradingService singleton."""
    from core_brain.server import _get_trading_service as get_ts_from_server
    return get_ts_from_server()


async def _broadcast_thought(message: str, module: str = "TRADING", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


@router.get("/signals")
async def get_signals(
    limit: int = 100, 
    minutes: int = 10080,
    symbols: str = None,  # Comma-separated: "EURUSD,GBPUSD"
    timeframes: str = None,  # Comma-separated: "M1,M5"
    regimes: str = None,  # Comma-separated: "TREND,RANGE"
    strategies: str = None,  # Comma-separated: "Trifecta,Oliver Velez"
    status: str = 'PENDING,EXECUTED,EXPIRED',  # Default to recent signals
    token: TokenPayload = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get recent signals from database with optional filters
    Includes live trade status and P/L for executed signals.
    """
    try:
        logger.info(f"GET /api/signals: limit={limit}, minutes={minutes}, symbols={symbols}, status={status}")
        
        storage = _get_storage()
        tenant_id = token.tid
        
        # Get signals from DB with SQL-level filtering
        all_signals = storage.get_recent_signals(
            minutes=minutes, 
            limit=limit,
            symbol=symbols,
            timeframe=timeframes,
            status=status,
            tenant_id=tenant_id
        )
        
        # Obtener estados de mercado para flag has_chart
        market_state = storage.get_all_market_states(tenant_id=tenant_id) or {}
        
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
            trace_results = storage.execute_query(trace_query, tuple(signal_ids), tenant_id=tenant_id)
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
                result = storage.get_trade_result_by_signal_id(sig_id, tenant_id=tenant_id)
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


@router.post("/signals/execute")
async def execute_signal_manual(data: dict, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
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
        
        storage = _get_storage()
        trading_service = _get_trading_service()
        tenant_id = token.tid
        
        # Get signal from database
        signal_data = storage.get_signal_by_id(signal_id, tenant_id=tenant_id)
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
        # Parse metadata
        metadata = signal_data.get('metadata', {})
        if isinstance(metadata, str):
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
        
        # Get MT5 connector via TradingService
        mt5_connector = trading_service.get_mt5_connector(tenant_id=tenant_id)
        if not mt5_connector:
            return {
                "success": False,
                "message": "MT5 connector not available. Check connection.",
                "signal_id": signal_id
            }
        
        # Create risk manager and executor
        account_balance = trading_service.get_account_balance(tenant_id=tenant_id)
        risk_manager = RiskManager(storage=storage, initial_capital=account_balance, tenant_id=tenant_id)
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
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
            storage.update_signal_status(signal_id, 'EXECUTED', {
                'executed_at': datetime.now().isoformat(),
                'execution_method': 'manual'
            }, tenant_id=tenant_id)
            
            await _broadcast_thought(
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


@router.get("/positions/open")
async def get_open_positions(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Get open positions with risk metadata.
    Returns positions with initial_risk_usd, r_multiple, asset_type.
    Delegates to TradingService (Micro-ETI 3.1).
    """
    try:
        trading_service = _get_trading_service()
        return await trading_service.get_open_positions(tenant_id=token.tid)
    except Exception as e:
        logger.error(f"Error getting open positions: {e}")
        return {"positions": [], "total_risk_usd": 0.0, "count": 0}


@router.get("/edge/history")
async def get_edge_history(limit: int = 50, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Retorna el historial unificado de aprendizaje y tunning.
    Combina:
    1. Ajustes paramétricos (vía EdgeTuner.adjust_parameters).
    2. Aprendizaje autónomo (vía EdgeTuner - Delta Feedback).
    """
    try:
        storage = _get_storage()
        tenant_id = token.tid
        
        # 1. Obtener historial de tuning (legacy)
        tuning_history = storage.get_tuning_history(limit=limit, tenant_id=tenant_id)
        
        # 2. Obtener historial de aprendizaje autónomo (Edge)
        edge_history = storage.get_edge_learning_history(limit=limit, tenant_id=tenant_id)
        
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


@router.post("/auto-trading/toggle")
async def toggle_auto_trading(request: Request, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Activa o desactiva el auto-trading"""
    try:
        # Parse JSON body
        body = await request.json()
        enabled = body.get('enabled', False)
        
        storage = _get_storage()
        tenant_id = token.tid
        
        success = storage.update_user_preferences(tenant_id, {'auto_trading_enabled': enabled}, tenant_id=tenant_id)
        if success:
            status = "enabled" if enabled else "disabled"
            logger.info(f"Auto-trading {status} for tenant {tenant_id}")
            return {"success": True, "auto_trading_enabled": enabled, "message": f"Auto-trading {status}"}
        else:
            raise HTTPException(status_code=400, detail="Failed to toggle auto-trading")
    except Exception as e:
        logger.error(f"Error toggling auto-trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/library")
async def get_strategies_library(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Returns the strategy library: registered strategies from DB + educational catalog."""
    try:
        storage = _get_storage()
        rankings = storage.get_all_strategy_rankings(tenant_id=token.tid)

        registered = [
            {
                "id": r.get("strategy_id"),
                "name": r.get("strategy_id", "").replace("_", " ").title(),
                "mode": r.get("execution_mode", "SHADOW"),
                "profit_factor": r.get("profit_factor", 0.0),
                "win_rate": r.get("win_rate", 0.0),
                "sharpe_ratio": r.get("sharpe_ratio", 0.0),
                "total_trades": r.get("total_trades", 0),
                "drawdown_max": r.get("drawdown_max", 0.0),
            }
            for r in rankings
        ]

        # Educational catalog (static reference data)
        educational = [
            {
                "id": "trifecta",
                "name": "Trifecta Alignment",
                "description": "Multi-timeframe confluence using EMA alignment, market structure, and regime confirmation.",
                "category": "Confluence",
            },
            {
                "id": "oliver_velez",
                "name": "Oliver Velez Elephant Bar",
                "description": "Momentum entry on high-volume expansion candles with strict risk management.",
                "category": "Price Action",
            },
            {
                "id": "fvg",
                "name": "Fair Value Gap (FVG)",
                "description": "Institutional order flow strategy targeting imbalance zones.",
                "category": "Institutional",
            },
        ]

        return {"registered": registered, "educational": educational}
    except Exception as e:
        logger.error(f"Error getting strategies library: {e}")
        raise HTTPException(status_code=500, detail=str(e))
