from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BaseNotificationProvider(ABC):
    """
    Base class for all notification providers (Telegram, WhatsApp, Email).
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', False)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def send_message(self, message: str, **kwargs) -> bool:
        """
        Send a generic message.
        """
        pass

    @abstractmethod
    async def send_alert(self, title: str, body: str, **kwargs) -> bool:
        """
        Send a formatted alert with title and body.
        """
        pass

    def is_configured(self) -> bool:
        """
        Check if the provider has all required configuration.
        """
        return True
