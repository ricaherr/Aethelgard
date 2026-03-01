import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class SentimentService:
    """
    Institutional sentiment stream integration (lightweight by design).

    The service is API-first and can consume preprocessed events from external
    providers (RSS/Twitter/Bloomberg aggregators), while keeping a deterministic
    fallback classifier for resilience.
    """

    SOURCE_WEIGHTS = {
        "BLOOMBERG": 1.00,
        "REUTERS": 0.95,
        "WSJ": 0.90,
        "FED": 1.00,
        "ECB": 0.95,
        "BIS": 0.95,
        "RSS": 0.80,
        "TWITTER": 0.75,
        "X": 0.75,
    }

    BEARISH_KEYWORDS = {
        "rate hike": 0.95,
        "higher for longer": 0.95,
        "hawkish": 0.85,
        "tightening": 0.75,
        "quantitative tightening": 0.95,
        "liquidity drain": 0.90,
        "balance sheet reduction": 0.80,
        "credit stress": 0.75,
        "recession risk": 0.70,
        "emergency meeting": 0.70,
    }

    BULLISH_KEYWORDS = {
        "rate cut": 0.95,
        "dovish": 0.85,
        "liquidity injection": 0.95,
        "qe": 0.80,
        "quantitative easing": 0.90,
        "stimulus": 0.75,
        "soft landing": 0.70,
        "disinflation": 0.65,
        "pause cycle": 0.70,
    }

    MACRO_KEYWORDS = {
        "fed",
        "fomc",
        "powell",
        "ecb",
        "boe",
        "boj",
        "nfp",
        "cpi",
        "inflation",
        "rates",
        "central bank",
        "treasury",
    }

    def __init__(self, storage: StorageManager, http_timeout_seconds: float = 2.5):
        self.storage = storage
        self.http_timeout_seconds = max(0.5, float(http_timeout_seconds))
        logger.info("SentimentService initialized.")

    def _get_settings(self) -> Dict[str, Any]:
        """Load sentiment settings from dynamic_params (SSOT)."""
        defaults = {
            "enabled": True,
            "api_url": "",
            "api_token": "",
            "lookback_minutes": 240,
            "min_events_for_veto": 1,
            "high_probability_threshold": 0.75,
            "bearish_veto_threshold_pct": 80.0,
            "bullish_veto_threshold_pct": 80.0,
        }
        try:
            dynamic_params = self.storage.get_dynamic_params()
            if isinstance(dynamic_params, dict):
                sentiment_cfg = dynamic_params.get("sentiment_stream", {})
                if isinstance(sentiment_cfg, dict):
                    defaults.update(sentiment_cfg)
        except Exception as exc:
            logger.debug("Could not load sentiment settings from storage: %s", exc)
        return defaults

    def _normalize_source(self, source: str) -> str:
        src = (source or "RSS").strip().upper()
        if src in {"X", "TWITTER"}:
            return "TWITTER"
        return src

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse timestamp into UTC datetime."""
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _event_text(self, event: Dict[str, Any]) -> str:
        fields = [
            str(event.get("title", "")),
            str(event.get("headline", "")),
            str(event.get("summary", "")),
            str(event.get("body", "")),
        ]
        return " ".join(part for part in fields if part).strip()

    def _is_macro_event(self, text: str) -> bool:
        text_low = text.lower()
        return any(k in text_low for k in self.MACRO_KEYWORDS)

    def _score_keywords(self, text: str) -> Tuple[float, float]:
        """
        Returns tuple (bullish_score, bearish_score) from deterministic keyword scan.
        """
        text_low = text.lower()
        bullish = 0.0
        bearish = 0.0
        for key, weight in self.BULLISH_KEYWORDS.items():
            if key in text_low:
                bullish += weight
        for key, weight in self.BEARISH_KEYWORDS.items():
            if key in text_low:
                bearish += weight
        return bullish, bearish

    def _institutional_weight(self, event: Dict[str, Any]) -> float:
        source = self._normalize_source(str(event.get("source", "RSS")))
        base = self.SOURCE_WEIGHTS.get(source, 0.70)
        # Institutional handles can elevate social events.
        handle = str(event.get("handle", "")).lower()
        if source == "TWITTER" and any(k in handle for k in ("federalreserve", "ecb", "bloomberg", "reuters")):
            base = max(base, 0.90)
        if bool(event.get("verified", False)):
            base += 0.05
        return min(1.05, max(0.40, base))

    def fetch_external_events(self) -> List[Dict[str, Any]]:
        """Fetch events from external API if configured. Returns empty list on failure."""
        cfg = self._get_settings()
        api_url = str(cfg.get("api_url", "") or "").strip()
        if not api_url:
            return []

        headers = {"Accept": "application/json"}
        token = str(cfg.get("api_token", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            req = urllib.request.Request(api_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.http_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                return [e for e in payload if isinstance(e, dict)]
            if isinstance(payload, dict):
                events = payload.get("events", payload.get("data", []))
                if isinstance(events, list):
                    return [e for e in events if isinstance(e, dict)]
            return []
        except Exception as exc:
            logger.warning("Sentiment API fetch failed: %s", exc)
            return []

    def build_snapshot(self, events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Build aggregated institutional sentiment snapshot.
        """
        cfg = self._get_settings()
        enabled = bool(cfg.get("enabled", True))
        if not enabled:
            return {
                "enabled": False,
                "bias": "NEUTRAL",
                "bullish_pct": 50.0,
                "bearish_pct": 50.0,
                "events_considered": 0,
                "high_impact_macro": False,
                "drivers": [],
            }

        all_events = list(events or [])
        all_events.extend(self.fetch_external_events())

        lookback_minutes = int(cfg.get("lookback_minutes", 240))
        lookback_cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(5, lookback_minutes))

        bullish_power = 0.0
        bearish_power = 0.0
        high_impact_macro = False
        considered = 0
        drivers: List[Dict[str, Any]] = []

        for raw in all_events:
            text = self._event_text(raw)
            if not text:
                continue
            ts = self._parse_timestamp(raw.get("published_at") or raw.get("timestamp"))
            if ts < lookback_cutoff:
                continue

            bullish_score, bearish_score = self._score_keywords(text)
            if bullish_score == 0.0 and bearish_score == 0.0:
                continue

            considered += 1
            macro = self._is_macro_event(text)
            inst_weight = self._institutional_weight(raw)
            macro_weight = 1.20 if macro else 0.75
            total_weight = inst_weight * macro_weight

            weighted_bull = bullish_score * total_weight
            weighted_bear = bearish_score * total_weight
            bullish_power += weighted_bull
            bearish_power += weighted_bear

            impact = max(weighted_bull, weighted_bear)
            if macro and impact >= 1.2:
                high_impact_macro = True

            direction = "BULLISH" if weighted_bull >= weighted_bear else "BEARISH"
            drivers.append(
                {
                    "source": self._normalize_source(str(raw.get("source", "RSS"))),
                    "headline": text[:180],
                    "direction": direction,
                    "impact": round(impact, 3),
                }
            )

        directional_total = bullish_power + bearish_power
        if directional_total <= 0:
            bullish_pct = 50.0
            bearish_pct = 50.0
            bias = "NEUTRAL"
        else:
            bullish_pct = (bullish_power / directional_total) * 100.0
            bearish_pct = (bearish_power / directional_total) * 100.0
            if bullish_pct >= 55.0:
                bias = "BULLISH"
            elif bearish_pct >= 55.0:
                bias = "BEARISH"
            else:
                bias = "NEUTRAL"

        drivers_sorted = sorted(drivers, key=lambda d: d["impact"], reverse=True)[:3]
        return {
            "enabled": True,
            "bias": bias,
            "bullish_pct": round(bullish_pct, 2),
            "bearish_pct": round(bearish_pct, 2),
            "events_considered": considered,
            "high_impact_macro": high_impact_macro,
            "drivers": drivers_sorted,
        }

    def evaluate_trade_veto(
        self,
        symbol: str,
        side: str,
        confidence: float,
        events: Optional[List[Dict[str, Any]]] = None,
        trace_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Decide whether a trade should be vetoed by institutional sentiment.
        When vetoing, reason includes [SENTIMENT_VETO][Trace_ID: trace_id] when trace_id is set.
        """
        cfg = self._get_settings()
        snapshot = self.build_snapshot(events=events)
        trade_side = (side or "").upper()

        min_events = int(cfg.get("min_events_for_veto", 1))
        high_prob_threshold = float(cfg.get("high_probability_threshold", 0.75))
        bearish_veto_threshold = float(cfg.get("bearish_veto_threshold_pct", 80.0))
        bullish_veto_threshold = float(cfg.get("bullish_veto_threshold_pct", 80.0))

        if not snapshot.get("enabled", True):
            return True, "Sentiment stream disabled.", snapshot

        if snapshot.get("events_considered", 0) < min_events:
            return True, "Insufficient institutional sentiment events for veto.", snapshot

        if float(confidence) < high_prob_threshold:
            return True, "Signal confidence below high-probability veto threshold.", snapshot

        high_impact_macro = bool(snapshot.get("high_impact_macro", False))
        bearish_pct = float(snapshot.get("bearish_pct", 50.0))
        bullish_pct = float(snapshot.get("bullish_pct", 50.0))

        prefix = f"[SENTIMENT_VETO][Trace_ID: {trace_id}] " if trace_id else "Sentiment veto: "
        if trade_side == "BUY" and high_impact_macro and bearish_pct >= bearish_veto_threshold:
            reason = f"{prefix}Bearish Sentiment detected ({bearish_pct:.0f}%)."
            return False, reason, snapshot

        if trade_side == "SELL" and high_impact_macro and bullish_pct >= bullish_veto_threshold:
            reason = f"{prefix}Bullish Sentiment detected ({bullish_pct:.0f}%)."
            return False, reason, snapshot

        return True, "Institutional sentiment aligned or neutral.", snapshot
