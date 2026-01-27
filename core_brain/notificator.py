"""
Sistema de Notificaciones de Telegram para Aethelgard
Envía alertas cuando el régimen cambia o se detecta una señal de Oliver Vélez
Soporta diferentes grupos según nivel de membresía (básico o premium)
"""
import logging
import asyncio
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum
import httpx

from models.signal import MarketRegime, Signal
from core_brain.module_manager import MembershipLevel

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Servicio de notificaciones de Telegram que envía alertas a diferentes grupos
    según el nivel de membresía del usuario
    """
    
    def __init__(self, 
                 bot_token: Optional[str] = None,
                 basic_chat_id: Optional[str] = None,
                 premium_chat_id: Optional[str] = None,
                 enabled: bool = True):
        """
        Inicializa el notificador de Telegram
        
        Args:
            bot_token: Token del bot de Telegram (obtenido de @BotFather)
            basic_chat_id: ID del chat/grupo para usuarios básicos
            premium_chat_id: ID del chat/grupo para usuarios premium
            enabled: Si las notificaciones están habilitadas
        """
        self.bot_token = bot_token
        self.basic_chat_id = basic_chat_id
        self.premium_chat_id = premium_chat_id
        self.enabled = enabled
        self.api_url = f"https://api.telegram.org/bot{bot_token}" if bot_token else None
        
        # Verificar configuración
        if enabled and not bot_token:
            logger.warning("Telegram notifier habilitado pero no se proporcionó bot_token")
        if enabled and not basic_chat_id and not premium_chat_id:
            logger.warning("Telegram notifier habilitado pero no se proporcionaron chat_ids")
    
    async def _send_message(self, 
                           chat_id: str, 
                           message: str, 
                           parse_mode: str = "HTML") -> bool:
        """
        Envía un mensaje a un chat de Telegram
        
        Args:
            chat_id: ID del chat destino
            message: Mensaje a enviar
            parse_mode: Modo de parseo (HTML o Markdown)
        
        Returns:
            True si se envió correctamente, False en caso contrario
        """
        if not self.enabled or not self.api_url or not chat_id:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode
                    }
                )
                response.raise_for_status()
                logger.debug(f"Mensaje enviado a chat {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error enviando mensaje a Telegram: {e}")
            return False
    
    async def notify_regime_change(self,
                                  symbol: str,
                                  previous_regime: Optional[MarketRegime],
                                  new_regime: MarketRegime,
                                  price: float,
                                  membership: MembershipLevel = MembershipLevel.BASIC,
                                  metrics: Optional[Dict] = None):
        """
        Envía una alerta cuando el régimen de mercado cambia
        
        Args:
            symbol: Símbolo del instrumento
            previous_regime: Régimen anterior
            new_regime: Nuevo régimen detectado
            price: Precio actual
            membership: Nivel de membresía del usuario
            metrics: Métricas adicionales (ADX, volatilidad, etc.)
        """
        if not self.enabled:
            return
        
        # Determinar chat_id según membresía
        chat_id = self.premium_chat_id if membership == MembershipLevel.PREMIUM else self.basic_chat_id
        
        if not chat_id:
            logger.warning(f"No hay chat_id configurado para membresía {membership.value}")
            return
        
        # Construir mensaje
        previous_str = previous_regime.value if previous_regime else "N/A"
        emoji = self._get_regime_emoji(new_regime)
        
        message = f"""
{emoji} <b>Cambio de Régimen Detectado</b>

📊 <b>Símbolo:</b> {symbol}
💰 <b>Precio:</b> {price:.2f}
🔄 <b>Cambio:</b> {previous_str} → {new_regime.value}

⏰ <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Añadir métricas para usuarios premium
        if membership == MembershipLevel.PREMIUM and metrics:
            adx = metrics.get('adx', 0)
            volatility = metrics.get('volatility', 0)
            bias = metrics.get('bias', 'N/A')
            
            message += f"""
📈 <b>Métricas Detalladas:</b>
• ADX: {adx:.2f}
• Volatilidad: {volatility:.4f}
• Sesgo: {bias}
"""
        
        await self._send_message(chat_id, message)
    
    async def notify_oliver_velez_signal(self,
                                        signal: Signal,
                                        membership: MembershipLevel = MembershipLevel.BASIC,
                                        strategy_details: Optional[Dict] = None):
        """
        Envía una alerta cuando se detecta una señal de Oliver Vélez
        
        Args:
            signal: Señal detectada
            membership: Nivel de membresía del usuario
            strategy_details: Detalles adicionales de la estrategia
        """
        if not self.enabled:
            return
        
        # Determinar chat_id según membresía
        chat_id = self.premium_chat_id if membership == MembershipLevel.PREMIUM else self.basic_chat_id
        
        if not chat_id:
            logger.warning(f"No hay chat_id configurado para membresía {membership.value}")
            return
        
        # Construir mensaje
        signal_emoji = "🟢" if signal.signal_type.value == "BUY" else "🔴"
        regime_emoji = self._get_regime_emoji(signal.regime) if signal.regime else "⚪"
        
        message = f"""
{signal_emoji} <b>Señal Oliver Vélez Detectada</b>

📊 <b>Símbolo:</b> {signal.symbol}
📈 <b>Tipo:</b> {signal.signal_type.value}
💰 <b>Precio:</b> {signal.price:.2f}
{regime_emoji} <b>Régimen:</b> {signal.regime.value if signal.regime else 'N/A'}

⏰ <b>Hora:</b> {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Añadir stop loss y take profit si están disponibles
        if signal.stop_loss or signal.take_profit:
            message += f"\n🛡️ <b>Gestión de Riesgo:</b>\n"
            if signal.stop_loss:
                message += f"• Stop Loss: {signal.stop_loss:.2f}\n"
            if signal.take_profit:
                message += f"• Take Profit: {signal.take_profit:.2f}\n"
        
        # Añadir detalles de estrategia para usuarios premium
        if membership == MembershipLevel.PREMIUM and strategy_details:
            message += f"\n📋 <b>Detalles de Estrategia:</b>\n"
            for key, value in strategy_details.items():
                message += f"• {key}: {value}\n"
        
        await self._send_message(chat_id, message)
    
    async def notify_system_alert(self,
                                 title: str,
                                 message: str,
                                 membership: MembershipLevel = MembershipLevel.PREMIUM,
                                 alert_type: str = "info"):
        """
        Envía una alerta del sistema (errores, modo seguridad, etc.)
        
        Args:
            title: Título de la alerta
            message: Mensaje de la alerta
            membership: Nivel de membresía (por defecto premium para alertas críticas)
            alert_type: Tipo de alerta (info, warning, error, critical)
        """
        if not self.enabled:
            return
        
        chat_id = self.premium_chat_id if membership == MembershipLevel.PREMIUM else self.basic_chat_id
        
        if not chat_id:
            return
        
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }.get(alert_type, "ℹ️")
        
        formatted_message = f"""
{emoji} <b>{title}</b>

{message}

⏰ <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        await self._send_message(chat_id, formatted_message)
    
    def _get_regime_emoji(self, regime: MarketRegime) -> str:
        """Retorna un emoji para cada tipo de régimen"""
        emoji_map = {
            MarketRegime.TREND: "📈",
            MarketRegime.RANGE: "↔️",
            MarketRegime.CRASH: "💥",
            MarketRegime.NORMAL: "⚪"
        }
        return emoji_map.get(regime, "⚪")
    
    def is_configured(self) -> bool:
        """Verifica si el notificador está correctamente configurado"""
        return bool(self.bot_token and (self.basic_chat_id or self.premium_chat_id))
    
    def set_enabled(self, enabled: bool):
        """Habilita o deshabilita las notificaciones"""
        self.enabled = enabled
        logger.info(f"Notificaciones de Telegram {'habilitadas' if enabled else 'deshabilitadas'}")


# Instancia global del notificador
_notifier_instance: Optional[TelegramNotifier] = None


def get_notifier() -> Optional[TelegramNotifier]:
    """Obtiene la instancia global del notificador"""
    return _notifier_instance


def initialize_notifier(bot_token: Optional[str] = None,
                       basic_chat_id: Optional[str] = None,
                       premium_chat_id: Optional[str] = None,
                       enabled: bool = True) -> TelegramNotifier:
    """
    Inicializa el notificador global
    
    Args:
        bot_token: Token del bot de Telegram
        basic_chat_id: ID del chat para usuarios básicos
        premium_chat_id: ID del chat para usuarios premium
        enabled: Si las notificaciones están habilitadas
    
    Returns:
        Instancia del notificador
    """
    global _notifier_instance
    _notifier_instance = TelegramNotifier(
        bot_token=bot_token,
        basic_chat_id=basic_chat_id,
        premium_chat_id=premium_chat_id,
        enabled=enabled
    )
    return _notifier_instance
