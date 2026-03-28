import asyncio
import logging
import time
import subprocess
from datetime import datetime
from typing import List, Dict, Any
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class AutonomousHealthService:
    """
    Servicio EDGE de auto-gestión y monitoreo de salud.
    Vigila el sistema, detecta anomalías y propone acciones.
    """
    
    def __init__(self, storage: StorageManager):
        self.storage = storage
        self.running = False
        self._last_validation_time = 0
        self.validation_interval = 3600  # 1 hora
        
    async def start(self) -> None:
        """Inicia el bucle de monitoreo autónomo"""
        self.running = True
        logger.info("[HEALTH] Iniciando Servicio de Salud Autónomo (PAS 2.0)")
        
        while self.running:
            try:
                await self._perform_health_check()
                # Esperar antes del siguiente ciclo reducido para monitoreo reactivo
                await asyncio.sleep(300) # Cada 5 min revisión ligera
            except Exception as e:
                logger.error(f"[HEALTH] Error en bucle de salud: {e}")
                await asyncio.sleep(60)

    async def _perform_health_check(self) -> None:
        """Ejecuta validaciones y genera pensamientos/propuestas"""
        now = time.time()

        # 1. Validación Global Periódica (PESADA)
        if now - self._last_validation_time > self.validation_interval:
            await self._run_global_validation()
            self._last_validation_time = now

        # 2. Monitoreo de Recursos
        await self._check_system_resources()

        # 3. Verificación de Integridad de Datos
        await self._check_db_integrity()

        # 4. Despachar diagnósticos del OperationalEdgeMonitor a la UI
        await self._dispatch_oem_diagnostics()

    async def _run_global_validation(self) -> None:
        """Corre el script de validación global"""
        from core_brain.server import broadcast_thought
        await broadcast_thought("Iniciando auditoría de salud global proactiva...", module="HEALTH")
        
        try:
            # Ejecutar validate_all.py
            process = await asyncio.create_subprocess_exec(
                "python", "scripts/validate_all.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                await broadcast_thought("Auditoría de salud completada: 100% OK.", level="success", module="HEALTH")
            else:
                await broadcast_thought("Se detectaron inconsistencias menores en la auditoría. Revisando...", level="warning", module="HEALTH")
                logger.warning(f"[HEALTH] Validation failures: {stderr.decode()}")
                
        except Exception as e:
            logger.error(f"[HEALTH] No se pudo ejecutar validación: {e}")

    async def _check_system_resources(self) -> None:
        """Vigila logs y CPU"""
        from core_brain.server import broadcast_thought
        
        # Check Log Size
        log_path = "logs/main.log"
        try:
            import os
            if os.path.exists(log_path):
                size_mb = os.path.getsize(log_path) / (1024 * 1024)
                if size_mb > 450:
                    await broadcast_thought(f"El log principal está cerca del límite ({size_mb:.1f}MB). Rotación programada para medianoche.", level="warning", module="INFRA")
        except Exception:
            pass

    async def _check_db_integrity(self) -> None:
        """Verifica que no haya bloqueos o errores en DB"""
        try:
            # Simple query de prueba
            self.storage.execute_query("SELECT 1")
        except Exception as e:
            from core_brain.server import broadcast_thought
            await broadcast_thought("¡CRÍTICO! Error de acceso a Base de Datos detectado.", level="error", module="DB")
            logger.error(f"[HEALTH] DB Integrity Check Failed: {e}")

    async def _dispatch_oem_diagnostics(self) -> None:
        """
        Lee el snapshot del OperationalEdgeMonitor desde DB y emite diagnósticos
        a la UI via broadcast_thought. Solo actúa sobre checks no accionables
        automáticamente (shadow_sync, signal_flow, rejection_rate,
        orchestrator_heartbeat) — los accionables ya tienen flags en sys_config
        que el MainOrchestrator consume.
        """
        import json as _json
        from core_brain.server import broadcast_thought

        # Mensajes de diagnóstico para checks no auto-reparables
        _HUMAN_CHECKS: dict = {
            "shadow_sync": (
                "warning",
                "SHADOW SYNC FAIL: hay instancias maduras con 0 trades. "
                "Posible causa: mercado fuera de sesión o símbolo no habilitado. "
                "Revisar ventanas de activación de estrategias SHADOW."
            ),
            "signal_flow": (
                "warning",
                "SIGNAL FLOW WARN: sin señales en los últimos 120 min. "
                "El scanner está activo pero no detecta oportunidades — puede ser correcto fuera de sesión."
            ),
            "rejection_rate": (
                "error",
                "REJECTION RATE FAIL: tasa de rechazo >95%. "
                "Pipeline bloqueado o umbrales demasiado restrictivos. Requiere revisión manual."
            ),
            "orchestrator_heartbeat": (
                "error",
                "ORCHESTRATOR HEARTBEAT FAIL: el loop principal no responde. "
                "Posible bloqueo en fase de scan o backtest. Revisar logs del proceso start.py."
            ),
        }

        try:
            sys_config = self.storage.get_sys_config()
            raw = sys_config.get("oem_health_snapshot")
            if not raw:
                return

            snapshot = _json.loads(raw) if isinstance(raw, str) else raw
            status = snapshot.get("status", "OK")
            failing = snapshot.get("failing", [])
            warnings = snapshot.get("warnings", [])

            if status == "CRITICAL":
                await broadcast_thought(
                    f"⚠ EDGE SELF-AUDIT CRITICAL: {len(failing)} invariante(s) violada(s): "
                    f"{', '.join(failing)}. Acciones correctivas en curso.",
                    level="error", module="OEM"
                )

            for check in failing + warnings:
                if check in _HUMAN_CHECKS:
                    level, message = _HUMAN_CHECKS[check]
                    await broadcast_thought(message, level=level, module="OEM")

        except Exception as exc:
            logger.warning("[HEALTH] Error dispatching OEM diagnostics: %s", exc)

    def stop(self) -> None:
        self.running = False
