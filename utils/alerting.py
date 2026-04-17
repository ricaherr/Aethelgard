"""
utils/alerting.py — Sistema de Alertas Operacionales
======================================================

Despacha alertas de eventos críticos a múltiples canales:
  - LOG_ONLY  : logging estructurado (siempre activo como fallback)
  - EMAIL     : SMTP con smtplib (configurable vía env vars / config dict)
  - TELEGRAM  : Bot API de Telegram (configurable vía token + chat_id)

Rate-limiting: máximo 1 alerta por (canal, clave) cada RATE_LIMIT_SECONDS.

Uso mínimo:
    from utils.alerting import AlertingService, Alert, AlertSeverity

    svc = AlertingService.from_env()
    svc.send_alert(Alert(
        severity=AlertSeverity.CRITICAL,
        key="db_degraded",
        title="DB Degradada",
        message="aethelgard.db marcada como DEGRADED tras recovery fallido",
    ))
"""

from __future__ import annotations

import logging
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tiempo mínimo entre alertas del mismo tipo por canal (segundos).
RATE_LIMIT_SECONDS: int = 300  # 5 minutos


class AlertSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertChannel(str, Enum):
    LOG_ONLY = "log_only"
    EMAIL = "email"
    TELEGRAM = "telegram"


class AlertEventType(str, Enum):
    """Tipos de eventos EDGE para trazabilidad de degradación granular."""
    EDGE_MODULE_DEGRADED = "EDGE_MODULE_DEGRADED"
    EDGE_MODULE_RESTORED = "EDGE_MODULE_RESTORED"
    EDGE_CLOSE_ONLY_ACTIVATED = "EDGE_CLOSE_ONLY_ACTIVATED"
    EDGE_CLOSE_ONLY_DEACTIVATED = "EDGE_CLOSE_ONLY_DEACTIVATED"


@dataclass
class Alert:
    """Representa un evento de alerta a despachar."""

    severity: AlertSeverity
    key: str          # Clave única para rate-limiting (ej. "db_degraded:aethelgard.db")
    title: str
    message: str
    db_path: str = ""
    component: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailConfig:
    """Configuración SMTP para envío de alertas por correo."""

    smtp_host: str
    smtp_port: int
    sender: str
    recipients: List[str]
    username: str = ""
    password: str = ""
    use_tls: bool = True


@dataclass
class TelegramConfig:
    """Configuración de Bot API de Telegram."""

    bot_token: str
    chat_id: str


class AlertingService:
    """
    Servicio de alertas operacionales multi-canal con rate-limiting.

    Instanciar vía AlertingService.from_env() para cargar config desde
    variables de entorno, o vía constructor directo con config dict.
    """

    def __init__(
        self,
        channels: Optional[List[AlertChannel]] = None,
        email_config: Optional[EmailConfig] = None,
        telegram_config: Optional[TelegramConfig] = None,
    ) -> None:
        self._channels: List[AlertChannel] = channels or [AlertChannel.LOG_ONLY]
        self._email_config = email_config
        self._telegram_config = telegram_config
        # key: f"{channel.value}:{alert.key}" → last_sent_ts
        self._rate_limit_cache: Dict[str, float] = {}

    @classmethod
    def from_env(cls) -> "AlertingService":
        """
        Construye el servicio leyendo variables de entorno.

        Variables soportadas:
          ALERT_CHANNELS         : comma-separated list (log_only,email,telegram)
          ALERT_SMTP_HOST        : SMTP host
          ALERT_SMTP_PORT        : SMTP port (default 587)
          ALERT_SMTP_SENDER      : remitente
          ALERT_SMTP_RECIPIENTS  : comma-separated lista de destinatarios
          ALERT_SMTP_USERNAME    : usuario SMTP (opcional)
          ALERT_SMTP_PASSWORD    : contraseña SMTP (opcional)
          ALERT_TELEGRAM_TOKEN   : Bot token
          ALERT_TELEGRAM_CHAT_ID : Chat/channel ID
        """
        import os

        raw_channels = os.getenv("ALERT_CHANNELS", "log_only").split(",")
        channels: List[AlertChannel] = []
        for c in raw_channels:
            try:
                channels.append(AlertChannel(c.strip().lower()))
            except ValueError:
                logger.warning("[AlertingService] Canal desconocido ignorado: %s", c.strip())

        email_config: Optional[EmailConfig] = None
        if AlertChannel.EMAIL in channels:
            smtp_host = os.getenv("ALERT_SMTP_HOST", "")
            smtp_recipients_raw = os.getenv("ALERT_SMTP_RECIPIENTS", "")
            if smtp_host and smtp_recipients_raw:
                email_config = EmailConfig(
                    smtp_host=smtp_host,
                    smtp_port=int(os.getenv("ALERT_SMTP_PORT", "587")),
                    sender=os.getenv("ALERT_SMTP_SENDER", "aethelgard@noreply.local"),
                    recipients=[r.strip() for r in smtp_recipients_raw.split(",")],
                    username=os.getenv("ALERT_SMTP_USERNAME", ""),
                    password=os.getenv("ALERT_SMTP_PASSWORD", ""),
                    use_tls=os.getenv("ALERT_SMTP_TLS", "true").lower() == "true",
                )
            else:
                logger.warning("[AlertingService] EMAIL configurado pero SMTP_HOST/RECIPIENTS vacíos — usando LOG_ONLY")
                channels = [c for c in channels if c != AlertChannel.EMAIL]

        telegram_config: Optional[TelegramConfig] = None
        if AlertChannel.TELEGRAM in channels:
            token = os.getenv("ALERT_TELEGRAM_TOKEN", "")
            chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
            if token and chat_id:
                telegram_config = TelegramConfig(bot_token=token, chat_id=chat_id)
            else:
                logger.warning("[AlertingService] TELEGRAM configurado pero TOKEN/CHAT_ID vacíos — usando LOG_ONLY")
                channels = [c for c in channels if c != AlertChannel.TELEGRAM]

        if not channels:
            channels = [AlertChannel.LOG_ONLY]

        return cls(
            channels=channels,
            email_config=email_config,
            telegram_config=telegram_config,
        )

    def send_alert(self, alert: Alert) -> Dict[str, bool]:
        """
        Despacha una alerta a todos los canales configurados.

        Aplica rate-limiting por (canal, alert.key).
        Siempre loguea (fallback) aunque los canales externos fallen.

        Returns:
            Dict canal → bool indicando si fue enviada (True) o saltada/fallida (False).
        """
        results: Dict[str, bool] = {}
        for channel in self._channels:
            rate_key = f"{channel.value}:{alert.key}"
            if self._is_rate_limited(rate_key):
                logger.debug(
                    "[AlertingService] Rate-limited: canal=%s key=%s", channel.value, alert.key
                )
                results[channel.value] = False
                continue

            sent = self._dispatch_to_channel(channel, alert)
            if sent:
                self._mark_sent(rate_key)
            results[channel.value] = sent

        return results

    def _dispatch_to_channel(self, channel: AlertChannel, alert: Alert) -> bool:
        """Despacha al canal indicado. Retorna True si fue enviada."""
        if channel == AlertChannel.LOG_ONLY:
            return self._send_log(alert)
        if channel == AlertChannel.EMAIL:
            return self._send_email(alert)
        if channel == AlertChannel.TELEGRAM:
            return self._send_telegram(alert)
        return False

    def _send_log(self, alert: Alert) -> bool:
        """Loguea la alerta estructuradamente."""
        log_fn = logger.error if alert.severity == AlertSeverity.CRITICAL else logger.warning
        log_fn(
            "[ALERT] severity=%s key=%s title=%s db_path=%s message=%s",
            alert.severity.value,
            alert.key,
            alert.title,
            alert.db_path,
            alert.message,
        )
        return True

    def _send_email(self, alert: Alert) -> bool:
        """Envía la alerta por correo SMTP. Retorna True si tuvo éxito."""
        cfg = self._email_config
        if cfg is None:
            logger.error("[AlertingService] _send_email llamado sin EmailConfig")
            return False

        subject = f"[Aethelgard {alert.severity.value}] {alert.title}"
        body = (
            f"Severity : {alert.severity.value}\n"
            f"Key      : {alert.key}\n"
            f"DB Path  : {alert.db_path}\n"
            f"Component: {alert.component}\n"
            f"Timestamp: {alert.timestamp}\n\n"
            f"{alert.message}\n"
        )
        if alert.extra:
            body += f"\nExtra: {alert.extra}"

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = cfg.sender
        msg["To"] = ", ".join(cfg.recipients)

        try:
            smtp_cls = smtplib.SMTP_SSL if not cfg.use_tls else smtplib.SMTP
            with smtp_cls(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:  # type: ignore[operator]
                if cfg.use_tls:
                    server.starttls()
                if cfg.username:
                    server.login(cfg.username, cfg.password)
                server.sendmail(cfg.sender, cfg.recipients, msg.as_string())
            logger.info("[AlertingService] Email enviado: %s → %s", subject, cfg.recipients)
            return True
        except Exception as exc:
            logger.error("[AlertingService] Error enviando email: %s", exc)
            return False

    def _send_telegram(self, alert: Alert) -> bool:
        """Envía la alerta al chat de Telegram. Retorna True si tuvo éxito."""
        cfg = self._telegram_config
        if cfg is None:
            logger.error("[AlertingService] _send_telegram llamado sin TelegramConfig")
            return False

        emoji = "🚨" if alert.severity == AlertSeverity.CRITICAL else "⚠️"
        text = (
            f"{emoji} *{alert.title}*\n"
            f"`{alert.key}`\n\n"
            f"{alert.message}\n\n"
            f"DB: `{alert.db_path}`\n"
            f"Timestamp: `{alert.timestamp}`"
        )

        try:
            import urllib.request, urllib.parse, json as _json  # noqa: E401

            payload = _json.dumps({
                "chat_id": cfg.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }).encode("utf-8")
            url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("[AlertingService] Telegram enviado: %s", alert.title)
                    return True
                logger.warning("[AlertingService] Telegram resp status: %s", resp.status)
                return False
        except Exception as exc:
            logger.error("[AlertingService] Error enviando Telegram: %s", exc)
            return False

    def _is_rate_limited(self, rate_key: str) -> bool:
        """Retorna True si la alerta fue enviada hace menos de RATE_LIMIT_SECONDS."""
        last_ts = self._rate_limit_cache.get(rate_key, 0.0)
        return (time.monotonic() - last_ts) < RATE_LIMIT_SECONDS

    def _mark_sent(self, rate_key: str) -> None:
        """Registra la hora de envío para rate-limiting."""
        self._rate_limit_cache[rate_key] = time.monotonic()

    def get_rate_limit_state(self) -> Dict[str, float]:
        """Retorna snapshot del estado de rate-limiting (para observabilidad)."""
        now = time.monotonic()
        return {
            key: max(0.0, RATE_LIMIT_SECONDS - (now - ts))
            for key, ts in self._rate_limit_cache.items()
        }

    def send_edge_event(
        self,
        event_type: AlertEventType,
        module: str,
        message: str,
        component: str = "ResilienceManager",
    ) -> Dict[str, bool]:
        """
        Despacha una alerta de evento EDGE de degradación/restauración.

        Convenience wrapper sobre send_alert para eventos ResilienceManager.

        Args:
            event_type: Tipo de evento (degradación, restauración, close-only).
            module: Nombre del módulo afectado (ej. "SignalFactory").
            message: Descripción humana del evento.
            component: Componente que origina el evento.

        Returns:
            Dict canal → bool, igual que send_alert.
        """
        severity = (
            AlertSeverity.CRITICAL
            if event_type in (
                AlertEventType.EDGE_MODULE_DEGRADED,
                AlertEventType.EDGE_CLOSE_ONLY_ACTIVATED,
            )
            else AlertSeverity.WARNING
        )
        alert = Alert(
            severity=severity,
            key=f"{event_type.value}:{module}",
            title=f"[EDGE] {event_type.value} — {module}",
            message=message,
            component=component,
        )
        return self.send_alert(alert)
