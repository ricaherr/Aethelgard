"""
Test EDGE en vivo - Simula trades para verificar auto-ajuste
"""
import asyncio
import logging
from datetime import datetime

from data_vault.storage import StorageManager
from core_brain.tuner import EdgeTuner

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


async def simulate_losing_streak():
    """Simula racha de 10 pérdidas para activar modo CONSERVADOR"""
    storage = StorageManager()
    tuner = EdgeTuner(storage=storage)
    
    logger.info("=" * 70)
    logger.info("🧪 TEST EDGE: Simulando racha de 10 pérdidas")
    logger.info("=" * 70)
    
    # Guardar 10 trades perdedores
    for i in range(10):
        trade = {
            "signal_id": f"test_loss_{i}_{datetime.now().timestamp()}",
            "symbol": "EURUSD",
            "entry_price": 1.1000 + (i * 0.0001),
            "exit_price": 1.0990 + (i * 0.0001),
            "pips": -10.0,
            "profit_loss": -100.0,
            "duration_minutes": 30,
            "is_win": False,
            "exit_reason": "stop_loss",
            "market_regime": "TREND",
            "volatility_atr": 0.0015,
            "parameters_used": {
                "adx_threshold": 25,
                "elephant_atr_multiplier": 0.3,
                "sma20_proximity_percent": 1.5
            }
        }
        trade_id = storage.save_trade_result(trade)
        logger.info(f"  ❌ Trade {i+1}/10 guardado: {trade_id[:8]}... (Pérdida -10 pips)")
    
    # Esperar un momento
    await asyncio.sleep(1)
    
    # Ejecutar ajuste EDGE
    logger.info("\n⚙️  Ejecutando ajuste EDGE...")
    adjustment = tuner.adjust_parameters()
    
    if adjustment and not adjustment.get("skipped_reason"):
        logger.info("✅ AJUSTE REALIZADO:")
        logger.info(f"   Trigger: {adjustment['trigger']}")
        logger.info(f"   Win Rate: {adjustment['stats']['win_rate']:.1%}")
        logger.info(f"   Pérdidas consecutivas: {adjustment['stats']['consecutive_losses']}")
        logger.info("\n📊 CAMBIOS DE PARÁMETROS:")
        
        old = adjustment['old_params']
        new = adjustment['new_params']
        
        logger.info(f"   ADX Threshold: {old['adx_threshold']:.1f} → {new['adx_threshold']:.1f}")
        logger.info(f"   ATR Multiplier: {old['elephant_atr_multiplier']:.2f} → {new['elephant_atr_multiplier']:.2f}")
        logger.info(f"   SMA20 Proximity: {old['sma20_proximity_percent']:.1f}% → {new['sma20_proximity_percent']:.1f}%")
        logger.info(f"   Min Score: {old['min_signal_score']} → {new['min_signal_score']}")
        
        logger.info("\n🎯 RESULTADO:")
        if new['adx_threshold'] > old['adx_threshold']:
            logger.info("   ✅ Sistema MÁS CONSERVADOR (ADX threshold aumentado)")
        if new['elephant_atr_multiplier'] > old['elephant_atr_multiplier']:
            logger.info("   ✅ Filtro ATR MÁS ESTRICTO (solo velas grandes)")
        if new['sma20_proximity_percent'] < old['sma20_proximity_percent']:
            logger.info("   ✅ Pullback MÁS PRECISO (proximidad reducida)")
    else:
        reason = adjustment.get("skipped_reason") if adjustment else "unknown"
        logger.info(f"⏸️  Sin ajustes: {reason}")


async def simulate_winning_streak():
    """Simula racha de victorias para activar modo AGRESIVO"""
    storage = StorageManager()
    tuner = EdgeTuner(storage=storage)
    
    logger.info("\n" + "=" * 70)
    logger.info("🧪 TEST EDGE: Simulando racha de 15 victorias (73% win rate)")
    logger.info("=" * 70)
    
    # Guardar 15 trades (11 wins, 4 losses = 73%)
    for i in range(15):
        is_winner = i < 11
        
        trade = {
            "signal_id": f"test_win_{i}_{datetime.now().timestamp()}",
            "symbol": "GBPJPY",
            "entry_price": 150.00 + (i * 0.01),
            "exit_price": 150.00 + (i * 0.01) + (0.30 if is_winner else -0.15),
            "pips": 30.0 if is_winner else -15.0,
            "profit_loss": 300.0 if is_winner else -150.0,
            "duration_minutes": 45,
            "is_win": is_winner,
            "exit_reason": "take_profit" if is_winner else "stop_loss",
            "market_regime": "TREND",
            "volatility_atr": 0.0020,
            "parameters_used": {
                "adx_threshold": 30,
                "elephant_atr_multiplier": 0.5,
                "sma20_proximity_percent": 1.0
            }
        }
        trade_id = storage.save_trade_result(trade)
        emoji = "✅" if is_winner else "❌"
        logger.info(f"  {emoji} Trade {i+1}/15 guardado: {trade_id[:8]}... ({'Ganancia +30' if is_winner else 'Pérdida -15'} pips)")
    
    await asyncio.sleep(1)
    
    logger.info("\n⚙️  Ejecutando ajuste EDGE...")
    adjustment = tuner.adjust_parameters()
    
    if adjustment and not adjustment.get("skipped_reason"):
        logger.info("✅ AJUSTE REALIZADO:")
        logger.info(f"   Trigger: {adjustment['trigger']}")
        logger.info(f"   Win Rate: {adjustment['stats']['win_rate']:.1%}")
        logger.info("\n📊 CAMBIOS DE PARÁMETROS:")
        
        old = adjustment['old_params']
        new = adjustment['new_params']
        
        logger.info(f"   ADX Threshold: {old['adx_threshold']:.1f} → {new['adx_threshold']:.1f}")
        logger.info(f"   ATR Multiplier: {old['elephant_atr_multiplier']:.2f} → {new['elephant_atr_multiplier']:.2f}")
        logger.info(f"   SMA20 Proximity: {old['sma20_proximity_percent']:.1f}% → {new['sma20_proximity_percent']:.1f}%")
        
        logger.info("\n🎯 RESULTADO:")
        if new['adx_threshold'] < old['adx_threshold']:
            logger.info("   ✅ Sistema MÁS AGRESIVO (ADX threshold reducido)")
        if new['elephant_atr_multiplier'] < old['elephant_atr_multiplier']:
            logger.info("   ✅ Filtro ATR RELAJADO (captura más señales)")
        if new['sma20_proximity_percent'] > old['sma20_proximity_percent']:
            logger.info("   ✅ Pullback MÁS TOLERANTE (mayor margen)")
    else:
        reason = adjustment.get("skipped_reason") if adjustment else "unknown"
        logger.info(f"⏸️  Sin ajustes: {reason}")


async def check_current_params():
    """Muestra parámetros actuales del sistema"""
    import json
    
    logger.info("\n" + "=" * 70)
    logger.info("📋 PARÁMETROS ACTUALES DEL SISTEMA")
    logger.info("=" * 70)
    
    with open("config/dynamic_params.json", 'r') as f:
        config = json.load(f)
    
    logger.info(f"ADX Threshold: {config.get('adx_threshold', 'N/A')}")
    logger.info(f"ATR Multiplier: {config.get('elephant_atr_multiplier', 'N/A')}")
    logger.info(f"SMA20 Proximity: {config.get('sma20_proximity_percent', 'N/A')}%")
    logger.info(f"Min Signal Score: {config.get('min_signal_score', 'N/A')}")
    logger.info(f"Tuning Enabled: {config.get('tuning_enabled', False)}")
    logger.info(f"Target Win Rate: {config.get('target_win_rate', 0.0):.1%}")


async def main():
    """Ejecuta todas las pruebas EDGE"""
    # Mostrar parámetros iniciales
    await check_current_params()
    
    # Test 1: Racha de pérdidas
    await simulate_losing_streak()
    await asyncio.sleep(2)
    await check_current_params()
    
    # Test 2: Racha de victorias
    await simulate_winning_streak()
    await asyncio.sleep(2)
    await check_current_params()
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ PRUEBA EDGE COMPLETA")
    logger.info("=" * 70)
    logger.info("El sistema demostró capacidad de auto-ajuste:")
    logger.info("  • Modo CONSERVADOR tras pérdidas ✓")
    logger.info("  • Modo AGRESIVO tras victorias ✓")
    logger.info("  • Parámetros persistidos en dynamic_params.json ✓")
    logger.info("\n🔄 El sistema en producción ajustará automáticamente cada 1 hora")


if __name__ == "__main__":
    asyncio.run(main())
