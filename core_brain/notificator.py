"""
Unified Notification Engine for Aethelgard
Manages multiple notification channels (Telegram, WhatsApp, Email) 
with database persistence and modular providers.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from models.signal import MarketRegime, Signal
from core_brain.module_manager import MembershipLevel
from data_vault.storage import StorageManager

from .notification_providers.telegram_provider import TelegramProvider
from .notification_providers.email_provider import EmailProvider
from .notification_providers.whatsapp_provider import WhatsAppProvider

logger = logging.getLogger(__name__)

class NotificationEngine:
    """
    Orchestrates notifications across multiple channels.
    Acts as a bridge between the system and specific providers.
    """
    
    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage or StorageManager()
        self.providers = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """
        Loads providers from database configuration.
        """
        try:
            settings = self.storage.get_all_notification_settings()
            # Map of provider names to classes
            provider_classes = {
                'telegram': TelegramProvider,
                'email': EmailProvider,
                'whatsapp': WhatsAppProvider
            }
            
            # If no settings in DB, try to create default telegram if possible (legacy support)
            if not settings:
                logger.debug("No notification settings found in DB. NotificationEngine waiting for configuration.")
            
            for setting in settings:
                name = setting['provider']
                if name in provider_classes:
                    config = setting.get('config', {})
                    config['enabled'] = setting.get('enabled', False)
                    self.providers[name] = provider_classes[name](config)
                    logger.info(f"Notification provider initialized: {name} (Enabled: {config['enabled']})")
                    
        except Exception as e:
            logger.error(f"Error initializing notification providers: {e}")

    async def notify_regime_change(self,
                                  symbol: str,
                                  previous_regime: Optional[MarketRegime],
                                  new_regime: MarketRegime,
                                  price: float,
                                  membership: MembershipLevel = MembershipLevel.BASIC,
                                  metrics: Optional[Dict] = None) -> None:
        """
        Broadcasts regime change alerts to all enabled channels.
        """
        previous_str = previous_regime.value if previous_regime else "N/A"
        emoji = self._get_regime_emoji(new_regime)
        
        title = f"{emoji} Cambio de Régimen Detectado"
        body = f"📊 Símbolo: {symbol}\n💰 Precio: {price:.2f}\n🔄 Cambio: {previous_str} → {new_regime.value}"
        
        if membership == MembershipLevel.PREMIUM and metrics:
            adx = metrics.get('adx', 0)
            volatility = metrics.get('volatility', 0)
            body += f"\n📈 ADX: {adx:.2f}\n🔍 Vol: {volatility:.4f}"

        await self._broadcast(title, body, membership=membership.value)

    async def notify_oliver_velez_signal(self,
                                        signal: Signal,
                                        membership: MembershipLevel = MembershipLevel.BASIC,
                                        strategy_details: Optional[Dict] = None) -> None:
        """
        Broadcasts trading signals to all enabled channels.
        """
        stype = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        signal_emoji = "🟢" if stype == "BUY" else "🔴"
        
        title = f"{signal_emoji} Señal Oliver Vélez Detectada"
        body = f"📊 Símbolo: {signal.symbol}\n📈 Tipo: {stype}\n💰 Precio: {signal.price:.5f}"
        
        if signal.stop_loss: body += f"\n🛑 SL: {signal.stop_loss:.5f}"
        if signal.take_profit: body += f"\n🎯 TP: {signal.take_profit:.5f}"

        await self._broadcast(title, body, membership=membership.value)

    async def notify_system_alert(self,
                                 title: str,
                                 message: str,
                                 membership: MembershipLevel = MembershipLevel.PREMIUM,
                                 alert_type: str = "info") -> None:
        """
        Broadcasts system alerts to all enabled channels.
        """
        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(alert_type, "ℹ️")
        full_title = f"{emoji} {title}"
        await self._broadcast(full_title, message, membership=membership.value)

    async def send_alert(self, message: str, title: str = "Aethelgard Alert") -> None:
        """Legacy compatibility method."""
        await self.notify_system_alert(title=title, message=message, alert_type="warning")

    async def _broadcast(self, title: str, body: str, **kwargs: Any) -> None:
        """
        Sends the notification to all active providers.
        """
        for name, provider in self.providers.items():
            if provider.enabled:
                await provider.send_alert(title, body, **kwargs)

    def _get_regime_emoji(self, regime: MarketRegime) -> str:
        emoji_map = {MarketRegime.TREND: "📈", MarketRegime.RANGE: "↔️", MarketRegime.CRASH: "💥"}
        return emoji_map.get(regime, "⚪")

    def is_configured(self) -> bool:
        return any(p.is_configured() for p in self.providers.values())

# Global singleton management
_engine_instance: Optional[NotificationEngine] = None

def get_notifier() -> Optional[NotificationEngine]:
    global _engine_instance
    if _engine_instance is None:
        # We try to initialize with default storage
        try:
            _engine_instance = NotificationEngine()
        except:
            return None
    return _engine_instance

def initialize_notifier(storage: Optional[StorageManager] = None) -> NotificationEngine:
    global _engine_instance
    _engine_instance = NotificationEngine(storage=storage)
    return _engine_instance
