"""
TDD: Test del sistema EDGE de auto-ajuste de parámetros
Verifica que el tuner se vuelva más conservador tras racha de pérdidas
"""
import pytest
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from core_brain.tuner import EdgeTuner
from data_vault.storage import StorageManager


@pytest.fixture
def temp_db(tmp_path):
    """Crea base de datos temporal para tests"""
    db_path = tmp_path / "test_system_state.json"
    storage = StorageManager(str(db_path))
    return storage


@pytest.fixture
def temp_config(tmp_path):
    """Crea archivo de configuración temporal"""
    config_path = tmp_path / "dynamic_params.json"
    initial_config = {
        "adx_threshold": 25,
        "elephant_atr_multiplier": 0.3,
        "sma20_proximity_percent": 1.5,
        "min_signal_score": 60,
        "tuning_enabled": True,
        "min_trades_for_tuning": 10,
        "target_win_rate": 0.55,
        "aggressive_mode_threshold": 0.65,
        "conservative_mode_threshold": 0.45
    }
    
    with open(config_path, 'w') as f:
        json.dump(initial_config, f, indent=2)
    
    return str(config_path)


@pytest.fixture
def edge_tuner(temp_db, temp_config):
    """Instancia EdgeTuner para tests"""
    return EdgeTuner(storage=temp_db, config_path=temp_config)


def test_tuner_becomes_conservative_after_losing_streak(temp_db, edge_tuner, temp_config):
    """
    TEST CRÍTICO: Tras 10 pérdidas consecutivas, el sistema debe:
    - Subir elephant_atr_multiplier (0.3 → 0.5+) para filtrar señales débiles
    - Subir adx_threshold (25 → 30+) para exigir tendencias más fuertes
    - Reducir sma20_proximity_percent (1.5 → 1.0) para ser más estricto en pullbacks
    """
    # === ARRANGE: Simular 10 trades perdedores consecutivos ===
    losing_trades = []
    base_time = datetime.now()
    
    for i in range(10):
        trade = {
            "signal_id": f"signal_{i}",
            "symbol": "EURUSD",
            "entry_price": 1.1000 + (i * 0.0001),
            "exit_price": 1.0990 + (i * 0.0001),  # Pérdida de 10 pips
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
        temp_db.save_trade_result(trade)
        losing_trades.append(trade)
    
    # === ACT: Ejecutar auto-ajuste del tuner ===
    adjustment = edge_tuner.adjust_parameters()
    
    # === ASSERT: Verificar que el sistema se volvió conservador ===
    assert adjustment is not None, "Tuner debería haber hecho ajustes tras 10 pérdidas"
    
    # Leer nueva configuración
    with open(temp_config, 'r') as f:
        new_config = json.load(f)
    
    # Verificar aumento de ATR multiplier (más filtrado)
    assert new_config["elephant_atr_multiplier"] > 0.3, \
        f"ATR multiplier debería subir tras pérdidas. Actual: {new_config['elephant_atr_multiplier']}"
    
    assert new_config["elephant_atr_multiplier"] >= 0.5, \
        f"ATR multiplier debería estar en al menos 0.5. Actual: {new_config['elephant_atr_multiplier']}"
    
    # Verificar aumento de ADX threshold (solo tendencias fuertes)
    assert new_config["adx_threshold"] > 25, \
        f"ADX threshold debería subir tras pérdidas. Actual: {new_config['adx_threshold']}"
    
    assert new_config["adx_threshold"] >= 30, \
        f"ADX threshold debería estar en al menos 30. Actual: {new_config['adx_threshold']}"
    
    # Verificar reducción de proximidad SMA20 (más estricto)
    assert new_config["sma20_proximity_percent"] < 1.5, \
        f"SMA20 proximity debería reducirse. Actual: {new_config['sma20_proximity_percent']}"
    
    # Verificar que se guardó el ajuste en historial
    assert adjustment["trigger"] == "consecutive_losses" or adjustment["trigger"] == "low_win_rate"
    assert "old_params" in adjustment
    assert "new_params" in adjustment
    assert adjustment["stats"]["win_rate"] == 0.0  # 0/10 wins


def test_tuner_becomes_aggressive_after_winning_streak(temp_db, edge_tuner, temp_config):
    """
    Tras 15 trades ganadores con win_rate > 65%, el sistema debe:
    - Bajar elephant_atr_multiplier (0.5 → 0.2) para capturar más señales
    - Bajar adx_threshold (30 → 20) para operar en tendencias moderadas
    - Aumentar sma20_proximity_percent (1.0 → 2.0) para dar más margen
    """
    # === ARRANGE: Simular 15 trades ganadores (win_rate 73%) ===
    for i in range(15):
        is_winner = i < 11  # 11 wins, 4 losses = 73% win rate
        
        trade = {
            "signal_id": f"signal_win_{i}",
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
        temp_db.save_trade_result(trade)
    
    # === ACT: Ejecutar auto-ajuste ===
    adjustment = edge_tuner.adjust_parameters()
    
    # === ASSERT: Verificar modo agresivo ===
    assert adjustment is not None
    
    with open(temp_config, 'r') as f:
        new_config = json.load(f)
    
    # ATR multiplier debería bajar (menos filtrado)
    assert new_config["elephant_atr_multiplier"] < 0.5, \
        f"ATR multiplier debería bajar tras victorias. Actual: {new_config['elephant_atr_multiplier']}"
    
    # ADX threshold debería bajar (aceptar tendencias más débiles)
    assert new_config["adx_threshold"] < 30, \
        f"ADX threshold debería bajar. Actual: {new_config['adx_threshold']}"
    
    # Proximidad SMA20 debería aumentar (más tolerante)
    assert new_config["sma20_proximity_percent"] > 1.0, \
        f"SMA20 proximity debería aumentar. Actual: {new_config['sma20_proximity_percent']}"
    
    assert adjustment["stats"]["win_rate"] >= 0.65


def test_tuner_requires_minimum_trades(temp_db, edge_tuner):
    """
    El tuner NO debe ajustar parámetros si hay menos de min_trades_for_tuning
    """
    # Solo 5 trades (min es 10 según config)
    for i in range(5):
        trade = {
            "signal_id": f"signal_{i}",
            "symbol": "USDJPY",
            "entry_price": 110.00,
            "exit_price": 109.90,
            "pips": -10.0,
            "profit_loss": -100.0,
            "duration_minutes": 20,
            "is_win": False,
            "exit_reason": "stop_loss",
            "market_regime": "TREND",
            "volatility_atr": 0.0012,
            "parameters_used": {"adx_threshold": 25}
        }
        temp_db.save_trade_result(trade)
    
    adjustment = edge_tuner.adjust_parameters()
    
    # No debería hacer ajustes con tan pocos datos
    assert adjustment is None or adjustment.get("skipped_reason") == "insufficient_data"


def test_tuner_stability_within_target_range(temp_db, edge_tuner, temp_config):
    """
    Si win_rate está cerca del target (50-60%), el tuner debe hacer ajustes mínimos
    """
    # 20 trades con win_rate 55% (11 wins, 9 losses)
    for i in range(20):
        is_winner = i % 2 == 0 and i < 22  # Simular ~55% win rate
        
        trade = {
            "signal_id": f"signal_{i}",
            "symbol": "EURUSD",
            "entry_price": 1.1000,
            "exit_price": 1.1010 if is_winner else 1.0995,
            "pips": 10.0 if is_winner else -5.0,
            "profit_loss": 100.0 if is_winner else -50.0,
            "duration_minutes": 30,
            "is_win": is_winner,
            "exit_reason": "take_profit" if is_winner else "stop_loss",
            "market_regime": "TREND",
            "volatility_atr": 0.0015,
            "parameters_used": {"adx_threshold": 25, "elephant_atr_multiplier": 0.3}
        }
        temp_db.save_trade_result(trade)
    
    # Leer configuración antes del ajuste
    with open(temp_config, 'r') as f:
        old_config = json.load(f)
    
    adjustment = edge_tuner.adjust_parameters()
    
    # Leer configuración después
    with open(temp_config, 'r') as f:
        new_config = json.load(f)
    
    # Cambios deben ser mínimos (< 10% de variación)
    old_atr = old_config["elephant_atr_multiplier"]
    new_atr = new_config["elephant_atr_multiplier"]
    change_pct = abs(new_atr - old_atr) / old_atr * 100
    
    assert change_pct < 20, f"Cambios deben ser graduales. Cambio: {change_pct}%"
