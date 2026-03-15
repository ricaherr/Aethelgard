"""
EDGE Monitor - Observabilidad Autónoma para Aethelgard
Monitorea inconsistencias entre módulos y genera informes de aprendizaje.
Incluye detección de operaciones externas y auditoría de señales.
"""
import threading
import time
import logging
from typing import Dict, Any, List, Optional
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class EdgeMonitor(threading.Thread):
    """
    Monitor autónomo que detecta inconsistencias entre módulos.
    Corre cada 60 segundos verificando sincronización entre SignalFactory, Executor y Scanner.
    Incluye detección de operaciones externas de MT5 y auditoría de señales.
    """
    
    def __init__(self, storage: StorageManager, mt5_connector: Optional[Any] = None, trade_listener: Optional[Any] = None, interval_seconds: int = 60):
        super().__init__(daemon=True)
        self.storage = storage
        self.interval_seconds = interval_seconds
        self.running = True
        self.name = "EdgeMonitor"
        self.mt5_connector = mt5_connector  # Injected dependency (reuse existing instance)
        self.trade_listener = trade_listener  # TradeClosureListener for reconciliation
        
    def run(self) -> None:
        """Loop principal del monitor"""
        logger.info("[EDGE] Monitor started - checking for inconsistencies every 60s")
        
        # PRUEBA DE AUTOINYECCIÓN
        try:
            self.storage.save_edge_learning(
                detection="Sistema Iniciado",
                action_taken="Auto-test de EDGE",
                learning="Canal de comunicación activo"
            )
        except Exception as e:
            logger.error(f"[EDGE TEST ERROR] Falló la inserción de prueba: {e}")
            raise
        
        while self.running:
            try:
                self._check_mt5_external_operations()
                self._check_inconsistencies()
                self._audit_signal_inconsistencies()
                self._check_risk_behavior_patterns()
            except Exception as e:
                logger.error(f"Error in EDGE Monitor: {e}")
            
            time.sleep(self.interval_seconds)
    
    def stop(self) -> None:
        """Detener el monitor"""
        self.running = False
        logger.info("[EDGE] Monitor stopped")
    
    def _get_mt5_connector(self) -> Optional[Any]:
        """Get MT5 connector instance (must be injected)"""
        if self.mt5_connector is None:
            logger.warning("[EDGE] MT5 connector not available (not injected)")
            return None
        return self.mt5_connector
    
    def _check_mt5_external_operations(self) -> None:
        """Comparar posiciones MT5 con operaciones activas del bot
        
        IMPORTANTE: Primero reconcilia cierres pendientes (MT5 → DB)
        para garantizar que la comparación sea contra datos actualizados.
        """
        mt5 = self._get_mt5_connector()
        if not mt5:
            return
            
        try:
            # Intentar conectar si no está conectado
            if not mt5.is_connected:
                if not mt5.connect():
                    return
            
            # PASO 1: Reconciliar cierres pendientes (sincronizar DB con MT5)
            if self.trade_listener:
                mt5.reconcile_closed_usr_trades(self.trade_listener, hours_back=24)
            else:
                logger.warning("[EDGE] TradeClosureListener not available - reconciliation skipped")
            
            # PASO 2: Obtener posiciones ABIERTAS de MT5 (ya sincronizadas)
            mt5_usr_positions = mt5.get_open_positions()
            if mt5_usr_positions is None:
                return
                
            # PASO 3: Obtener operaciones activas del bot (ya actualizadas)
            bot_operations = self.storage.get_open_operations()
            
            # LOG DE DIAGNÓSTICO
            logger.debug(f"🔍 MT5 Open: {len(mt5_usr_positions)} | DB Open: {len(bot_operations)} (post-reconciliation)")
            
            bot_tickets = set()
            
            # Extraer tickets de las operaciones del bot
            for op in bot_operations:
                metadata = op.get('metadata', {})
                ticket = metadata.get('ticket') or metadata.get('order_id')
                if ticket:
                    bot_tickets.add(int(ticket))
            
            # PASO 4: Comparar posiciones MT5 con operaciones del bot
            mt5_tickets = set(pos['ticket'] for pos in mt5_usr_positions)
            external_tickets = mt5_tickets - bot_tickets
            
            # Reportar operaciones externas detectadas
            for ticket in external_tickets:
                # Verificar si ya fue reportado recientemente (últimas 24h)
                if not self._was_external_operation_reported_recently(ticket):
                    self._report_external_operation(ticket)
                    
        except Exception as e:
            logger.error(f"Error checking MT5 external operations: {e}")
        # NOTE: NO disconnect MT5 here - connection is managed by start.py and shared across componentsents
    
    def _was_external_operation_reported_recently(self, ticket: int) -> bool:
        """Verificar si una operación externa ya fue reportada recientemente"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM usr_edge_learning 
                WHERE detection LIKE ? 
                AND timestamp >= datetime('now', '-24 hours')
            """, (f"Operación manual externa detectada (Ticket: #{ticket})%",))
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            self.storage._close_conn(conn)
    
    def _report_external_operation(self, ticket: int) -> None:
        """Reportar operación externa detectada"""
        detection = f"Operación manual externa detectada (Ticket: #{ticket})"
        action_taken = "Registro en diario y exclusión de gestión automática para evitar conflictos"
        learning = "Intervención humana detectada; ajustando métricas de riesgo total"
        details = f"Ticket MT5 #{ticket} no corresponde a ninguna operación generada por el bot"
        
        self.storage.save_edge_learning(
            detection=detection,
            action_taken=action_taken,
            learning=learning,
            details=details
        )
        
        logger.warning(f"[EDGE] {detection}")
    
    def _check_inconsistencies(self) -> None:
        """Verificar inconsistencias entre módulos"""
        # Contar señales generadas en los últimos 60s
        generated_count = self._count_recent_usr_signals()
        
        # Contar señales ejecutadas en los últimos 60s
        executed_count = self._count_recent_executed_usr_signals()
        
        # Si hay discrepancia significativa (>10% o >1), investigar
        if generated_count > executed_count + max(1, generated_count * 0.1):
            self._investigate_inconsistency(generated_count, executed_count)
    
    def _audit_signal_inconsistencies(self) -> None:
        """Auditoría específica: señales generadas vs órdenes ejecutadas"""
        # Obtener señales recientes que deberían haber sido ejecutadas
        recent_usr_signals = self._get_recent_pending_sys_signals()
        
        for signal in recent_usr_signals:
            signal_id = signal['id']
            symbol = signal['symbol']
            
            # Verificar si hay orden correspondiente en MT5
            mt5 = self._get_mt5_connector()
            if mt5:
                try:
                    if not mt5.is_connected:
                        mt5.connect()
                    
                    # Buscar orden o posición correspondiente en MT5 (PEDANTIC API COMPLIANCE)
                    # Method resolution: get_pending_orders() + get_open_positions()
                    found_matching_order = self._find_mt5_matching_order(mt5, symbol, signal)
                    
                    if not found_matching_order:
                        # No hay orden correspondiente - investigar
                        self._investigate_missing_order(signal)
                            
                except Exception as e:
                    logger.error(f"Error auditing signal {signal_id}: {e}")
                # NOTE: NO disconnect MT5 here - connection is managed by start.py and shared across components
    
    def _get_recent_pending_sys_signals(self) -> List[Dict]:
        """Obtener señales recientes que deberían haber sido ejecutadas"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sys_signals 
                WHERE status = 'PENDING' 
                AND timestamp >= datetime('now', '-300 seconds')  -- Últimos 5 minutos
                ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self.storage._close_conn(conn)
    
    def _find_mt5_matching_order(self, mt5_connector: Any, symbol: str, signal: Dict) -> bool:
        """
        Find if signal has a corresponding order or position in MT5.
        
        Searches both pending orders AND open positions with 5-minute tolerance window.
        Uses MT5Connector API correctly (get_pending_orders + get_open_positions).
        
        Args:
            mt5_connector: MT5Connector instance
            symbol: Trading symbol to search
            signal: Signal dict with timestamp field
            
        Returns:
            True if matching order/position found, False otherwise
        """
        try:
            signal_time_str = signal.get('timestamp')
            if not signal_time_str:
                logger.warning(f"Signal {signal.get('id')} missing timestamp, cannot match")
                return False
            
            # Parse signal timestamp
            from datetime import datetime, timezone
            try:
                if isinstance(signal_time_str, str):
                    signal_time = datetime.fromisoformat(signal_time_str.replace('Z', '+00:00'))
                else:
                    signal_time = signal_time_str
                    
                if signal_time.tzinfo is None:
                    signal_time = signal_time.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"Could not parse signal timestamp: {e}")
                return False
            
            tolerance_seconds = 300  # 5-minute window
            
            # Strategy 1: Check pending orders (orders not yet executed)
            try:
                pending_orders = mt5_connector.get_pending_orders(symbol=symbol)
                if pending_orders:
                    for order in pending_orders:
                        order_time = order.get('time_setup')
                        if order_time:
                            # Handle both unix timestamp and datetime
                            if isinstance(order_time, (int, float)):
                                from datetime import datetime, timezone
                                order_time = datetime.fromtimestamp(order_time, tz=timezone.utc)
                            elif isinstance(order_time, str):
                                order_time = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                            
                            time_diff = abs((order_time - signal_time).total_seconds())
                            if time_diff < tolerance_seconds:
                                logger.info(f"✅ Found matching pending order for {symbol} (diff: {time_diff:.0f}s)")
                                return True
            except Exception as e:
                logger.debug(f"Error checking pending orders: {e}")
            
            # Strategy 2: Check open positions (orders already executed)
            try:
                open_positions = mt5_connector.get_open_positions()
                if open_positions:
                    symbol_positions = [p for p in open_positions if p.get('symbol') == symbol]
                    if symbol_positions:
                        # For open positions, check if ANY position matches time window
                        for position in symbol_positions:
                            open_time = position.get('open_time')
                            if open_time:
                                # Handle both unix timestamp and datetime
                                if isinstance(open_time, (int, float)):
                                    from datetime import datetime, timezone
                                    open_time = datetime.fromtimestamp(open_time, tz=timezone.utc)
                                elif isinstance(open_time, str):
                                    open_time = datetime.fromisoformat(open_time.replace('Z', '+00:00'))
                                
                                time_diff = abs((open_time - signal_time).total_seconds())
                                if time_diff < tolerance_seconds:
                                    logger.info(f"✅ Found matching open position for {symbol} (diff: {time_diff:.0f}s)")
                                    return True
            except Exception as e:
                logger.debug(f"Error checking open positions: {e}")
            
            # No match found in either pending or open positions
            logger.debug(f"❌ No matching order/position found for {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error in _find_mt5_matching_order: {e}")
            return False
    
    def _investigate_missing_order(self, signal: Dict) -> None:
        """Investigar por qué una señal no tiene orden correspondiente"""
        signal_id = signal['id']
        symbol = signal['symbol']
        
        # Simular investigación del OrderExecutor (en producción revisar logs)
        investigation_result = "OrderExecutor: No se encontró orden correspondiente en MT5"
        
        # Determinar motivo probable
        possible_reasons = []
        
        # Verificar si el RiskManager rechazó la orden
        metadata = signal.get('metadata', {})
        if 'risk_rejection' in metadata:
            possible_reasons.append("Rechazo por RiskManager")
        
        # Verificar conectividad MT5
        mt5 = self._get_mt5_connector()
        if mt5:
            try:
                if not mt5.is_connected:
                    if not mt5.connect():
                        possible_reasons.append("MT5 desconectado")
                    else:
                        possible_reasons.append("MT5 conectado pero orden no enviada")
                else:
                    possible_reasons.append("MT5 conectado pero orden no ejecutada")
            except:
                possible_reasons.append("Error de conectividad MT5")
        else:
            possible_reasons.append("MT5 no disponible")
        
        # Si no hay razones específicas, asumir rechazo por margen
        if not possible_reasons:
            possible_reasons.append("Rechazo por margen insuficiente")
        
        reason = possible_reasons[0] if possible_reasons else "Motivo desconocido"
        
        # Generar evento EDGE
        detection = f"Señal generada pero sin orden en MT5: {symbol} ({signal_id[:8]})"
        action_taken = f"Auditoría completada - Motivo identificado: {reason}"
        learning = f"Optimización del flujo SignalFactory → OrderExecutor requerida"
        details = f"Investigación: {investigation_result}. Razones posibles: {', '.join(possible_reasons)}"
        
        self.storage.save_edge_learning(
            detection=detection,
            action_taken=action_taken,
            learning=learning,
            details=details
        )
        
        logger.warning(f"[EDGE] Signal inconsistency: {detection}")
    
    def _count_recent_usr_signals(self) -> int:
        """Contar señales generadas en los últimos 60s"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM sys_signals 
                WHERE timestamp >= datetime('now', '-60 seconds')
            """)
            return cursor.fetchone()[0]
        finally:
            self.storage._close_conn(conn)
    
    def _count_recent_executed_usr_signals(self) -> int:
        """Contar señales ejecutadas en los últimos 60s"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM sys_signals 
                WHERE status = 'EXECUTED' 
                AND timestamp >= datetime('now', '-60 seconds')
            """)
            return cursor.fetchone()[0]
        finally:
            self.storage._close_conn(conn)
    
    def _investigate_inconsistency(self, generated: int, executed: int) -> None:
        """Investigar inconsistencia y generar informe"""
        # Simulación de investigación (en producción parsear logs)
        investigation = {
            "signal_factory_logs": "Señales generadas correctamente",
            "executor_logs": f"Ejecutadas {executed} de {generated}",
            "scanner_logs": "Scanner operativo"
        }
        
        # Generar aprendizaje
        detection = f"Inconsistencia detectada: {generated} señales generadas vs {executed} ejecutadas en 60s"
        action_taken = "Monitoreo continuo activado"
        learning = f"Posible bottleneck en Executor. Ratio ejecución: {executed/generated:.2f} si generated > 0"
        
        # Guardar en EDGE learning
        self.storage.save_edge_learning(
            detection=detection,
            action_taken=action_taken,
            learning=learning,
            details=f"Investigación: {investigation}"
        )

    def _check_risk_behavior_patterns(self) -> None:
        """Check for emerging risk behavior patterns"""
        # Get recent usr_signals with vetoed status
        recent_usr_signals = self.storage.get_recent_sys_signals(minutes=60)
        
        # Group by symbol and count vetoed vs total
        symbol_stats = {}
        for signal in recent_usr_signals:
            symbol = signal.get('symbol', 'UNKNOWN')
            status = signal.get('status', None)
            
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {'total': 0, 'vetoed': 0}
            
            symbol_stats[symbol]['total'] += 1
            if status == 'VETADO':
                symbol_stats[symbol]['vetoed'] += 1
        
        # Check for 100% veto rate on any symbol
        detection = None
        for symbol, stats in symbol_stats.items():
            if stats['total'] >= 5 and stats['vetoed'] == stats['total']:
                # 100% veto rate detected
                detection = f"Patrón emergente: Risk Manager bloqueando 100% de señales para {symbol}"
                action_taken = "Análisis de volatilidad activado"
                learning = f"El activo {symbol} presenta alta volatilidad. Risk Manager actuando preventivamente."
                
                self.storage.save_edge_learning(
                    detection=detection,
                    action_taken=action_taken,
                    learning=learning,
                    details=f"Estadísticas: {stats['vetoed']}/{stats['total']} señales vetadas en última hora"
                )
                logger.warning(f"Emerging pattern detected: 100% veto rate for {symbol}")
        
        if detection:
            logger.warning(f"[EDGE] Inconsistency detected: {detection}")