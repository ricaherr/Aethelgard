"""
cTrader Demo Account Setup
Configures a cTrader DEMO account in Aethelgard (OAuth2 credentials required).

PREREQUISITE — obtain credentials before running:
  1. Open a demo account at a cTrader broker:
       IC Markets:  https://www.icmarkets.com/demo-trading-account/
       Pepperstone: https://pepperstone.com/en/demo-account
  2. Register an application at the Spotware Developer Portal:
       https://openapi.ctrader.com/apps
  3. Copy your Application client_id and client_secret.
  4. Generate an access_token via OAuth2:
       Authorization URL: https://connect.spotware.com/apps/auth
       Parameters: client_id=<your_id>&redirect_uri=<your_uri>&scope=trading
       Exchange the authorization code for an access_token at:
         https://connect.spotware.com/apps/token
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager

# Supported cTrader brokers
BROKERS = {
    "1": {
        "broker_id": "ic_markets",
        "name": "IC Markets",
        "server": "demo.ctraderapi.com",
        "website": "https://www.icmarkets.com/demo-trading-account/",
        "notes": "Login with IC Markets credentials → select cTrader platform",
    },
    "2": {
        "broker_id": "pepperstone",
        "name": "Pepperstone",
        "server": "demo.ctraderapi.com",
        "website": "https://pepperstone.com/en/demo-account",
        "notes": "Login with Pepperstone credentials → select cTrader platform",
    },
    "3": {
        "broker_id": "fxpro",
        "name": "FxPro",
        "server": "demo.ctraderapi.com",
        "website": "https://www.fxpro.com/trading/platforms/ctrader",
        "notes": "Login with FxPro credentials → select cTrader platform",
    },
    "4": {
        "broker_id": "custom",
        "name": "Custom broker",
        "server": "demo.ctraderapi.com",
        "website": "",
        "notes": "Any broker connected to cTrader Open API",
    },
}

SPOTWARE_PORTAL = "https://openapi.ctrader.com/apps"
OAUTH_AUTH_URL = "https://connect.spotware.com/apps/auth"
OAUTH_TOKEN_URL = "https://connect.spotware.com/apps/token"


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_header() -> None:
    print("\n" + "=" * 70)
    print(">>> AETHELGARD - cTrader Demo Account Setup")
    print("=" * 70)
    print()


def print_oauth_guide() -> None:
    print()
    print("  What you need (one-time setup):")
    print()
    print("  A. A cTrader DEMO account at a supported broker")
    print("     (IC Markets, Pepperstone, FxPro, or any cTrader broker)")
    print()
    print("  B. A registered application at Spotware Developer Portal:")
    print(f"     -> {SPOTWARE_PORTAL}")
    print("     After registering you will get:")
    print("        client_id     — Application identifier")
    print("        client_secret — Application secret")
    print()
    print("  C. An access_token generated via OAuth2 authorization flow:")
    print()
    print("     Step 1 — Open this URL in your browser:")
    print(f"       {OAUTH_AUTH_URL}?")
    print("         client_id=YOUR_CLIENT_ID")
    print("         &redirect_uri=https://localhost")
    print("         &scope=trading")
    print("         &response_type=code")
    print()
    print("     Step 2 — After authorizing, exchange the code for a token:")
    print(f"       POST {OAUTH_TOKEN_URL}")
    print("       Body: grant_type=authorization_code")
    print("             &code=AUTHORIZATION_CODE")
    print("             &redirect_uri=https://localhost")
    print("             &client_id=YOUR_CLIENT_ID")
    print("             &client_secret=YOUR_CLIENT_SECRET")
    print()
    print("     The response contains 'access_token'.")
    print()


def display_broker_menu() -> dict:
    print("Select your broker:")
    print()
    for key, broker in BROKERS.items():
        print(f"  [{key}] {broker['name']}")
        if broker["website"]:
            print(f"       Demo: {broker['website']}")
        print(f"       {broker['notes']}")
        print()

    while True:
        choice = input("Enter your choice [1-4]: ").strip()
        if choice in BROKERS:
            return BROKERS[choice]
        print("[ERROR] Invalid choice, enter 1-4")


# ---------------------------------------------------------------------------
# Credential input
# ---------------------------------------------------------------------------

def get_credentials(broker: dict) -> dict:
    print()
    print(f"[INPUT] Credentials for {broker['name']} cTrader DEMO:")
    print()
    print("  (Obtain these from the Spotware Developer Portal and OAuth2 flow)")
    print("  Run this script with --help to see the full OAuth2 guide.")
    print()

    account_number = input("  cTrader Account ID (numeric, e.g. 12345678): ").strip()
    client_id = input("  Application client_id: ").strip()
    client_secret = input("  Application client_secret: ").strip()
    access_token = input("  OAuth2 access_token: ").strip()

    if broker["broker_id"] == "custom":
        broker["name"] = input("  Broker display name: ").strip()
        broker["broker_id"] = broker["name"].lower().replace(" ", "_")

    return {
        "account_number": account_number,
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
    }


def validate_inputs(creds: dict) -> bool:
    """Basic sanity checks before hitting the network."""
    for field in ("account_number", "client_id", "client_secret", "access_token"):
        if not creds.get(field):
            print(f"[ERROR] Field '{field}' is required and cannot be empty.")
            return False
    if not creds["account_number"].isdigit():
        print("[ERROR] cTrader Account ID must be numeric.")
        return False
    return True


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection(account_id: str) -> bool:
    """Instantiate CTraderConnector and verify WebSocket handshake."""
    print()
    print("[CONNECT] Testing cTrader WebSocket connection...")

    try:
        import websockets  # noqa: F401 — ensure library available
    except ImportError:
        print("[ERROR] 'websockets' library not installed.")
        print("         Run: pip install websockets")
        return False

    storage = StorageManager()

    # Import here to avoid heavy import at module load
    from connectors.ctrader_connector import CTraderConnector  # noqa: PLC0415

    connector = CTraderConnector(storage=storage)

    if not connector.config.get("enabled"):
        print("[ERROR] Connector reports 'enabled=False'. Check that the account")
        print("         was saved correctly and that credentials are not empty.")
        return False

    success = connector.connect()

    if success:
        print()
        print("=" * 70)
        print("[OK] CONNECTION SUCCESSFUL!")
        print("=" * 70)
        print()
        print(f"   Account ID:   {connector.config.get('account_id')}")
        print(f"   Account name: {connector.config.get('account_name', 'N/A')}")
        print(f"   Account type: {connector.config.get('account_type', 'N/A')}")
        print(f"   Host:         {connector.config.get('host', 'N/A')}")
        print(f"   Latency:      {connector.get_latency():.1f} ms")
        print()
        connector.disconnect()
    else:
        print()
        print("[ERROR] WebSocket connection failed.")
        print()
        print("  Common causes:")
        print("  - Invalid or expired access_token (tokens typically expire in 1 hour)")
        print("  - Wrong client_id / client_secret")
        print("  - cTrader account not linked to the registered application")
        print("  - Network / firewall blocking port 5035")
        print()
        print("  Fix: re-generate access_token and run this script again.")

    return success


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def save_to_db(broker: dict, creds: dict) -> str:
    """Save broker account + credentials to DB (SSOT)."""
    print()
    print("[SAVE] Saving configuration to database...")

    storage = StorageManager()
    account_id = f"{broker['broker_id']}_ctrader_demo_20001"

    # 1. Broker account row
    storage.save_broker_account(
        account_id=account_id,
        broker_id=broker["broker_id"],
        platform_id="ctrader",
        account_name=f"{broker['name']} cTrader Demo",
        account_number=creds["account_number"],
        server=broker["server"],
        account_type="demo",
        enabled=True,
    )

    # 2. Encrypted credentials (access_token + OAuth app keys)
    storage.update_credential(
        account_id,
        {
            "access_token": creds["access_token"],
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
        },
    )

    print(f"[OK] Account saved in DB (ID: {account_id})")
    print("[OK] Credentials encrypted and stored in sys_credentials")
    return account_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up cTrader DEMO account in Aethelgard"
    )
    parser.add_argument(
        "--help-oauth",
        action="store_true",
        help="Print the full OAuth2 credential guide and exit",
    )
    args, _ = parser.parse_known_args()

    print_header()

    if args.help_oauth:
        print_oauth_guide()
        return

    # Brief OAuth2 reminder
    print("  NOTE: cTrader uses OAuth2. You need credentials from the Spotware")
    print("  Developer Portal BEFORE running this script.")
    print(f"  Run with --help-oauth to see the full guide.")
    print()

    # Step 1 — Select broker
    broker = display_broker_menu()

    # Step 2 — Enter credentials
    creds = get_credentials(broker)
    if not validate_inputs(creds):
        print("\n[ERROR] Setup cancelled due to invalid input.")
        return

    # Step 3 — Persist to DB first (so connector can load config)
    account_id = save_to_db(broker, creds)

    # Step 4 — Test connectivity
    ok = test_connection(account_id)

    if not ok:
        print("[WARN] Account saved in DB but connection test failed.")
        print("       Fix the credentials and re-run this script to update them.")
        print("       The account is saved as enabled=True — disable it if needed:")
        print(f"         storage.update_account_enabled('{account_id}', False)")
        return

    # Final summary
    print()
    print("=" * 70)
    print("[OK] cTrader SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("  Next steps:")
    print("    1. Start the system:   python start.py")
    print("    2. Open dashboard:     http://localhost:8000")
    print("    3. The scanner will prioritize cTrader as primary data provider")
    print("       (priority=100 > MT5 priority=70)")
    print()
    print("  NOTE: OAuth2 access_tokens expire (usually 1 hour).")
    print("  Refresh them and re-run this script when the token expires.")
    print()


if __name__ == "__main__":
    main()
