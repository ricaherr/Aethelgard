"""Quick MT5 status checker"""
import MetaTrader5 as mt5

print("Connecting to existing MT5 instance...")
# Don't specify path - connect to already running instance
result = mt5.initialize()
print(f"Init result: {result}")

if result:
    info = mt5.terminal_info()
    print(f"Terminal: {info.company if info else 'Not available'}")
    
    account_info = mt5.account_info()
    if account_info:
        print(f"Account Login: {account_info.login}")
        print(f"Account Balance: ${account_info.balance:.2f}")
        print(f"Account Equity: ${account_info.equity:.2f}")
    else:
        print("No account connected")
    
    positions = mt5.positions_get()
    print(f"\nPositions: {len(positions) if positions else 0}")
    
    if positions:
        for p in positions:
            print(f"  Ticket {p.ticket}: {p.symbol}, entry={p.price_open:.5f}, SL={p.sl:.5f}, profit=${p.profit:.2f}")
    
    mt5.shutdown()
else:
    print(f"Failed to initialize MT5. Error: {mt5.last_error()}")
