#!/usr/bin/env python
"""
Test WebSocket Emission - EXEC-UI-VALIDATION-FIX
TRACE_ID: EXEC-UI-VALIDATION-FIX-ACCION-1

Script independiente para validar que el MainOrchestrator está emitiendo datos reales
a través del WebSocket. Se conecta como cliente externo y registra cada paquete.

Uso:
    1. En Terminal 1: python start.py (inicia servidor)
    2. En Terminal 2: python scripts/test_ws_emission.py (conecta y escucha)
    3. Observa en consola cada paquete recibido del servidor

Salida esperada:
    [WEBSOCKET_PACKET] timestamp, type, payload_size, priority (si aplica)
    [ANALYSIS_DATA] Si detecta datos de análisis
    [TRADING_DATA] Si detecta datos de trader
    [SYSTEM_EVENT] Si detecta eventos del sistema
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import websockets
from websockets.client import WebSocketClientProtocol

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI Colors
class Colors:
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

class WebSocketTester:
    """Cliente WebSocket independiente para validar emisión de datos."""
    
    def __init__(self, uri: str = "ws://localhost:8000/ws/GENERIC/test_ws_validator"):
        """
        Inicializa tester.
        
        Args:
            uri: URI del WebSocket (default: localhost:8000/ws/GENERIC/test_ws_validator)
        """
        self.uri = uri
        self.ws: Optional[WebSocketClientProtocol] = None
        self.packets_received = 0
        self.packets_by_type: Dict[str, int] = {}
        self.last_packet_time: Optional[datetime] = None
        self.connection_time: Optional[datetime] = None
        
    async def connect(self) -> bool:
        """
        Conecta al WebSocket del servidor.
        
        Returns:
            True si conectó exitosamente, False si falló
        """
        try:
            logger.info(f"{Colors.CYAN}Conectando a {self.uri}...{Colors.RESET}")
            self.ws = await asyncio.wait_for(
                websockets.connect(self.uri),
                timeout=5.0
            )
            self.connection_time = datetime.now()
            logger.info(
                f"{Colors.GREEN}✓ Conectado exitosamente al WebSocket{Colors.RESET}"
            )
            return True
        except asyncio.TimeoutError:
            logger.error(
                f"{Colors.RED}✗ Timeout esperando conexión (5s). ¿Está el servidor activo?{Colors.RESET}"
            )
            return False
        except ConnectionRefusedError:
            logger.error(
                f"{Colors.RED}✗ Conexión rechazada. Verifica que el servidor está en puerto 8000{Colors.RESET}"
            )
            return False
        except Exception as e:
            logger.error(
                f"{Colors.RED}✗ Error conectando: {str(e)}{Colors.RESET}"
            )
            return False
    
    async def listen(self, duration: int = 30) -> bool:
        """
        Escucha WebSocket durante X segundos y registra packets.
        
        Args:
            duration: Segundos a escuchar (default 30)
            
        Returns:
            True si recibió al menos un packet, False si timeout sin datos
        """
        if not self.ws:
            logger.error(f"{Colors.RED}WebSocket no conectado{Colors.RESET}")
            return False
        
        logger.info(
            f"{Colors.CYAN}Esperando datos por {duration} segundos...{Colors.RESET}\n"
        )
        
        start_time = datetime.now()
        received_any = False
        
        try:
            while (datetime.now() - start_time).total_seconds() < duration:
                try:
                    # Timeout para recibir cada mensaje (5 segundos)
                    remaining = duration - (datetime.now() - start_time).total_seconds()
                    timeout = min(5.0, max(0.1, remaining))
                    
                    message = await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=timeout
                    )
                    
                    self._process_packet(message)
                    received_any = True
                    
                except asyncio.TimeoutError:
                    # Normal - no datos en los últimos 5 segundos
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed % 10 < 5:  # Log cada 10 segundos
                        logger.info(
                            f"{Colors.YELLOW}[WAITING] {elapsed:.1f}s sin datos...{Colors.RESET}"
                        )
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(
                        f"{Colors.YELLOW}Conexión cerrada por servidor{Colors.RESET}"
                    )
                    break
                    
        except Exception as e:
            logger.error(f"{Colors.RED}Error escuchando: {str(e)}{Colors.RESET}")
        
        return received_any
    
    def _process_packet(self, raw_message: str) -> None:
        """
        Procesa un paquete recibido y lo registra.
        
        Args:
            raw_message: Mensaje JSON del servidor
        """
        self.packets_received += 1
        self.last_packet_time = datetime.now()
        
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.error(f"{Colors.RED}[ERROR] Paquete inválido: {raw_message[:100]}{Colors.RESET}")
            return
        
        # Extraer tipo y prioridad
        msg_type = data.get("type", "UNKNOWN")
        priority = data.get("payload", {}).get("priority", "normal")
        timestamp = data.get("timestamp", "N/A")
        
        # Contar por tipo
        self.packets_by_type[msg_type] = self.packets_by_type.get(msg_type, 0) + 1
        
        # Lógica de clasificación y registro
        payload = data.get("payload", {})
        payload_size = len(json.dumps(payload))
        
        # Validar campos esperados
        has_analysis = "signals" in payload or "reasoning" in payload or "structures" in payload
        has_trading_data = "drawings" in payload or "layers" in payload or "positions" in payload
        
        priority_color = Colors.RED if priority == "high" else Colors.CYAN
        
        logger.info(
            f"{Colors.BOLD}[WEBSOCKET_PACKET #{self.packets_received}]{Colors.RESET} "
            f"type={msg_type} | "
            f"priority={priority_color}{priority}{Colors.RESET} | "
            f"size={payload_size}B | "
            f"ts={timestamp}"
        )
        
        # Detectar y loguear tipo de datos
        if msg_type == "ANALYSIS_UPDATE" or has_analysis:
            logger.info(
                f"  └─ {Colors.YELLOW}[ANALYSIS_DATA]{Colors.RESET} "
                f"signals={payload.get('signals', '?')} | "
                f"reasoning={bool(payload.get('reasoning'))}"
            )
        
        if msg_type == "TRADER_PAGE_UPDATE" or has_trading_data:
            drawings_count = len(payload.get("drawings", []))
            layers = list(payload.get("layers", {}).keys())
            logger.info(
                f"  └─ {Colors.GREEN}[TRADING_DATA]{Colors.RESET} "
                f"drawings={drawings_count} | "
                f"layers={layers}"
            )
        
        if msg_type.startswith("SYSTEM_"):
            logger.info(
                f"  └─ {Colors.BLUE}[SYSTEM_EVENT]{Colors.RESET} "
                f"message={payload.get('message', '?')[:80]}"
            )
        
        # Validar esquema básico
        if not isinstance(data, dict):
            logger.warning(f"{Colors.YELLOW}[SCHEMA] Raíz no es diccionario{Colors.RESET}")
        if "type" not in data:
            logger.warning(f"{Colors.YELLOW}[SCHEMA] Falta campo 'type'{Colors.RESET}")
        if "payload" not in data:
            logger.warning(f"{Colors.YELLOW}[SCHEMA] Falta campo 'payload'{Colors.RESET}")
        if "timestamp" not in data:
            logger.warning(f"{Colors.YELLOW}[SCHEMA] Falta campo 'timestamp'{Colors.RESET}")
    
    async def disconnect(self) -> None:
        """Desconecta del WebSocket."""
        if self.ws:
            try:
                await self.ws.close()
                logger.info(f"{Colors.GREEN}Desconectado{Colors.RESET}")
            except Exception as e:
                logger.error(f"Error desconectando: {e}")
    
    def print_summary(self) -> None:
        """Imprime resumen de emisión."""
        elapsed = None
        if self.connection_time and self.last_packet_time:
            elapsed = (self.last_packet_time - self.connection_time).total_seconds()
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}RESUMEN DE EMISIÓN WEBSOCKET{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")
        
        if self.packets_received == 0:
            print(
                f"{Colors.RED}{Colors.BOLD}"
                f"✗ CRÍTICO: No se recibieron paquetes del servidor.{Colors.RESET}\n"
                f"{Colors.RED}Posibles causas:{Colors.RESET}\n"
                f"  1. El servidor no está en puerto 8000\n"
                f"  2. MainOrchestrator no está emitiendo datos\n"
                f"  3. UI_Mapping_Service no está inicializado\n"
                f"  4. Firewall bloqueando WebSocket\n"
            )
            return
        
        print(f"{Colors.GREEN}{Colors.BOLD}✓ EMISIÓN CONFIRMADA{Colors.RESET}\n")
        print(f"{Colors.CYAN}Paquetes Recibidos: {Colors.BOLD}{self.packets_received}{Colors.RESET}")
        print(f"{Colors.CYAN}Duración: {Colors.BOLD}{elapsed:.1f}s{Colors.RESET}")
        print(f"{Colors.CYAN}Frecuencia: {Colors.BOLD}{self.packets_received / elapsed:.1f} pkt/s{Colors.RESET}\n")
        
        print(f"{Colors.BOLD}Distribución por Tipo:{Colors.RESET}")
        for msg_type, count in sorted(
            self.packets_by_type.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / self.packets_received) * 100
            print(f"  • {msg_type:<30} {count:>3} ({pct:>5.1f}%)")
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")


async def main():
    """Punto de entrada principal."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}[EXEC-UI-VALIDATION-FIX] WebSocket Emission Validator{Colors.RESET}")
    print(f"{Colors.CYAN}Actúa como cliente externo para validar emisión de datos reales{Colors.RESET}\n")
    
    tester = WebSocketTester(uri="ws://localhost:8000/ws/GENERIC/test_ws_validator")
    
    # Conectar
    if not await tester.connect():
        return 1
    
    # Escuchar (30 segundos por defecto)
    try:
        await tester.listen(duration=30)
    except KeyboardInterrupt:
        logger.info(f"\n{Colors.YELLOW}Interrumpido por usuario{Colors.RESET}")
    finally:
        await tester.disconnect()
    
    # Mostrar resumen
    tester.print_summary()
    
    # Retornar código de éxito si recibió algo
    return 0 if tester.packets_received > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
