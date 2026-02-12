"""Verify risk calculation accuracy"""
import MetaTrader5 as mt5

mt5.initialize()

def verify_position(ticket, backfill_value):
    """Verify risk calculation for a specific position"""
    pos = [p for p in mt5.positions_get() if p.ticket == ticket][0]
    
    print("=" * 60)
    print(f"{pos.symbol} RISK CALCULATION VERIFICATION (Ticket {ticket})")
    print("=" * 60)
    
    entry = pos.price_open
    sl = pos.sl
    volume = pos.volume
    symbol = pos.symbol
    
    print(f"\nPosition Details:")
    print(f"  Entry: {entry:.5f}")
    print(f"  SL: {sl:.5f}")
    print(f"  Volume: {volume} lots")
    
    # Determine pip size
    if 'JPY' in symbol:
        pip_size = 0.01
        print(f"  Pip size: 0.01 (JPY pair)")
    else:
        pip_size = 0.0001
        print(f"  Pip size: 0.0001 (standard pair)")
    
    # Calculate pips at risk
    price_diff = abs(entry - sl)
    pips = price_diff / pip_size
    print(f"\nDistance:")
    print(f"  Price diff: {price_diff:.5f}")
    print(f"  Pips at risk: {pips:.1f}")
    
    # Calculate pip value
    # Standard approach: 1 pip per lot depends on quote currency
    if symbol.endswith('USD'):
        # Quote is USD - direct calculation
        pip_value_usd = volume * 10
        print(f"\nPip Value (direct - quote is USD):")
        print(f"  {pip_value_usd:.2f} USD per pip")
    elif symbol.endswith('JPY'):
        # Quote is JPY - need USDJPY rate
        usdjpy_rate = mt5.symbol_info_tick('USDJPY').bid
        # For JPY pairs: 1 pip = 1000 JPY per lot (since pip = 0.01)
        pip_value_jpy = volume * 1000
        pip_value_usd = pip_value_jpy / usdjpy_rate
        print(f"\nPip Value (JPY pair):")
        print(f"  USDJPY rate: {usdjpy_rate:.3f}")
        print(f"  In JPY: {pip_value_jpy:.2f} JPY per pip")
        print(f"  In USD: {pip_value_usd:.2f} USD per pip")
    elif symbol.startswith('USD'):
        # Base is USD - inverse calculation
        current_rate = entry
        pip_value_usd = (volume * 10) / current_rate
        print(f"\nPip Value (USD is base):")
        print(f"  {pip_value_usd:.2f} USD per pip")
    else:
        # Cross pair - use quote currency conversion
        quote_currency = symbol[-3:]
        quote_usd_pair = quote_currency + 'USD'
        try:
            quote_rate = mt5.symbol_info_tick(quote_usd_pair).bid
            pip_value_quote = volume * 10
            pip_value_usd = pip_value_quote * quote_rate
            print(f"\nPip Value (cross pair):")
            print(f"  {quote_usd_pair} rate: {quote_rate:.5f}")
            print(f"  In {quote_currency}: {pip_value_quote:.2f} per pip")
            print(f"  In USD: {pip_value_usd:.2f} USD per pip")
        except:
            print(f"\n⚠️  Could not get conversion rate for {quote_usd_pair}")
            return
    
    # Total risk
    total_risk_manual = pips * pip_value_usd
    
    print(f"\nTotal Risk:")
    print(f"  Manual: {pips:.1f} pips x {pip_value_usd:.2f} USD/pip = ${total_risk_manual:.2f}")
    print(f"  Backfill: ${backfill_value:.2f}")
    print(f"  Difference: ${abs(backfill_value - total_risk_manual):.2f}")
    
    # Verification status
    if abs(backfill_value - total_risk_manual) < 10.0:
        print(f"\n✅ FORMULA IS CORRECT (within $10 tolerance)")
        return True
    else:
        print(f"\n❌ FORMULA HAS ERROR (difference: ${abs(backfill_value - total_risk_manual):.2f})")
        return False


# Verify different pair types
print("\n" + "=" * 80)
print("COMPREHENSIVE RISK CALCULATION VERIFICATION")
print("=" * 80 + "\n")

results = []
results.append(("EURGBP (cross)", verify_position(1469758096, 195.28)))
results.append(("GBPJPY (JPY pair)", verify_position(1473711239, 183.64)))
results.append(("EURUSD (USD quote)", verify_position(1469894229, 163.13)))
results.append(("USDCAD (USD base)", verify_position(1469894296, 156.00)))

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
for pair_type, passed in results:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {pair_type}")

if all([r[1] for r in results]):
    print("\n🎯 ALL FORMULAS ARE CORRECT - READY FOR PRODUCTION")
else:
    print("\n⚠️  SOME FORMULAS NEED CORRECTION")

mt5.shutdown()
