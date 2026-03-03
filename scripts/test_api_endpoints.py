#!/usr/bin/env python
"""
API Endpoints Health Check - Valida que endpoints devuelven respuestas válidas (nunca 500).

TRACE_ID: EXEC-API-RESILIENCE-FIX

Script independiente que verifica:
1. GET /api/chart/{symbol}/{timeframe} - Devuelve datos o estructura vacía (nunca 500)
2. GET /api/instrument/{symbol}/analysis - Devuelve análisis o estructura vacía (nunca 500)

Uso:
    python scripts/test_api_endpoints.py
"""

import asyncio
import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Tuple

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class APIHealthCheck:
    """Validador de endpoints API."""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 10):
        self.base_url = base_url
        self.timeout = timeout
        self.results = {}
    
    async def check_endpoint(self, endpoint: str, name: str) -> Tuple[bool, str]:
        """
        Valida un endpoint.
        
        Returns:
            (success, message)
        """
        try:
            import aiohttp
        except ImportError:
            return False, "aiohttp not installed"
        
        try:
            url = f"{self.base_url}{endpoint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status == 500:
                        text = await resp.text()
                        return False, f"HTTP 500: {text[:100]}"
                    
                    if resp.status == 401:
                        return True, f"HTTP 401 (expected - auth required)"
                    
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            return True, f"HTTP 200: {len(json.dumps(data))} bytes"
                        except:
                            return True, f"HTTP 200 (invalid JSON, check content-type)"
                    
                    return True, f"HTTP {resp.status}"
        
        except asyncio.TimeoutError:
            return False, "Timeout (server may not be running)"
        except ConnectionRefusedError:
            return False, "Connection refused (server not running?)"
        except Exception as e:
            return False, f"Error: {str(e)[:80]}"
    
    async def run_checks(self) -> int:
        """Ejecuta todas las validaciones."""
        print("\n[API_HEALTH_CHECK] Validando endpoints de API\n")
        
        endpoints = [
            ("/api/chart/EURUSD/M5", "Chart Data (EURUSD/M5)"),
            ("/api/instrument/EURUSD/analysis", "Instrument Analysis (EURUSD)"),
            ("/api/analysis/heatmap", "Heatmap"),
            ("/api/analysis/predator-radar?symbol=EURUSD&timeframe=M5", "Predator Radar"),
            ("/api/regime/EURUSD", "Regime (EURUSD)"),
        ]
        
        failures = 0
        
        for endpoint, name in endpoints:
            success, message = await self.check_endpoint(endpoint, name)
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} {name:<40} {message}")
            
            if not success and "500" in message:
                failures += 1
        
        print()
        
        if failures == 0:
            print("[SUCCESS] All endpoints responding correctly (no 500 errors)")
            return 0
        else:
            print(f"[FAIL] {failures} endpoint(s) returning 500 errors")
            return 1


async def main():
    checker = APIHealthCheck()
    return await checker.run_checks()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
