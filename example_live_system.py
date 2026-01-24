"""
Ejemplo de Integración Completa: Scanner + Signal Factory + MT5 Bridge
Demuestra el flujo completo de Aethelgard con ejecución automática en MT5 Demo
"""
import asyncio
import logging
from pathlib import Path

# Core Brain
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory

# Connectors
from connectors.mt5_data_provider import MT5DataProvider
from connectors.bridge_mt5 import MT5Bridge

# Models
from models.signal import ConnectorType, MembershipTier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AethelgardLiveSystem:
    """
    Sistema completo de Aethelgard con:
    - Scanner proactivo multihilo
    - Signal Factory con scoring Oliver Vélez
    - Ejecución automática en MT5 Demo
    """
    
    def __init__(
        self,
        assets: list[str],
        mt5_bridge_url: str = "ws://localhost:8000/ws/MT5/",
        auto_execute: bool = True,
        demo_mode: bool = True,
        scan_mode: str = "STANDARD"
    ):
        """
        Args:
            assets: Lista de símbolos a escanear
            mt5_bridge_url: URL del servidor WebSocket
            auto_execute: Ejecutar señales automáticamente
            demo_mode: Solo ejecutar en cuenta demo
            scan_mode: Modo de escaneo (ECO, STANDARD, AGRESSIVE)
        """
        self.assets = assets
        
        # Inicializar componentes
        logger.info("🚀 Inicializando Aethelgard Live System...")
        
        # 1. Data Provider
        self.data_provider = MT5DataProvider()
        logger.info("✓ MT5 Data Provider inicializado")
        
        # 2. Scanner Engine
        self.scanner = ScannerEngine(
            assets=assets,
            data_provider=self.data_provider,
            config_path="config/config.json",
            scan_mode=scan_mode
        )
        logger.info(f"✓ Scanner Engine inicializado en modo {scan_mode}")
        
        # 3. Signal Factory
        self.signal_factory = SignalFactory(
            connector_type=ConnectorType.METATRADER5,
            strategy_id="oliver_velez_swing_v1",
            premium_threshold=80.0,
            elite_threshold=90.0
        )
        logger.info("✓ Signal Factory inicializado (Oliver Vélez)")
        
        # 4. MT5 Bridge (se inicializa en async)
        self.mt5_bridge_url = mt5_bridge_url
        self.auto_execute = auto_execute
        self.demo_mode = demo_mode
        self.mt5_bridge = None
        
        # Estado
        self.running = False
    
    async def initialize_bridge(self):
        """Inicializa el bridge de MT5 de forma asíncrona"""
        try:
            self.mt5_bridge = MT5Bridge(
                server_url=self.mt5_bridge_url,
                symbol=self.assets[0] if self.assets else "EURUSD",
                auto_execute=self.auto_execute,
                demo_mode=self.demo_mode
            )
            await self.mt5_bridge.connect()
            logger.info("✓ MT5 Bridge conectado")
        except Exception as e:
            logger.error(f"Error inicializando MT5 Bridge: {e}")
            raise
    
    def scan_and_generate_signals(self) -> list:
        """
        Ejecuta un ciclo de escaneo y genera señales
        
        Returns:
            Lista de señales generadas
        """
        signals = []
        
        # Obtener estado del scanner
        status = self.scanner.get_status()
        last_regimes = status.get("last_regime", {})
        
        # Escanear cada activo
        for symbol in self.assets:
            try:
                # Obtener datos OHLC
                df = self.data_provider.fetch_ohlc(symbol, timeframe="M5", count=500)
                
                if df is None or df.empty:
                    logger.debug(f"Sin datos para {symbol}")
                    continue
                
                # Obtener régimen del scanner
                regime_str = last_regimes.get(symbol, "NEUTRAL")
                
                # Importar MarketRegime para conversión
                from models.signal import MarketRegime
                regime = MarketRegime(regime_str)
                
                # Generar señal
                signal = self.signal_factory.generate_signal(
                    symbol=symbol,
                    df=df,
                    regime=regime
                )
                
                if signal:
                    signals.append(signal)
            
            except Exception as e:
                logger.error(f"Error procesando {symbol}: {e}")
                continue
        
        return signals
    
    async def process_signals(self, signals: list):
        """
        Procesa señales y las envía al MT5 Bridge para ejecución
        
        Args:
            signals: Lista de señales generadas
        """
        if not signals:
            return
        
        logger.info(f"📊 Procesando {len(signals)} señales...")
        
        for signal in signals:
            try:
                # Convertir señal a dict para envío
                signal_dict = {
                    "type": "signal",
                    "connector": signal.connector.value,
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type.value,
                    "price": signal.price,
                    "volume": signal.volume,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "timestamp": signal.timestamp.isoformat(),
                    "regime": signal.regime.value if signal.regime else None,
                    "strategy_id": signal.strategy_id,
                    "score": signal.score,
                    "membership_tier": signal.membership_tier.value,
                    "is_elephant_candle": signal.is_elephant_candle,
                    "volume_above_average": signal.volume_above_average,
                    "near_sma20": signal.near_sma20,
                    "metadata": signal.metadata
                }
                
                # Enviar al bridge para ejecución
                if self.mt5_bridge:
                    await self.mt5_bridge.handle_signal(signal_dict)
                
                # Log
                logger.info(
                    f"✉️  Señal enviada: {signal.symbol} {signal.signal_type.value} | "
                    f"Score: {signal.score:.1f} | Tier: {signal.membership_tier.value}"
                )
            
            except Exception as e:
                logger.error(f"Error procesando señal: {e}")
    
    async def run_cycle(self):
        """Ejecuta un ciclo completo: escaneo -> señales -> ejecución"""
        try:
            # 1. Ejecutar un ciclo del scanner (actualiza regímenes)
            self.scanner._run_cycle()
            
            # 2. Generar señales basadas en el estado actual
            signals = self.scan_and_generate_signals()
            
            # 3. Procesar y ejecutar señales
            await self.process_signals(signals)
            
            # 4. Estadísticas
            if signals:
                premium_signals = [s for s in signals if s.membership_tier == MembershipTier.PREMIUM]
                elite_signals = [s for s in signals if s.membership_tier == MembershipTier.ELITE]
                
                logger.info(
                    f"📈 Ciclo completado: {len(signals)} señales | "
                    f"Premium: {len(premium_signals)} | Elite: {len(elite_signals)}"
                )
        
        except Exception as e:
            logger.error(f"Error en ciclo: {e}", exc_info=True)
    
    async def run(self, interval: float = 60.0):
        """
        Ejecuta el sistema completo en bucle
        
        Args:
            interval: Intervalo entre ciclos (segundos)
        """
        self.running = True
        
        try:
            # Inicializar bridge
            await self.initialize_bridge()
            
            logger.info(f"🎯 Sistema Aethelgard activo. Intervalo: {interval}s")
            logger.info(f"📊 Escaneando: {', '.join(self.assets)}")
            logger.info(f"🤖 Auto-ejecución: {'HABILITADO' if self.auto_execute else 'DESHABILITADO'}")
            logger.info(f"🔐 Modo: {'DEMO' if self.demo_mode else 'REAL'}")
            logger.info("=" * 60)
            
            # Bucle principal
            while self.running:
                await self.run_cycle()
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("⏸️  Interrupción recibida. Deteniendo sistema...")
        except Exception as e:
            logger.error(f"Error fatal en sistema: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Cierra todos los componentes del sistema"""
        logger.info("🛑 Cerrando sistema...")
        
        self.running = False
        
        # Detener scanner
        if self.scanner:
            self.scanner.stop()
            logger.info("✓ Scanner detenido")
        
        # Desconectar bridge
        if self.mt5_bridge:
            await self.mt5_bridge.disconnect()
            logger.info("✓ MT5 Bridge desconectado")
        
        logger.info("✅ Sistema cerrado correctamente")


async def main():
    """Función principal para ejecutar el sistema"""
    
    # Configuración
    ASSETS = [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "GOLD",
        "US30"
    ]
    
    # Crear sistema
    system = AethelgardLiveSystem(
        assets=ASSETS,
        mt5_bridge_url="ws://localhost:8000/ws/MT5/",
        auto_execute=True,  # Ejecutar automáticamente en demo
        demo_mode=True,     # Solo en demo
        scan_mode="STANDARD"  # ECO, STANDARD, AGRESSIVE
    )
    
    # Ejecutar (ciclos cada 60 segundos)
    await system.run(interval=60.0)


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🏰  AETHELGARD LIVE TRADING SYSTEM  🏰            ║
    ║                                                           ║
    ║  Scanner Proactivo + Signal Factory + MT5 Auto-Execute   ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())
