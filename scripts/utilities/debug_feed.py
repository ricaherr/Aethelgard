
import requests
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api/signals"

def check_modules_state() -> None:
    logger.info("Testing /api/signals endpoint...")

    # mimic the dashboard default calls
    # 1. Default call (no params, implicitly limit=100, minutes=10080, status=PENDING,EXECUTED,EXPIRED)
    try:
        response = requests.get(BASE_URL)
        if response.status_code == 200:
            data = response.json()
            signals = data.get("signals", [])
            logger.info(f"Default call returned {len(signals)} signals.")
            
            if signals:
                first_sig = signals[0]
                last_sig = signals[-1]
                logger.info(f"First signal (Newest): {first_sig.get('timestamp')} | Score: {first_sig.get('score')}")
                logger.info(f"Last signal (Oldest of 100): {last_sig.get('timestamp')} | Score: {last_sig.get('score')}")
                
            # Check for high score signals
            high_score_signals = [s for s in signals if s.get('score', 0) >= 0.70]
            logger.info(f"Found {len(high_score_signals)} signals with score >= 0.70 in default call.")

        else:
            logger.error(f"Default call failed: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error calling API: {e}")

    # 2. Call with explicit params matching SignalFeed.tsx defaults or potential user filters
    # User mentioned "Feed" option in "Analysis".
    # SignalFeed.tsx logic: minutes=43200 (if no time filter), status (if filtered)
    
    logger.info("\nTesting with typical Feed params (minutes=43200, status=PENDING,EXECUTED,EXPIRED)...")
    params = {
        "minutes": 43200,
        "limit": 100,
        "status": "PENDING,EXECUTED,EXPIRED"
    }
    try:
        response = requests.get(BASE_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            signals = data.get("signals", [])
            logger.info(f"Feed call returned {len(signals)} signals.")
            
            high_score_signals = [s for s in signals if s.get('score', 0) >= 0.70]
            logger.info(f"Found {len(high_score_signals)} signals with score >= 0.70 in Feed call.")
             
            if high_score_signals:
                logger.info("Top 5 High Score Signals:")
                for s in high_score_signals[:5]:
                    logger.info(f"  - ID: {s['id']} | {s['symbol']} | {s['status']} | Score: {s['score']}")
            else:
                logger.warning("No high score signals found via API despite DB having them!")

    except Exception as e:
        logger.error(f"Error calling API with params: {e}")

if __name__ == "__main__":
    test_feed_signals()
