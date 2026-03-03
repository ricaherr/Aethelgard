"""
Audit Service - Core logic for system integrity auditing.

This service encapsulates all audit-related operations including:
- Running validation scripts
- Parsing validation output
- Broadcasting audit events via WebSocket
- Handling audit errors gracefully

Extracted from system.py to maintain hygiene of mass (<500 lines per file).
"""
import logging
import asyncio
import os
import traceback
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _broadcast_thought(message: str, module: str = "CORE", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


async def run_integrity_audit() -> Dict[str, Any]:
    """
    Ejecuta validación global con espera completa y retorna resultados.
    Envía eventos en tiempo real vía broadcast_thought.
    
    Returns: Audit results dict with success status, passed/failed counts, and detailed results.
    """
    # Maps of sophisticated language per stage
    sophisticated_lexicon = {
        "Architecture": "Analizando topología de arquitectura y coherencia de módulos...",
        "QA Guard": "Verificando integridad sintáctica y estándares de calidad QA...",
        "Code Quality": "Escaneando densidad de complejidad y patrones de duplicidad...",
        "UI Quality": "Validando ecosistema React y consistencia de tipos en interfaz...",
        "Manifesto": "Enforzando leyes del Manifesto (DI & SSOT)...",
        "Patterns": "Escrutando firmas de métodos y protocolos de seguridad AST...",
        "Core Tests": "Ejecutando suite crítica de deduplicación y gestión de riesgo...",
        "Integration": "Validando puentes de integración y persistencia en Data Vault...",
        "Connectivity": "Auditando latencia y fidelidad del uplink con el Broker...",
        "System DB": "Verificando integridad estructural de la base de Datos..."
    }

    await _broadcast_thought("Desplegando hilos de auditoría paralela... Iniciando escaneo de vectores de integridad.", module="HEALTH")
    
    validation_results = []
    error_details = {}
    total_time = 0.0
    
    try:
        process = await asyncio.create_subprocess_exec(
            "python", "scripts/validate_all.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.getcwd()
        )
        
        # Read stdout line by line to intercept STAGE_START, STAGE_END and DEBUG_FAIL
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode(errors='replace').strip()
            
            if decoded_line.startswith("STAGE_START:"):
                stage = decoded_line.split(":")[1]
                msg = sophisticated_lexicon.get(stage, f"Iniciando fase: {stage}...")
                await _broadcast_thought(msg, level="info", module="HEALTH", metadata={"stage": stage, "status": "STARTING"})
            
            elif decoded_line.startswith("DEBUG_FAIL:"):
                parts = decoded_line.split(":", 2)
                if len(parts) >= 3:
                    stage, error = parts[1], parts[2]
                    error_details[stage] = error

            elif decoded_line.startswith("STAGE_END:"):
                parts = decoded_line.split(":")
                if len(parts) >= 4:
                    stage, result_status, duration = parts[1], parts[2], parts[3]
                    try:
                        duration_float = float(duration)
                        total_time += duration_float
                    except:
                        duration_float = 0.0
                    
                    if result_status == "OK":
                        color_indicator = "OK"
                        await _broadcast_thought(
                            f"{color_indicator} Vector {stage} successfully validated ({duration}s).",
                            level="success",
                            module="HEALTH",
                            metadata={"stage": stage, "status": "OK", "duration": duration}
                        )
                        validation_results.append({
                            "stage": stage,
                            "status": "PASSED",
                            "duration": duration_float
                        })
                    else:
                        color_indicator = "FAIL"
                        error_msg = error_details.get(stage, "Inconsistencia de integridad no especificada.")
                        await _broadcast_thought(
                            f"{color_indicator} Vector {stage} compromised ({duration}s). Error: {error_msg}",
                            level="warning",
                            module="HEALTH",
                            metadata={
                                "stage": stage,
                                "status": "FAIL",
                                "duration": duration,
                                "error": error_msg
                            }
                        )
                        validation_results.append({
                            "stage": stage,
                            "status": "FAILED",
                            "duration": duration_float,
                            "error": error_msg
                        })
        
        await process.wait()
        
        # Create snapshots to avoid "dictionary changed size during iteration" error
        validation_results_snapshot = list(validation_results)
        error_details_snapshot = dict(error_details)
        
        # Success logic: Must have return code 0 AND no failed stages detected in stdout
        passed_count = sum(1 for r in validation_results_snapshot if r.get("status") == "PASSED")
        failed_count = sum(1 for r in validation_results_snapshot if r.get("status") == "FAILED")
        total_count = len(validation_results_snapshot)
        
        # Final determination: We trust the process return code first, but verify stage count
        success = (process.returncode == 0) and (failed_count == 0) and (total_count > 0)
        
        # Debug Return Code
        if process.returncode != 0:
            logger.warning(f"[AUDIT] Validation process exited with non-zero code: {process.returncode} (Failed count: {failed_count})")
        
        if success:
            final_msg = f"Auditoría de alto rendimiento completada: Matriz de integridad 100% estable ({passed_count}/{total_count} vectores validados en {total_time:.2f}s)."
            await _broadcast_thought(final_msg, level="success", module="HEALTH", metadata={"status": "FINISHED", "success": True, "total_time": total_time})
        else:
            final_msg = f"Auditoría finalizada con {failed_count} vectores comprometidos ({passed_count}/{total_count} validados en {total_time:.2f}s)."
            await _broadcast_thought(final_msg, level="warning", module="HEALTH", metadata={"status": "FINISHED", "success": False, "total_time": total_time})
        
        # Return complete results
        return {
            "success": success,
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "duration": total_time,
            "results": validation_results_snapshot,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"[AUDIT] Error en flujo de auditoría evolucionada: {e}\n{tb_str}", exc_info=True)
        error_msg = f"Falla crítica en motor de auditoría: {str(e)}"
        try:
            await _broadcast_thought(error_msg, level="error", module="HEALTH")
        except:
            pass  # Ignore broadcast errors during error handling
        return {
            "success": False,
            "error": error_msg,
            "traceback": tb_str,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
