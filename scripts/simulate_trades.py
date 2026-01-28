"""
Simulador de Trades para Demostración del Feedback Loop
Crea trades de ejemplo para visualizar el Dashboard de Análisis de Activos
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType
import random

def simulate_trades():
    """Simula trades cerrados para demostrar el Feedback Loop"""
    
    print("=" * 70)
    print("📊 SIMULADOR DE TRADES - FEEDBACK LOOP DEMO")
    print("=" * 70)
    print()
    
    storage = StorageManager()
    
    # Símbolos a simular
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD']
    
    # Generar 20 trades de ejemplo
    num_trades = 20
    trades_created = 0
    
    print(f"Creando {num_trades} trades de ejemplo...")
    print()
    
    for i in range(num_trades):
        symbol = random.choice(symbols)
        signal_type = random.choice([SignalType.BUY, SignalType.SELL])
        
        # Precios de ejemplo
        if symbol == 'EURUSD':
            entry_price = round(random.uniform(1.0800, 1.1200), 5)
        elif symbol == 'GBPUSD':
            entry_price = round(random.uniform(1.2500, 1.3000), 5)
        elif symbol == 'USDJPY':
            entry_price = round(random.uniform(145.00, 150.00), 3)
        elif symbol == 'AUDUSD':
            entry_price = round(random.uniform(0.6500, 0.6800), 5)
        else:  # USDCAD
            entry_price = round(random.uniform(1.3400, 1.3800), 5)
        
        # Simular resultado (70% win rate)
        is_win = random.random() < 0.70
        
        if is_win:
            # Trade ganador
            pips = random.uniform(10, 50)
            profit = round(random.uniform(50, 200), 2)
            exit_reason = random.choice(['TAKE_PROFIT', 'TAKE_PROFIT', 'MANUAL'])
        else:
            # Trade perdedor
            pips = -random.uniform(5, 30)
            profit = round(random.uniform(-100, -30), 2)
            exit_reason = 'STOP_LOSS'
        
        # Calcular exit price
        if symbol == 'USDJPY':
            pip_value = 0.01
        else:
            pip_value = 0.0001
        
        if signal_type == SignalType.BUY:
            exit_price = entry_price + (pips * pip_value)
        else:
            exit_price = entry_price - (pips * pip_value)
        
        # Crear señal primero
        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            entry_price=entry_price,
            stop_loss=entry_price - (20 * pip_value) if signal_type == SignalType.BUY else entry_price + (20 * pip_value),
            take_profit=entry_price + (30 * pip_value) if signal_type == SignalType.BUY else entry_price - (30 * pip_value),
            confidence=random.uniform(0.6, 0.9),
            connector_type='SIMULATED'
        )
        
        signal_id = storage.save_signal(signal)
        
        # Actualizar a EXECUTED
        storage.update_signal_status(signal_id, 'EXECUTED', {
            'ticket': 100000 + i,
            'execution_time': datetime.now().isoformat()
        })
        
        # Guardar resultado del trade
        duration_minutes = random.randint(15, 480)  # 15 min a 8 horas
        
        trade_result = {
            'signal_id': signal_id,
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pips': round(pips, 2),
            'profit_loss': profit,
            'duration_minutes': duration_minutes,
            'is_win': is_win,
            'exit_reason': exit_reason,
            'market_regime': random.choice(['TREND', 'RANGE', 'VOLATILE']),
            'volatility_atr': random.uniform(0.0005, 0.0020),
            'parameters_used': {
                'strategy': 'oliver_velez_swing_v2',
                'adx_threshold': 25,
                'rsi_oversold': 30,
                'rsi_overbought': 70
            }
        }
        
        storage.save_trade_result(trade_result)
        
        # Actualizar señal a CLOSED
        storage.update_signal_status(signal_id, 'CLOSED', {
            'exit_price': exit_price,
            'profit': profit,
            'pips': pips,
            'exit_reason': exit_reason
        })
        
        trades_created += 1
        
        # Mostrar progreso
        result_emoji = "🟢" if is_win else "🔴"
        print(f"{result_emoji} Trade {i+1}/{num_trades}: {symbol} {signal_type.value} | "
              f"Profit: ${profit:+.2f} | PIPs: {pips:+.2f} | {exit_reason}")
    
    print()
    print("=" * 70)
    print(f"✅ {trades_created} trades simulados creados exitosamente!")
    print("=" * 70)
    print()
    
    # Mostrar estadísticas
    win_rate = storage.get_win_rate(days=30)
    total_profit = storage.get_total_profit(days=30)
    
    print("📊 ESTADÍSTICAS GENERALES:")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"   Profit Total: ${total_profit:,.2f}")
    print()
    
    # Mostrar por símbolo
    profit_by_symbol = storage.get_profit_by_symbol(days=30)
    
    print("💰 RENTABILIDAD POR SÍMBOLO:")
    for item in profit_by_symbol:
        result_emoji = "🟢" if item['profit'] > 0 else "🔴"
        print(f"   {result_emoji} {item['symbol']}: ${item['profit']:+,.2f} "
              f"({item['total_trades']} trades, {item['win_rate']:.1f}% WR)")
    
    print()
    print("=" * 70)
    print("🎯 Ahora abre el Dashboard en: http://localhost:8504")
    print("   Ve a la pestaña '💰 Análisis de Activos' para ver los resultados")
    print("=" * 70)


if __name__ == "__main__":
    simulate_trades()
