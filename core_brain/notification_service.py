"""
Notification Service - Sistema de notificaciones contextuales EDGE

Este servicio genera notificaciones inteligentes basadas en el contexto del usuario
y su nivel de autonomía configurado.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationCategory(str, Enum):
    """Categorías de notificaciones"""
    SIGNAL = "signal"
    EXECUTION = "execution"
    RISK = "risk"
    REGIME = "regime"
    POSITION = "position"
    SYSTEM = "system"


class NotificationPriority(str, Enum):
    """Prioridades de notificaciones"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationService:
    """
    Servicio de notificaciones contextuales que adapta mensajes según
    el perfil y configuración de autonomía del usuario.
    """
    
    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: Instancia de StorageManager para acceder a preferencias
        """
        self.storage = storage_manager
        self.notifications = []  # Buffer en memoria
        logger.info("NotificationService initialized")
    
    def create_notification(
        self,
        category: NotificationCategory,
        context: Dict[str, Any],
        user_id: str = 'default'
    ) -> Optional[Dict[str, Any]]:
        """
        Crea una notificación contextual basada en las preferencias del usuario.
        
        Args:
            category: Categoría de la notificación
            context: Contexto específico (señal, ejecución, riesgo, etc.)
            user_id: ID del usuario
            
        Returns:
            Dict con la notificación o None si no debe notificarse
        """
        # Obtener preferencias del usuario
        prefs = self.storage.get_user_preferences(user_id)
        if not prefs:
            logger.warning(f"No preferences found for user {user_id}, using defaults")
            prefs = self.storage.get_default_profile('active_trader')
        
        # Verificar si debe notificar según preferencias
        if not self._should_notify(category, context, prefs):
            return None
        
        # Generar notificación contextual
        notification = self._generate_notification(category, context, prefs)
        
        if notification:
            # Agregar a buffer
            self.notifications.append(notification)
            logger.info(f"Notification created: {category.value} - {notification['title']}")
        
        return notification
    
    def _should_notify(
        self,
        category: NotificationCategory,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> bool:
        """Determina si debe notificar según preferencias del usuario."""
        
        # Riesgos SIEMPRE se notifican
        if category == NotificationCategory.RISK:
            return prefs.get('notify_risks', True)
        
        # Señales: solo si auto-trading OFF
        if category == NotificationCategory.SIGNAL:
            if prefs.get('auto_trading_enabled', False):
                return False  # No notificar señales si auto-trading activo
            
            # Verificar umbral de score
            score = context.get('score', 0)
            threshold = prefs.get('notify_threshold_score', 0.85)
            return score >= threshold and prefs.get('notify_signals', True)
        
        # Ejecuciones: solo si auto-trading ON
        if category == NotificationCategory.EXECUTION:
            if not prefs.get('auto_trading_enabled', False):
                return False  # No notificar ejecuciones si auto-trading inactivo
            return prefs.get('notify_executions', True)
        
        # Cambios de régimen
        if category == NotificationCategory.REGIME:
            return prefs.get('notify_regime_changes', True)
        
        # Por defecto, notificar
        return True
    
    def _generate_notification(
        self,
        category: NotificationCategory,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Genera el contenido de la notificación según categoría y contexto."""
        
        if category == NotificationCategory.SIGNAL:
            return self._notification_signal_detected(context, prefs)
        elif category == NotificationCategory.EXECUTION:
            return self._notification_execution(context, prefs)
        elif category == NotificationCategory.RISK:
            return self._notification_risk(context, prefs)
        elif category == NotificationCategory.REGIME:
            return self._notification_regime_change(context, prefs)
        elif category == NotificationCategory.POSITION:
            return self._notification_position(context, prefs)
        elif category == NotificationCategory.SYSTEM:
            return self._notification_system(context, prefs)
        
        return None
    
    def _notification_signal_detected(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de señal detectada (auto-trading OFF)."""
        
        symbol = context.get('symbol', 'UNKNOWN')
        direction = context.get('direction', 'UNKNOWN')
        score = context.get('score', 0)
        timeframe = context.get('timeframe', 'M5')
        strategy = context.get('strategy', 'Unknown')
        entry = context.get('entry_price', 0)
        sl = context.get('sl', 0)
        tp = context.get('tp', 0)
        
        return {
            'id': f"signal_{datetime.now().timestamp()}",
            'category': NotificationCategory.SIGNAL.value,
            'priority': NotificationPriority.HIGH.value,
            'title': 'SETUP DETECTADO - ACCIÓN MANUAL REQUERIDA',
            'message': f"{symbol} • {timeframe} • {strategy}\nDirección: {direction} • Probabilidad: {score:.0%}",
            'details': {
                'symbol': symbol,
                'direction': direction,
                'score': score,
                'timeframe': timeframe,
                'strategy': strategy,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'r_r': context.get('r_r', 0)
            },
            'actions': [
                {'label': 'Ejecutar', 'action': 'execute_signal'},
                {'label': 'Ver Chart', 'action': 'view_chart'},
                {'label': 'Análisis', 'action': 'view_analysis'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_execution(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de ejecución automática (auto-trading ON)."""
        
        symbol = context.get('symbol', 'UNKNOWN')
        direction = context.get('direction', 'UNKNOWN')
        ticket = context.get('ticket', 'N/A')
        entry = context.get('entry_price', 0)
        sl = context.get('sl', 0)
        tp = context.get('tp', 0)
        volume = context.get('volume', 0)
        risk_usd = context.get('risk_usd', 0)
        score = context.get('score', 0)
        
        return {
            'id': f"execution_{ticket}",
            'category': NotificationCategory.EXECUTION.value,
            'priority': NotificationPriority.HIGH.value,
            'title': 'POSICIÓN ABIERTA - EJECUCIÓN AUTOMÁTICA',
            'message': f"{symbol} {direction} • Ticket: #{ticket}\nEntry: {entry} • SL: {sl} • TP: {tp}",
            'details': {
                'symbol': symbol,
                'direction': direction,
                'ticket': ticket,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'volume': volume,
                'risk_usd': risk_usd,
                'score': score
            },
            'actions': [
                {'label': 'Monitor', 'action': 'monitor_position'},
                {'label': 'Trace', 'action': 'view_trace'},
                {'label': 'Cerrar', 'action': 'close_position'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_risk(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de riesgo detectado."""
        
        risk_type = context.get('risk_type', 'unknown')
        auto_adjust_enabled = prefs.get('auto_trading_enabled', False)
        
        if risk_type == 'drawdown':
            return self._notification_risk_drawdown(context, auto_adjust_enabled)
        elif risk_type == 'exposure':
            return self._notification_risk_exposure(context, auto_adjust_enabled)
        elif risk_type == 'consecutive_losses':
            return self._notification_risk_consecutive_losses(context, auto_adjust_enabled)
        
        return None
    
    def _notification_risk_drawdown(
        self,
        context: Dict[str, Any],
        auto_adjust: bool
    ) -> Dict[str, Any]:
        """Notificación de drawdown excesivo."""
        
        current_dd = context.get('current_drawdown', 0)
        limit_dd = context.get('limit_drawdown', 5.0)
        actions_taken = context.get('actions_taken', [])
        
        if auto_adjust:
            title = 'GESTIÓN DE RIESGO - AJUSTE AUTOMÁTICO'
            message = f"Drawdown detectado: {current_dd:.1f}% (límite: {limit_dd:.1f}%)\n"
            message += "Acciones tomadas automáticamente:\n" + "\n".join(f"✅ {a}" for a in actions_taken)
        else:
            title = 'ALERTA DE RIESGO - REVISIÓN REQUERIDA'
            message = f"Drawdown actual: {current_dd:.1f}% (límite: {limit_dd:.1f}%)\n"
            message += "Auto-trading PAUSADO por seguridad"
        
        return {
            'id': f"risk_dd_{datetime.now().timestamp()}",
            'category': NotificationCategory.RISK.value,
            'priority': NotificationPriority.CRITICAL.value,
            'title': title,
            'message': message,
            'details': context,
            'actions': [
                {'label': 'Ver Dashboard', 'action': 'view_dashboard'},
                {'label': 'Ajustar Config', 'action': 'adjust_config'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_risk_exposure(
        self,
        context: Dict[str, Any],
        auto_adjust: bool
    ) -> Dict[str, Any]:
        """Notificación de exposición total elevada."""
        
        total_risk = context.get('total_risk', 0)
        limit_risk = context.get('limit_risk', 10.0)
        open_positions = context.get('open_positions', 0)
        
        return {
            'id': f"risk_exposure_{datetime.now().timestamp()}",
            'category': NotificationCategory.RISK.value,
            'priority': NotificationPriority.HIGH.value,
            'title': 'EXPOSICIÓN TOTAL ELEVADA',
            'message': f"Riesgo agregado: {total_risk:.1f}% (límite: {limit_risk:.1f}%)\nPosiciones abiertas: {open_positions} trades",
            'details': context,
            'actions': [
                {'label': 'Ver Posiciones', 'action': 'view_positions'},
                {'label': 'Ajustar Límites', 'action': 'adjust_limits'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_risk_consecutive_losses(
        self,
        context: Dict[str, Any],
        auto_adjust: bool
    ) -> Dict[str, Any]:
        """Notificación de pérdidas consecutivas."""
        
        consecutive = context.get('consecutive_losses', 0)
        pattern = context.get('pattern_detected', 'Unknown')
        
        if auto_adjust:
            title = 'RACHA PERDEDORA - AJUSTE AUTOMÁTICO'
            message = f"{consecutive} pérdidas consecutivas detectadas\nPatrón: {pattern}\nSistema ajustado automáticamente"
        else:
            title = 'RACHA PERDEDORA DETECTADA'
            message = f"{consecutive} pérdidas consecutivas\nPatrón: {pattern}\nRevisión recomendada"
        
        return {
            'id': f"risk_losses_{datetime.now().timestamp()}",
            'category': NotificationCategory.RISK.value,
            'priority': NotificationPriority.HIGH.value,
            'title': title,
            'message': message,
            'details': context,
            'actions': [
                {'label': 'Análisis', 'action': 'view_analysis'},
                {'label': 'Pausar Trading', 'action': 'pause_trading'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_regime_change(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de cambio de régimen de mercado."""
        
        symbol = context.get('symbol', 'UNKNOWN')
        old_regime = context.get('old_regime', 'UNKNOWN')
        new_regime = context.get('new_regime', 'UNKNOWN')
        auto_adjust = prefs.get('auto_trading_enabled', False)
        actions_taken = context.get('actions_taken', [])
        
        if auto_adjust and actions_taken:
            title = 'CAMBIO DE RÉGIMEN - ADAPTACIÓN AUTOMÁTICA'
            message = f"{symbol}: {old_regime} → {new_regime}\n"
            message += "Ajustes aplicados:\n" + "\n".join(f"✅ {a}" for a in actions_taken)
        else:
            title = 'CAMBIO DE RÉGIMEN DETECTADO'
            message = f"{symbol}: {old_regime} → {new_regime}"
        
        return {
            'id': f"regime_{symbol}_{datetime.now().timestamp()}",
            'category': NotificationCategory.REGIME.value,
            'priority': NotificationPriority.MEDIUM.value,
            'title': title,
            'message': message,
            'details': context,
            'actions': [
                {'label': 'Ver Análisis', 'action': 'view_analysis'},
                {'label': 'Ajustar Config', 'action': 'adjust_config'}
            ],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_position(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de gestión de posiciones."""
        
        event_type = context.get('event_type', 'unknown')
        
        if event_type == 'trailing_stop':
            title = 'TRAILING STOP ACTIVADO'
        elif event_type == 'partial_tp':
            title = 'TAKE PROFIT PARCIAL EJECUTADO'
        elif event_type == 'breakeven':
            title = 'TRADE RISK-FREE'
        elif event_type == 'at_risk':
            title = 'POSICIÓN EN ZONA DE RIESGO'
        else:
            title = 'ACTUALIZACIÓN DE POSICIÓN'
        
        return {
            'id': f"position_{context.get('ticket')}_{datetime.now().timestamp()}",
            'category': NotificationCategory.POSITION.value,
            'priority': NotificationPriority.MEDIUM.value,
            'title': title,
            'message': context.get('message', ''),
            'details': context,
            'actions': context.get('actions', []),
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def _notification_system(
        self,
        context: Dict[str, Any],
        prefs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notificación de sistema."""
        
        return {
            'id': f"system_{datetime.now().timestamp()}",
            'category': NotificationCategory.SYSTEM.value,
            'priority': context.get('priority', NotificationPriority.MEDIUM.value),
            'title': context.get('title', 'ACTUALIZACIÓN DEL SISTEMA'),
            'message': context.get('message', ''),
            'details': context,
            'actions': context.get('actions', []),
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
    
    def get_unread_notifications(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """Retorna notificaciones no leídas del usuario."""
        return [n for n in self.notifications if not n.get('read', False)]
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Marca una notificación como leída."""
        for notification in self.notifications:
            if notification['id'] == notification_id:
                notification['read'] = True
                return True
        return False
    
    def clear_old_notifications(self, hours: int = 24) -> int:
        """Elimina notificaciones antiguas del buffer."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=hours)
        
        initial_count = len(self.notifications)
        self.notifications = [
            n for n in self.notifications
            if datetime.fromisoformat(n['timestamp']) > cutoff
        ]
        
        removed = initial_count - len(self.notifications)
        if removed > 0:
            logger.info(f"Cleared {removed} old notifications")
        
        return removed
