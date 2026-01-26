"""
Example: RiskManager Integration
Demonstrates risk management with dynamic position sizing and lockdown protection
"""
from core_brain.risk_manager import RiskManager
from models.signal import MarketRegime


def main():
    """Demonstrate RiskManager usage in trading scenarios"""
    
    print("=" * 70)
    print("AETHELGARD - Risk Manager Demo")
    print("=" * 70)
    
    # Initialize with $10,000 capital
    rm = RiskManager(initial_capital=10000)
    
    print(f"\n📊 Initial State:")
    print(f"   Capital: ${rm.capital:,.2f}")
    print(f"   Base Risk: {rm.base_risk_pct}%")
    print(f"   Volatile Risk: {rm.volatile_risk_pct}%")
    print(f"   Max Consecutive Losses: {rm.max_consecutive_losses}")
    
    # Scenario 1: TREND regime - Normal risk (1%)
    print("\n" + "─" * 70)
    print("Scenario 1: TREND Regime - Normal Risk")
    print("─" * 70)
    
    entry = 100.0
    stop_loss = 95.0
    regime = MarketRegime.TREND
    
    position_size = rm.calculate_position_size(regime, entry, stop_loss)
    risk_pct = rm.get_current_risk_pct(regime)
    
    print(f"   Regime: {regime.value}")
    print(f"   Entry: ${entry:.2f}")
    print(f"   Stop Loss: ${stop_loss:.2f}")
    print(f"   Risk per Unit: ${abs(entry - stop_loss):.2f}")
    print(f"   Risk %: {risk_pct}%")
    print(f"   → Position Size: {position_size:.2f} units")
    print(f"   → Total Risk: ${rm.capital * (risk_pct/100):.2f}")
    
    # Scenario 2: RANGE regime - Reduced risk (0.5%)
    print("\n" + "─" * 70)
    print("Scenario 2: RANGE Regime - Reduced Risk")
    print("─" * 70)
    
    regime = MarketRegime.RANGE
    position_size = rm.calculate_position_size(regime, entry, stop_loss)
    risk_pct = rm.get_current_risk_pct(regime)
    
    print(f"   Regime: {regime.value}")
    print(f"   Entry: ${entry:.2f}")
    print(f"   Stop Loss: ${stop_loss:.2f}")
    print(f"   Risk %: {risk_pct}% (REDUCED)")
    print(f"   → Position Size: {position_size:.2f} units")
    print(f"   → Total Risk: ${rm.capital * (risk_pct/100):.2f}")
    
    # Scenario 3: Loss sequence and lockdown
    print("\n" + "─" * 70)
    print("Scenario 3: Loss Sequence → Lockdown Activation")
    print("─" * 70)
    
    losses = [-100, -150, -200]
    for i, loss in enumerate(losses, 1):
        rm.record_trade_result(is_win=False, pnl=loss)
        status = rm.get_status()
        
        print(f"\n   Loss #{i}: ${loss:.2f}")
        print(f"   Capital: ${status['capital']:,.2f}")
        print(f"   Consecutive Losses: {status['consecutive_losses']}")
        print(f"   Locked: {status['is_locked']}")
        
        if status['is_locked']:
            print(f"   ⚠️  LOCKDOWN ACTIVATED!")
            print(f"   → Trading DISABLED until manual unlock")
    
    # Try to trade while locked
    print("\n" + "─" * 70)
    print("Scenario 4: Attempt to Trade in Lockdown")
    print("─" * 70)
    
    can_trade = rm.can_trade()
    position_size = rm.calculate_position_size(MarketRegime.TREND, 100, 95)
    
    print(f"   Can Trade: {can_trade}")
    print(f"   Position Size: {position_size} (blocked)")
    
    # Manual unlock
    print("\n" + "─" * 70)
    print("Scenario 5: Manual Unlock")
    print("─" * 70)
    
    rm.unlock()
    status = rm.get_status()
    
    print(f"   ✅ Lockdown UNLOCKED")
    print(f"   Consecutive Losses Reset: {status['consecutive_losses']}")
    print(f"   Can Trade: {rm.can_trade()}")
    
    # Winning trade resets counter
    print("\n" + "─" * 70)
    print("Scenario 6: Winning Trade → Counter Reset")
    print("─" * 70)
    
    # Simulate 2 losses then 1 win
    rm.record_trade_result(is_win=False, pnl=-100)
    rm.record_trade_result(is_win=False, pnl=-150)
    
    print(f"   After 2 losses:")
    status = rm.get_status()
    print(f"   Consecutive Losses: {status['consecutive_losses']}")
    print(f"   Trades until Lockdown: {status['trades_until_lockdown']}")
    
    # Winning trade
    rm.record_trade_result(is_win=True, pnl=500)
    
    print(f"\n   After WIN (+$500):")
    status = rm.get_status()
    print(f"   Consecutive Losses: {status['consecutive_losses']} (RESET)")
    print(f"   Capital: ${status['capital']:,.2f}")
    print(f"   Trades until Lockdown: {status['trades_until_lockdown']}")
    
    # Final status
    print("\n" + "=" * 70)
    print("Final Status Report")
    print("=" * 70)
    
    final_status = rm.get_status()
    for key, value in final_status.items():
        print(f"   {key}: {value}")
    
    print("\n✅ Risk Manager Demo Complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
