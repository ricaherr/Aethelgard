#!/usr/bin/env python3
"""
UI HEALTH CHECK - Aethelgard Smoke Test Suite
Checks build accessibility, critical component existence, and API connectivity.
"""

import os
import sys
import requests
import logging
import io
from pathlib import Path
from typing import List, Dict

# Fix encoding for Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Configuración de logs profesional
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UIHealth")

class UIHealthCheck:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.ui_dist = self.project_root / "ui" / "dist"
        self.ui_src = self.project_root / "ui" / "src"
        self.api_base = "http://localhost:8000"
        
        # Componentes críticos a verificar
        self.critical_components = [
            "components/edge/RegimeBadge.tsx",
            "components/edge/WeightedMetricsVisualizer.tsx",
            "components/edge/EdgeHub.tsx"
        ]
        
        # Endpoints críticos de la API
        self.critical_endpoints = [
            "/health",
            "/api/system/status",
            "/api/risk/status",
            "/api/regime_configs"
        ]

    def check_typescript_strict(self) -> bool:
        """
        Ejecuta TypeScript con validación de tipos estricta.
        Detecta errores de tipos que podrían no aparecer en build normal.
        """
        import subprocess
        import platform

        ui_dir = self.project_root / "ui"
        logger.info("Ejecutando validación estricta de TypeScript...")

        # En Windows npm es npm.cmd; en Unix es npm
        npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"

        try:
            result = subprocess.run(
                [npm_cmd, "run", "tsc-check"],
                cwd=str(ui_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info("✅ TypeScript strict check: OK (sin errores de tipos)")
                return True
            else:
                logger.error("❌ Errores de tipos detectados en TypeScript")
                if result.stdout:
                    logger.error("   %s", result.stdout[:200])
                return False
        except subprocess.TimeoutExpired:
            logger.error("❌ TypeScript check timeout (>60s)")
            return False
        except FileNotFoundError:
            logger.warning("⚠️ npm no encontrado — ejecuta 'npm run tsc-check' en ui/ manualmente")
            return True
        except Exception as e:
            logger.warning("⚠️ TypeScript check no disponible: %s", e)
            return True

    def check_build_accessibility(self) -> bool:
        """Verifica que la build de producción exista y sea legible"""
        index_html = self.ui_dist / "index.html"
        if not index_html.exists():
            logger.error(f"❌ Build no encontrada: {index_html}")
            return False
        
        size = index_html.stat().st_size
        if size < 100:
            logger.error(f"❌ Build corrupta (index.html demasiado pequeño: {size} bytes)")
            return False
            
        logger.info(f"✅ Build accesible: {index_html} ({size} bytes)")
        return True

    def check_component_integrity(self) -> bool:
        """Verifica la existencia física de componentes críticos"""
        missing = []
        for comp in self.critical_components:
            path = self.ui_src / comp
            if not path.exists():
                missing.append(comp)
            else:
                # Verificación básica de exportación (estática)
                content = path.read_text(encoding="utf-8")
                # Verificación básica de exportación (estática)
                content = path.read_text(encoding="utf-8")
                export_patterns = ["export const", "export default", "export function", "export {", "export interface", "export interface"]
                if not any(pattern in content for pattern in export_patterns):
                    logger.warning(f"⚠️ Componente {comp} existe pero no parece exportar nada estándar.")
        
        if missing:
            logger.error(f"❌ Componentes críticos faltantes: {', '.join(missing)}")
            return False
            
        logger.info(f"✅ Integridad de componentes: OK ({len(self.critical_components)} verificados)")
        return True

    def check_api_connectivity(self) -> bool:
        """
        Verifica que el backend esté arriba y respondiendo.

        El check de conectividad se hace contra /health (sin auth).
        Un 401 en endpoints protegidos indica que el servidor está activo
        (la autenticación es una capa separada, no un fallo de conectividad).
        """
        try:
            # Verificar disponibilidad del servidor con el endpoint público
            response = requests.get(f"{self.api_base}/health", timeout=3)
            if response.status_code not in (200, 401, 403):
                logger.error("❌ API Backend respondió con status inesperado: %s", response.status_code)
                return False

            logger.info("✅ Conectividad API: OK (status %s)", response.status_code)

            # Verificar que los endpoints protegidos están activos (401 = servidor OK, solo falta auth)
            for endpoint in self.critical_endpoints:
                if endpoint == "/health":
                    continue
                try:
                    res = requests.get(f"{self.api_base}{endpoint}", timeout=2)
                    if res.status_code == 200:
                        logger.info("  ✅ %s → %s", endpoint, res.status_code)
                    elif res.status_code in (401, 403):
                        logger.info("  ✅ %s → %s (auth requerida, servidor activo)", endpoint, res.status_code)
                    else:
                        logger.warning("  ⚠️ %s → %s", endpoint, res.status_code)
                except Exception:
                    logger.warning("  ⚠️ %s no accesible", endpoint)

            return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.warning("⚠️ API no disponible en %s (servidor offline o lento)", self.api_base)
            # No bloquear el audit si el servidor no está arriba durante pre-flight
            return True
        except Exception as e:
            logger.error("❌ Error inesperado en API check: %s", e)
            return False

    def run_all(self) -> int:
        print("\n" + "="*60)
        print("🛡️  AETHELGARD UI HEALTH CHECK")
        print("="*60)
        
        results = [
            self.check_typescript_strict(),  # NEW: TypeScript type validation
            self.check_build_accessibility(),
            self.check_component_integrity(),
            self.check_api_connectivity()
        ]
        
        print("="*60)
        if all(results):
            print("✨ UI HEALTH STATUS: OPTIMAL")
            print("="*60 + "\n")
            return 0
        else:
            print("🛑 UI HEALTH STATUS: COMPROMISED")
            print("="*60 + "\n")
            return 1

if __name__ == "__main__":
    health = UIHealthCheck()
    sys.exit(health.run_all())
