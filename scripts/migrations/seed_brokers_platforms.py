"""
Seed Initial Data: Platforms and Brokers
Populates database with common trading platforms and brokers
"""
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_platforms():
    """Seed common trading platforms"""
    storage = StorageManager()
    
    platforms = [
        {
            "platform_id": "mt5",
            "name": "MetaTrader 5",
            "vendor": "MetaQuotes Software Corp.",
            "type": "desktop",
            "capabilities": ["forex", "cfd", "futures", "stocks"],
            "connector_class": "connectors.mt5_connector.MT5Connector"
        },
        {
            "platform_id": "mt4",
            "name": "MetaTrader 4",
            "vendor": "MetaQuotes Software Corp.",
            "type": "desktop",
            "capabilities": ["forex", "cfd"],
            "connector_class": "connectors.mt4_connector.MT4Connector"
        },
        {
            "platform_id": "nt8",
            "name": "NinjaTrader 8",
            "vendor": "NinjaTrader LLC",
            "type": "desktop",
            "capabilities": ["futures", "forex", "stocks"],
            "connector_class": "connectors.nt8_connector.NT8Connector"
        },
        {
            "platform_id": "tradingview",
            "name": "TradingView",
            "vendor": "TradingView Inc.",
            "type": "web",
            "capabilities": ["forex", "crypto", "stocks", "futures"],
            "connector_class": "connectors.webhook_tv.TradingViewWebhook"
        },
        {
            "platform_id": "binance_api",
            "name": "Binance API",
            "vendor": "Binance",
            "type": "api",
            "capabilities": ["crypto", "spot", "futures", "margin"],
            "connector_class": "connectors.binance_connector.BinanceConnector"
        },
        {
            "platform_id": "ibkr_api",
            "name": "Interactive Brokers API",
            "vendor": "Interactive Brokers",
            "type": "api",
            "capabilities": ["stocks", "options", "futures", "forex", "bonds"],
            "connector_class": "connectors.ibkr_connector.IBKRConnector"
        },
        {
            "platform_id": "ctrader",
            "name": "cTrader",
            "vendor": "Spotware Systems",
            "type": "desktop",
            "capabilities": ["forex", "cfd"],
            "connector_class": "connectors.ctrader_connector.CTraderConnector"
        }
    ]
    
    for platform in platforms:
        storage.save_platform(platform)
        logger.info(f"✅ Platform: {platform['name']}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Platforms seeded: {len(platforms)}")


def seed_brokers():
    """Seed common brokers"""
    storage = StorageManager()
    
    brokers = [
        {
            "broker_id": "pepperstone",
            "name": "Pepperstone",
            "type": "forex",
            "website": "https://pepperstone.com",
            "platforms_available": ["mt5", "mt4", "ctrader"],
            "data_server": "Pepperstone-Demo",
            "auto_provision_available": False,
            "registration_url": "https://pepperstone.com/en/demo-account"
        },
        {
            "broker_id": "ic_markets",
            "name": "IC Markets",
            "type": "forex",
            "website": "https://www.icmarkets.com",
            "platforms_available": ["mt5", "mt4", "ctrader"],
            "data_server": "ICMarketsSC-Demo",
            "auto_provision_available": False,
            "registration_url": "https://www.icmarkets.com/demo-trading-account/"
        },
        {
            "broker_id": "xm",
            "name": "XM Global",
            "type": "forex",
            "website": "https://www.xm.com",
            "platforms_available": ["mt5", "mt4"],
            "data_server": "XMGlobal-Demo",
            "auto_provision_available": False,
            "registration_url": "https://www.xm.com/demo-account"
        },
        {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "website": "https://www.binance.com",
            "platforms_available": ["binance_api"],
            "data_server": "https://api.binance.com",
            "auto_provision_available": True,  # Testnet supports auto-provision
            "registration_url": "https://www.binance.com/en/register"
        },
        {
            "broker_id": "interactive_brokers",
            "name": "Interactive Brokers",
            "type": "multi_asset",
            "website": "https://www.interactivebrokers.com",
            "platforms_available": ["ibkr_api"],
            "data_server": "https://api.ibkr.com",
            "auto_provision_available": False,
            "registration_url": "https://www.interactivebrokers.com/en/trading/free-trial.php"
        },
        {
            "broker_id": "amp_futures",
            "name": "AMP Futures",
            "type": "futures",
            "website": "https://ampfutures.com",
            "platforms_available": ["nt8"],
            "data_server": "Rithmic Paper Trading",
            "auto_provision_available": False,
            "registration_url": "https://ampfutures.com/demo-account/"
        },
        {
            "broker_id": "tradovate",
            "name": "Tradovate",
            "type": "futures",
            "website": "https://www.tradovate.com",
            "platforms_available": ["tradovate_api", "nt8"],
            "data_server": "https://demo.tradovateapi.com",
            "auto_provision_available": True,  # Free demo available
            "registration_url": "https://www.tradovate.com/welcome"
        }
    ]
    
    for broker in brokers:
        storage.save_broker(broker)
        auto_icon = "🤖" if broker['auto_provision_available'] else "👤"
        logger.info(f"✅ {auto_icon} Broker: {broker['name']:25} - {broker['type']:12} - Platforms: {len(broker['platforms_available'])}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Brokers seeded: {len(brokers)}")
    
    # Statistics
    auto_provision = sum(1 for b in brokers if b['auto_provision_available'])
    logger.info(f"Auto-Provision Available: {auto_provision}/{len(brokers)}")


if __name__ == "__main__":
    logger.info("="*50)
    logger.info("SEEDING INITIAL DATA")
    logger.info("="*50)
    
    logger.info("\n1. Seeding Platforms...")
    seed_platforms()
    
    logger.info("\n2. Seeding Brokers...")
    seed_brokers()
    
    logger.info("\n" + "="*50)
    logger.info("✅ SEED COMPLETE")
    logger.info("="*50)
    
    # Verify
    storage = StorageManager()
    platforms = storage.get_platforms()
    brokers = storage.get_brokers()
    
    logger.info(f"\nDatabase now contains:")
    logger.info(f"  - {len(platforms)} Platforms")
    logger.info(f"  - {len(brokers)} Brokers")
    logger.info(f"\nNext step: Configure accounts in Dashboard")
