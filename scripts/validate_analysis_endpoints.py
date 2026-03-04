#!/usr/bin/env python3
"""
Validador de Endpoints para Analysis Hub
Verifica que todos los endpoints funcionen y devuelvan datos esperados.

Usage:
  python scripts/validate_analysis_endpoints.py
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api"
TEST_SYMBOL = "EURUSD"
TEST_TIMEFRAME = "M1"
TEST_USER = "default"
TEST_PASSWORD = "default"

# Definir todos los endpoints que Analysis Hub usa
ENDPOINTS = {
    "market": [
        {
            "name": "Get Heatmap Data",
            "method": "GET",
            "endpoint": "/analysis/heatmap",
            "description": "Matriz de calor de símbolos x timeframes"
        },
        {
            "name": "Get Predator Radar",
            "method": "GET",
            "endpoint": "/analysis/predator-radar",
            "description": "Radar de predadores (institucionales)"
        },
        {
            "name": f"Get Instrument Analysis ({TEST_SYMBOL})",
            "method": "GET",
            "endpoint": f"/instrument/{TEST_SYMBOL}/analysis",
            "description": "Análisis completo del instrumento"
        },
        {
            "name": f"Get Regime ({TEST_SYMBOL})",
            "method": "GET",
            "endpoint": f"/regime/{TEST_SYMBOL}",
            "description": "Régimen de mercado actual"
        },
        {
            "name": f"Get Regime History ({TEST_SYMBOL})",
            "method": "GET",
            "endpoint": f"/regime/{TEST_SYMBOL}/history",
            "description": "Historial de regímenes"
        },
        {
            "name": f"Get Chart ({TEST_SYMBOL}/{TEST_TIMEFRAME})",
            "method": "GET",
            "endpoint": f"/chart/{TEST_SYMBOL}/{TEST_TIMEFRAME}",
            "description": "Datos OHLC del gráfico"
        },
        {
            "name": "Get Regime Configs",
            "method": "GET",
            "endpoint": "/regime_configs",
            "description": "Configuración de regímenes"
        },
        {
            "name": "Get Instruments",
            "method": "GET",
            "endpoint": "/instruments",
            "description": "Lista de instrumentos disponibles"
        }
    ],
    "trading": [
        {
            "name": "Get Active Signals",
            "method": "GET",
            "endpoint": "/signals",
            "description": "Señales activas en el sistema"
        },
        {
            "name": "Get Open Positions",
            "method": "GET",
            "endpoint": "/positions/open",
            "description": "Posiciones abiertas"
        },
        {
            "name": "Get Edge History",
            "method": "GET",
            "endpoint": "/edge/history",
            "description": "Historial de ventaja estadística"
        },
        {
            "name": "Get Strategies Library",
            "method": "GET",
            "endpoint": "/strategies/library",
            "description": "Librería de estrategias disponibles"
        }
    ]
}

class EndpointValidator:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.results: Dict[str, List[Dict[str, Any]]] = {
            "market": [],
            "trading": [],
            "websocket": []
        }
        self.session = None
        self.token = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        await self.get_auth_token()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_auth_token(self) -> None:
        """Obtiene token de autenticación."""
        try:
            logger.info("🔐 Obteniendo token de autenticación...")
            url = f"{self.base_url}/login"
            payload = {"username": TEST_USER, "password": TEST_PASSWORD}
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data.get("access_token")
                    logger.info(f"✅ Token obtenido exitosamente")
                else:
                    logger.warning(f"⚠️ No se pudo obtener token: {resp.status}")
                    error_detail = await resp.text()
                    logger.warning(f"   Detalle: {error_detail[:100]}")
        except Exception as e:
            logger.error(f"❌ Error al obtener token: {e}")
    
    def get_headers(self) -> Dict[str, str]:
        """Retorna headers con autenticación."""
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def test_endpoint(self, endpoint_def: Dict[str, Any]) -> Dict[str, Any]:
        """Prueba un endpoint y retorna resultado."""
        try:
            url = f"{self.base_url}{endpoint_def['endpoint']}"
            method = endpoint_def['method'].upper()
            
            logger.info(f"🔍 Probando: {endpoint_def['name']} ({method} {url})")
            
            if method == "GET":
                async with self.session.get(url, headers=self.get_headers(), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    status = resp.status
                    try:
                        data = await resp.json()
                    except:
                        data = await resp.text()
                    
                    result = {
                        "endpoint": endpoint_def['endpoint'],
                        "name": endpoint_def['name'],
                        "status": status,
                        "success": 200 <= status < 300,
                        "data_received": data is not None,
                        "response_sample": str(data)[:200] if data else "No data",
                        "timestamp": datetime.now().isoformat(),
                        "error": None
                    }
                    
                    if result['success']:
                        logger.info(f"  ✅ SUCCESS - Status {status}")
                    else:
                        logger.warning(f"  ⚠️ WARNING - Status {status}")
                    
                    return result
            
        except asyncio.TimeoutError:
            logger.error(f"  ❌ TIMEOUT - Endpoint no responde")
            return {
                "endpoint": endpoint_def['endpoint'],
                "name": endpoint_def['name'],
                "status": None,
                "success": False,
                "data_received": False,
                "response_sample": "Timeout",
                "timestamp": datetime.now().isoformat(),
                "error": "Timeout after 10s"
            }
        except Exception as e:
            logger.error(f"  ❌ ERROR - {str(e)}")
            return {
                "endpoint": endpoint_def['endpoint'],
                "name": endpoint_def['name'],
                "status": None,
                "success": False,
                "data_received": False,
                "response_sample": str(e)[:200],
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def validate_all(self) -> Dict[str, Any]:
        """Valida todos los endpoints."""
        logger.info("\n" + "="*80)
        logger.info("INICIANDO VALIDACIÓN DE ENDPOINTS - ANALYSIS HUB")
        logger.info("="*80 + "\n")
        
        # Test Market endpoints
        logger.info("📊 ENDPOINTS DE MERCADO")
        logger.info("-" * 80)
        for endpoint_def in ENDPOINTS["market"]:
            result = await self.test_endpoint(endpoint_def)
            self.results["market"].append(result)
        
        logger.info("\n📈 ENDPOINTS DE TRADING")
        logger.info("-" * 80)
        for endpoint_def in ENDPOINTS["trading"]:
            result = await self.test_endpoint(endpoint_def)
            self.results["trading"].append(result)
        
        logger.info("\n🔌 VALIDANDO WEBSOCKET")
        logger.info("-" * 80)
        await self.test_websocket()
        
        return self.results
    
    async def test_websocket(self) -> None:
        """Prueba conexión WebSocket."""
        try:
            ws_url = f"ws://localhost:8000/ws/GENERIC/analysis"
            logger.info(f"🔍 Probando WebSocket: {ws_url}")
            
            async with self.session.ws_connect(ws_url, timeout=5) as ws:
                logger.info("  ✅ WebSocket conectado")
                
                # Esperar mensaje
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=3)
                    logger.info(f"  ✅ Mensaje recibido: {str(msg)[:100]}")
                    self.results["websocket"].append({
                        "status": "connected",
                        "success": True,
                        "message_received": True,
                        "sample": str(msg)[:200]
                    })
                except asyncio.TimeoutError:
                    logger.warning("  ⚠️ WebSocket conectado pero sin mensajes en 3s")
                    self.results["websocket"].append({
                        "status": "connected_no_messages",
                        "success": True,
                        "message_received": False,
                        "sample": "Timeout esperando mensaje"
                    })
        except Exception as e:
            logger.error(f"  ❌ WebSocket Error: {str(e)}")
            self.results["websocket"].append({
                "status": "failed",
                "success": False,
                "message_received": False,
                "error": str(e)
            })
    
    def print_summary(self) -> None:
        """Imprime resumen de validación."""
        logger.info("\n" + "="*80)
        logger.info("RESUMEN DE VALIDACIÓN")
        logger.info("="*80 + "\n")
        
        for category, endpoints in [("MERCADO", self.results["market"]), 
                                     ("TRADING", self.results["trading"])]:
            logger.info(f"\n📊 {category}")
            logger.info("-" * 80)
            
            passed = sum(1 for ep in endpoints if ep.get('success', False))
            total = len(endpoints)
            
            for ep in endpoints:
                status_icon = "✅" if ep.get('success') else "❌"
                status_code = ep.get('status', 'N/A')
                name = ep.get('name', 'Unknown')
                logger.info(f"{status_icon} {name:<50} [{status_code}]")
            
            logger.info(f"\n{category}: {passed}/{total} endpoints funcionando")
        
        # WebSocket
        logger.info(f"\n🔌 WEBSOCKET")
        logger.info("-" * 80)
        if self.results["websocket"]:
            ws_result = self.results["websocket"][0]
            status_icon = "✅" if ws_result.get('success') else "❌"
            status = ws_result.get('status')
            logger.info(f"{status_icon} WebSocket Connection: {status}")
        
        # Resumen general
        all_passed = sum(1 for cat in self.results.values() for ep in cat if ep.get('success', False))
        all_total = sum(len(cat) for cat in self.results.values())
        
        logger.info("\n" + "="*80)
        logger.info(f"RESULTADO FINAL: {all_passed}/{all_total} endpoints operacionales")
        logger.info("="*80 + "\n")
        
        if all_passed == all_total:
            logger.info("✅ TODOS LOS ENDPOINTS FUNCIONAN CORRECTAMENTE")
        else:
            logger.warning(f"⚠️  {all_total - all_passed} endpoints con problemas")

async def main():
    """Función principal."""
    logger.info(f"Conectando a servidor en {BASE_URL}\n")
    
    # Verificar que el servidor está levantado
    try:
        async with aiohttp.ClientSession() as test_session:
            async with test_session.get(f"{BASE_URL}/instruments", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in [200, 401, 403]:  # 401/403 significa auth requerido pero servidor está up
                    logger.info(f"✅ Servidor disponible en {BASE_URL}")
                else:
                    logger.error(f"❌ Servidor respondió con status {resp.status}")
                    sys.exit(1)
    except Exception as e:
        logger.error(f"❌ No se puede conectar al servidor: {e}")
        logger.error("Ejecuta: python start.py")
        sys.exit(1)
    
    # Validar endpoints
    async with EndpointValidator(BASE_URL) as validator:
        results = await validator.validate_all()
        validator.print_summary()
        
        # Retornar código de salida
        all_passed = sum(1 for cat in results.values() for ep in cat if ep.get('success', False))
        all_total = sum(len(cat) for cat in results.values())
        
        if all_passed == all_total:
            return 0
        else:
            return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
