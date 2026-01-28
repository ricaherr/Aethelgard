"""
MetaTrader 5 Demo Account Setup
Auto-configures MT5 demo account for Aethelgard trading
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
from datetime import datetime

try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ MetaTrader5 library not installed!")
    print("   Install with: pip install MetaTrader5")
    sys.exit(1)


BROKERS_CONFIG = {
    "1": {
        "name": "Pepperstone",
        "server": "Pepperstone-Demo",
        "description": "Popular forex broker with tight spreads",
        "website": "https://pepperstone.com/en/demo-account"
    },
    "2": {
        "name": "IC Markets",
        "server": "ICMarketsSC-Demo",
        "description": "Low spread broker, good for scalping",
        "website": "https://www.icmarkets.com/global/en/open-account/demo"
    },
    "3": {
        "name": "XM",
        "server": "XMGlobal-Demo",
        "description": "Reliable broker with many instruments",
        "website": "https://www.xm.com/demo-account"
    },
    "4": {
        "name": "FXCM",
        "server": "FXCM-USDDemo01",
        "description": "Established broker with good platform",
        "website": "https://www.fxcm.com/uk/demo-account/"
    },
    "5": {
        "name": "Custom",
        "server": "CUSTOM",
        "description": "Enter your own broker details",
        "website": ""
    }
}


def print_header():
    """Print welcome header"""
    print("\n" + "=" * 70)
    print("🚀 AETHELGARD - MetaTrader 5 Demo Account Setup")
    print("=" * 70)
    print()


def check_mt5_installation():
    """Check if MT5 is installed and accessible"""
    print("🔍 Checking MetaTrader 5 installation...")
    
    if not mt5.initialize():
        error = mt5.last_error()
        print(f"❌ Error: Could not initialize MT5: {error}")
        print()
        print("💡 Solutions:")
        print("   1. Install MetaTrader 5 from: https://www.metatrader5.com/en/download")
        print("   2. Make sure MT5 is closed before running this script")
        print("   3. Run this script as Administrator")
        return False
    
    version = mt5.version()
    print(f"✅ MT5 Found! Version: {version[0]}.{version[1]}.{version[2]}")
    mt5.shutdown()
    return True


def display_broker_menu():
    """Display broker selection menu"""
    print()
    print("📋 Select a broker for demo account:")
    print()
    
    for key, broker in BROKERS_CONFIG.items():
        print(f"   [{key}] {broker['name']}")
        print(f"       Server: {broker['server']}")
        print(f"       {broker['description']}")
        if broker['website']:
            print(f"       Demo: {broker['website']}")
        print()
    
    while True:
        choice = input("Enter your choice [1-5]: ").strip()
        if choice in BROKERS_CONFIG:
            return BROKERS_CONFIG[choice]
        print("❌ Invalid choice. Please enter 1-5")


def get_broker_credentials(broker):
    """Get broker login credentials from user"""
    print()
    print(f"📝 Enter credentials for {broker['name']}:")
    print()
    
    if broker['server'] == 'CUSTOM':
        server = input("   Server name: ").strip()
    else:
        server = broker['server']
        print(f"   Server: {server}")
    
    print()
    print("   If you don't have a demo account yet:")
    if broker['website']:
        print(f"   👉 Visit: {broker['website']}")
    else:
        print(f"   👉 Search for '{broker['name']} demo account'")
    print()
    
    login = input("   Login (account number): ").strip()
    password = input("   Password: ").strip()
    
    return {
        'login': login,
        'password': password,
        'server': server,
        'broker_name': broker['name']
    }


def test_connection(credentials):
    """Test MT5 connection with provided credentials"""
    print()
    print("🔌 Testing connection...")
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return False
    
    # Attempt login
    authorized = mt5.login(
        login=int(credentials['login']),
        password=credentials['password'],
        server=credentials['server']
    )
    
    if not authorized:
        error = mt5.last_error()
        print(f"❌ Login failed: {error}")
        print()
        print("💡 Common issues:")
        print("   - Incorrect login/password")
        print("   - Wrong server name")
        print("   - Demo account expired (most brokers expire after 30 days)")
        print("   - Server is offline")
        mt5.shutdown()
        return False
    
    # Get account info
    account_info = mt5.account_info()
    
    if account_info is None:
        print("❌ Could not retrieve account information")
        mt5.shutdown()
        return False
    
    # Verify it's a demo account
    is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    
    print()
    print("=" * 70)
    print("✅ CONNECTION SUCCESSFUL!")
    print("=" * 70)
    print()
    print(f"   Account: {account_info.login}")
    print(f"   Name: {account_info.name}")
    print(f"   Server: {account_info.server}")
    print(f"   Currency: {account_info.currency}")
    print(f"   Balance: {account_info.balance:,.2f} {account_info.currency}")
    print(f"   Leverage: 1:{account_info.leverage}")
    print(f"   Account Type: {'DEMO' if is_demo else '⚠️  REAL ACCOUNT'}")
    print()
    
    if not is_demo:
        print("⚠️  WARNING: This appears to be a REAL MONEY account!")
        print("⚠️  Aethelgard will NOT execute trades on real accounts without explicit override.")
        confirm = input("\n   Type 'I UNDERSTAND THE RISK' to continue anyway: ")
        if confirm != "I UNDERSTAND THE RISK":
            print("\n❌ Setup cancelled for safety.")
            mt5.shutdown()
            return False
    
    mt5.shutdown()
    return True


def save_configuration(credentials):
    """Save broker configuration to .env file"""
    print()
    print("💾 Saving configuration...")
    
    env_path = Path(__file__).parent.parent / 'config' / 'mt5.env'
    env_path.parent.mkdir(exist_ok=True)
    
    with open(env_path, 'w') as f:
        f.write(f"# MetaTrader 5 Configuration\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Broker: {credentials['broker_name']}\n\n")
        f.write(f"MT5_LOGIN={credentials['login']}\n")
        f.write(f"MT5_PASSWORD={credentials['password']}\n")
        f.write(f"MT5_SERVER={credentials['server']}\n")
        f.write(f"MT5_ENABLED=true\n")
    
    print(f"✅ Configuration saved to: {env_path}")
    
    # Also save to JSON for easier Python access
    json_path = Path(__file__).parent.parent / 'config' / 'mt5_config.json'
    
    config_data = {
        'login': credentials['login'],
        'server': credentials['server'],
        'broker_name': credentials['broker_name'],
        'enabled': True,
        'configured_at': datetime.now().isoformat()
    }
    
    with open(json_path, 'w') as f:
        json.dump(config_data, f, indent=2)
    
    print(f"✅ JSON config saved to: {json_path}")
    print()
    print("⚠️  Security Note: Password is stored locally in plain text.")
    print("   Keep config/mt5.env secure and never commit to version control!")


def run_test_trade():
    """Offer to run a test trade"""
    print()
    print("=" * 70)
    print("🧪 Test Trade")
    print("=" * 70)
    print()
    print("Would you like to execute a test trade to verify everything works?")
    print("(This will open a small position and close it immediately)")
    print()
    
    response = input("Run test trade? [y/N]: ").strip().lower()
    
    if response == 'y':
        print()
        print("🔄 Running test trade...")
        print("   (Feature coming soon - will execute via MT5Bridge)")
        print()
    else:
        print()
        print("⏭️  Skipped test trade")


def main():
    """Main setup flow"""
    print_header()
    
    # Step 1: Check MT5 installation
    if not check_mt5_installation():
        return
    
    # Step 2: Select broker
    broker = display_broker_menu()
    
    # Step 3: Get credentials
    credentials = get_broker_credentials(broker)
    
    # Step 4: Test connection
    if not test_connection(credentials):
        print()
        print("❌ Setup failed. Please check your credentials and try again.")
        return
    
    # Step 5: Save configuration
    save_configuration(credentials)
    
    # Step 6: Optional test trade
    run_test_trade()
    
    # Final instructions
    print()
    print("=" * 70)
    print("✅ SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("   1. Start the system: python start_production.py")
    print("   2. Open dashboard: http://localhost:8504")
    print("   3. Go to tab '💰 Análisis de Activos' to see results")
    print()
    print("The system will now:")
    print("   ✓ Scan markets automatically")
    print("   ✓ Generate trading signals")
    print("   ✓ Execute trades on your MT5 demo account")
    print("   ✓ Monitor closed positions")
    print("   ✓ Display results in real-time dashboard")
    print()
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
