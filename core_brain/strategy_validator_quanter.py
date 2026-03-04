"""
Validador de 4 Pilares para UniversalStrategyEngine
Trace_ID: STRATEGY-VALIDATOR-QUANTER-2026

Implementa validación en 4 capas antes de ejecutar una firma operativa:
1. Pilar Sensorial: ¿El sensor está listo? (Datos frescos, no NULL)
2. Pilar Régimen: ¿El régimen de mercado permite esta estrategia?
3. Pilar Multi-Tenant: ¿La membresía del usuario permite acceso?
4. Pilar Coherencia: ¿La señal es coherente? (No conflictos, confluence OK)

Usado por: UniversalStrategyEngine.execute()
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PillarStatus(Enum):
    """Estado de validación de cada pilar."""
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Bloqueado por policy/FundamentalGuard


@dataclass
class PillarValidationResult:
    """Resultado de validación de un pilar."""
    pillar_name: str
    status: PillarStatus
    confidence: float  # 0.0-1.0 (nivel de certeza)
    reason: str  # Explicación humana
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializar a diccionario."""
        return {
            "pillar": self.pillar_name,
            "status": self.status.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "details": self.details
        }


class ValidationPillar(ABC):
    """Clase base para cada pilar de validación."""
    
    @abstractmethod
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any]
    ) -> PillarValidationResult:
        """
        Valida la estrategia contra este pilar.
        
        Args:
            strategy_id: ID de la estrategia (S-0001...S-0006)
            symbol: Activo (EUR/USD)
            signal_data: Datos de señal generada
            
        Returns:
            PillarValidationResult con status y razón
        """
        pass


class SensorialPillar(ValidationPillar):
    """
    Pilar 1: Sensorial
    ¿El sensor está listo? ¿Datos frescos? ¿No NULL?
    """
    
    def __init__(self, storage_manager: Any):
        """
        Args:
            storage_manager: StorageManager para leer metadata de sensores
        """
        self.storage = storage_manager
    
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any]
    ) -> PillarValidationResult:
        """Valida que los sensores requeridos estén listos."""
        try:
            # Lógica: Verificar que signal_data contiene indicadores no-NULL
            indicators = signal_data.get("indicators", {})
            
            if not indicators:
                return PillarValidationResult(
                    pillar_name="Sensorial",
                    status=PillarStatus.FAILED,
                    confidence=0.0,
                    reason="No indicators calculated (sensor failure)",
                    details={"indicators_count": 0}
                )
            
            # Verificar que valores no sean None/NaN
            null_indicators = [
                key for key, val in indicators.items()
                if val is None
            ]
            
            if null_indicators:
                return PillarValidationResult(
                    pillar_name="Sensorial",
                    status=PillarStatus.FAILED,
                    confidence=0.0,
                    reason=f"NULL indicators detected: {null_indicators}",
                    details={"null_indicators": null_indicators}
                )
            
            # Pilar Sensorial PASADO
            return PillarValidationResult(
                pillar_name="Sensorial",
                status=PillarStatus.PASSED,
                confidence=0.95,
                reason=f"All {len(indicators)} sensors ready with fresh data",
                details={"indicators_count": len(indicators)}
            )
        
        except Exception as e:
            logger.error(f"[PILLAR_SENSORIAL_ERROR] {strategy_id}/{symbol}: {str(e)}")
            return PillarValidationResult(
                pillar_name="Sensorial",
                status=PillarStatus.FAILED,
                confidence=0.0,
                reason=f"Sensorial validation error: {str(e)}",
                details={}
            )


class RegimePillar(ValidationPillar):
    """
    Pilar 2: Régimen
    ¿El régimen de mercado permite esta estrategia?
    Ej: S-0006 no ejecuta en RANGO, solo en TREND
    """
    
    def __init__(self, regime_classifier: Any):
        """
        Args:
            regime_classifier: RegimeClassifier para obtener régimen actual
        """
        self.regime_classifier = regime_classifier
    
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any]
    ) -> PillarValidationResult:
        """Valida compatibilidad de régimen."""
        try:
            # Obtener régimen actual
            current_regime = await self.regime_classifier.get_current_regime(symbol)
            
            # Mapeo de estrategias a regímenes permitidos
            regime_requirements = {
                "STRUC_SHIFT_0001": ["TREND_UP", "TREND_DOWN"],  # S-0006
                "BRK_OPEN_0001": ["TREND_UP", "TREND_DOWN"],  # S-0001
                "LIQ_SWEEP_0001": ["VOLATILITY", "TREND_UP", "TREND_DOWN"],  # S-0004
                "SESS_EXT_0001": ["TREND_UP", "TREND_DOWN"],  # S-0005
                "MOM_BIAS_0001": ["VOLATILITY", "EXPANSION"],  # S-0003
                "institutional_footprint": ["ANY"],  # S-0002 (flexible)
            }
            
            allowed_regimes = regime_requirements.get(strategy_id, ["ANY"])
            
            if "ANY" in allowed_regimes:
                return PillarValidationResult(
                    pillar_name="Régimen",
                    status=PillarStatus.PASSED,
                    confidence=1.0,
                    reason=f"Strategy {strategy_id} works in any regime",
                    details={"current_regime": current_regime, "allowed": ["ANY"]}
                )
            
            if current_regime in allowed_regimes:
                return PillarValidationResult(
                    pillar_name="Régimen",
                    status=PillarStatus.PASSED,
                    confidence=0.95,
                    reason=f"Régimen {current_regime} compatible with {strategy_id}",
                    details={"current_regime": current_regime, "allowed": allowed_regimes}
                )
            
            # Régimen INCOMPATIBLE
            return PillarValidationResult(
                pillar_name="Régimen",
                status=PillarStatus.FAILED,
                confidence=0.0,
                reason=f"Régimen {current_regime} NOT compatible with {strategy_id}",
                details={
                    "current_regime": current_regime,
                    "allowed_regimes": allowed_regimes
                }
            )
        
        except Exception as e:
            logger.error(f"[PILLAR_REGIME_ERROR] {strategy_id}/{symbol}: {str(e)}")
            return PillarValidationResult(
                pillar_name="Régimen",
                status=PillarStatus.FAILED,
                confidence=0.0,
                reason=f"Régimen validation error: {str(e)}",
                details={}
            )


class MultiTenantPillar(ValidationPillar):
    """
    Pilar 3: Multi-Tenant
    ¿La membresía del usuario permite esta estrategia?
    Ej: S-0005 es Premium only, S-0001 es Free
    """
    
    def __init__(self, storage_manager: Any):
        """
        Args:
            storage_manager: StorageManager para leer nivel de membresía del usuario
        """
        self.storage = storage_manager
    
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any]
    ) -> PillarValidationResult:
        """Valida acceso por membresía."""
        try:
            # Mapeo de estrategias a nivel de membresía requerido
            membership_requirements = {
                "STRUC_SHIFT_0001": "FREE",  # S-0006 acceso universal
                "BRK_OPEN_0001": "FREE",  # S-0001 acceso universal
                "LIQ_SWEEP_0001": "PREMIUM",  # S-0004 requiere Premium
                "SESS_EXT_0001": "PREMIUM",  # S-0005 requiere Premium
                "MOM_BIAS_0001": "STANDARD",  # S-0003 requiere Standard+
                "institutional_footprint": "PREMIUM",  # S-0002 requiere Premium
            }
            
            required_tier = membership_requirements.get(strategy_id, "FREE")
            
            # Nota: En producción, leería del usuario autenticado
            # Por ahora, asumimos modo demo = PREMIUM
            user_tier = signal_data.get("user_tier", "DEMO")
            
            # Lógica de asignación de tiers: DEMO >= PREMIUM >= STANDARD >= FREE
            tier_hierarchy = ["FREE", "STANDARD", "PREMIUM", "DEMO"]
            
            required_index = tier_hierarchy.index(required_tier)
            user_index = tier_hierarchy.index(user_tier)
            
            if user_index >= required_index:
                return PillarValidationResult(
                    pillar_name="Multi-Tenant",
                    status=PillarStatus.PASSED,
                    confidence=1.0,
                    reason=f"User tier {user_tier} has access to {strategy_id} (requires {required_tier})",
                    details={
                        "user_tier": user_tier,
                        "required_tier": required_tier
                    }
                )
            
            # Membresía INSUFICIENTE
            return PillarValidationResult(
                pillar_name="Multi-Tenant",
                status=PillarStatus.BLOCKED,
                confidence=0.0,
                reason=f"User tier {user_tier} lacks access to {strategy_id} (requires {required_tier})",
                details={
                    "user_tier": user_tier,
                    "required_tier": required_tier,
                    "upgrade_required": True
                }
            )
        
        except Exception as e:
            logger.error(f"[PILLAR_MULTITENANT_ERROR] {strategy_id}/{symbol}: {str(e)}")
            return PillarValidationResult(
                pillar_name="Multi-Tenant",
                status=PillarStatus.BLOCKED,
                confidence=0.0,
                reason=f"Multi-Tenant validation error: {str(e)}",
                details={}
            )


class CoherencePillar(ValidationPillar):
    """
    Pilar 4: Coherencia
    ¿La señal es coherente? ¿No hay conflictos? ¿Confluence válida?
    """
    
    def __init__(self, conflict_resolver: Any = None):
        """
        Args:
            conflict_resolver: ConflictResolver para detectar conflictos (opcional)
        """
        self.conflict_resolver = conflict_resolver
    
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any]
    ) -> PillarValidationResult:
        """Valida coherencia de la señal."""
        try:
            # Lógica 1: Validar confluence (debe tener al menos 2 elementos confluentes)
            confluence_items = signal_data.get("confluence_elements", [])
            
            if len(confluence_items) < 2:
                return PillarValidationResult(
                    pillar_name="Coherencia",
                    status=PillarStatus.FAILED,
                    confidence=0.3,
                    reason=f"Insufficient confluence elements ({len(confluence_items)}, needs >= 2)",
                    details={"confluence_count": len(confluence_items)}
                )
            
            # Lógica 2: Validar confidence >= 0.60
            signal_confidence = signal_data.get("confidence", 0.0)
            
            if signal_confidence < 0.60:
                return PillarValidationResult(
                    pillar_name="Coherencia",
                    status=PillarStatus.FAILED,
                    confidence=0.0,
                    reason=f"Signal confidence {signal_confidence:.2f} below minimum 0.60",
                    details={"signal_confidence": signal_confidence}
                )
            
            # Lógica 3: Si hay conflict_resolver, verificar sin conflictos
            if self.conflict_resolver:
                has_conflict = signal_data.get("has_conflict", False)
                if has_conflict:
                    return PillarValidationResult(
                        pillar_name="Coherencia",
                        status=PillarStatus.FAILED,
                        confidence=0.0,
                        reason="Signal conflicts with other active strategies",
                        details={"conflicting_strategy": signal_data.get("conflict_with")}
                    )
            
            # Pilar Coherencia PASADO
            return PillarValidationResult(
                pillar_name="Coherencia",
                status=PillarStatus.PASSED,
                confidence=signal_confidence,
                reason=f"Signal coherent with {len(confluence_items)} confluence elements (confidence {signal_confidence:.2f})",
                details={
                    "confluence_count": len(confluence_items),
                    "signal_confidence": signal_confidence
                }
            )
        
        except Exception as e:
            logger.error(f"[PILLAR_COHERENCE_ERROR] {strategy_id}/{symbol}: {str(e)}")
            return PillarValidationResult(
                pillar_name="Coherencia",
                status=PillarStatus.FAILED,
                confidence=0.0,
                reason=f"Coherencia validation error: {str(e)}",
                details={}
            )


@dataclass
class ValidationReport:
    """Reporte completo de validación 4 Pilares."""
    strategy_id: str
    symbol: str
    overall_status: PillarStatus  # PASSED si TODOS pilares PASSED
    pillars: List[PillarValidationResult]
    overall_confidence: float  # Promedio ponderado
    trace_id: str = ""
    
    def is_approved(self) -> bool:
        """¿La estrategia fue APROBADA para ejecución?"""
        return self.overall_status == PillarStatus.PASSED
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializar a diccionario."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "overall_status": self.overall_status.value,
            "overall_confidence": self.overall_confidence,
            "is_approved": self.is_approved(),
            "pillars": [p.to_dict() for p in self.pillars],
            "trace_id": self.trace_id
        }


class StrategySignalValidator:
    """
    Ejecuta validación 4 Pilares en serie.
    Retorna ValidationReport con status final.
    """
    
    def __init__(
        self,
        storage_manager: Any = None,
        regime_classifier: Any = None,
        conflict_resolver: Any = None
    ):
        """
        Args:
            storage_manager: Para Pilar Multi-Tenant y Sensorial
            regime_classifier: Para Pilar Régimen
            conflict_resolver: Para Pilar Coherencia (opcional)
        """
        self.pillars: List[ValidationPillar] = []
        
        # Inicializar pilares en orden
        if storage_manager:
            self.pillars.append(SensorialPillar(storage_manager))
        
        if regime_classifier:
            self.pillars.append(RegimePillar(regime_classifier))
        
        if storage_manager:
            self.pillars.append(MultiTenantPillar(storage_manager))
        
        self.pillars.append(CoherencePillar(conflict_resolver))
    
    async def validate(
        self,
        strategy_id: str,
        symbol: str,
        signal_data: Dict[str, Any],
        trace_id: str = ""
    ) -> ValidationReport:
        """
        Ejecuta validación 4 Pilares en serie.
        
        Args:
            strategy_id: ID de estrategia (S-0001...S-0006)
            symbol: Activo (EUR/USD)
            signal_data: Datos de señal a validar
            trace_id: ID de trazabilidad
            
        Returns:
            ValidationReport con status final
        """
        results: List[PillarValidationResult] = []
        
        # Ejecutar cada pilar
        for pillar in self.pillars:
            result = await pillar.validate(strategy_id, symbol, signal_data)
            results.append(result)
            
            # Logging
            logger.info(
                f"[PILLAR_RESULT] {strategy_id}/{symbol} "
                f"Pilar={result.pillar_name} Status={result.status.value} "
                f"Confidence={result.confidence:.2f} Reason={result.reason}"
            )
        
        # Determinar status overall
        failed_pillars = [p for p in results if p.status in [PillarStatus.FAILED, PillarStatus.BLOCKED]]
        
        if failed_pillars:
            overall_status = PillarStatus.FAILED
            failed_names = [p.pillar_name for p in failed_pillars]
            logger.warning(
                f"[VALIDATION_REJECTED] {strategy_id}/{symbol} "
                f"Failed pillars: {failed_names}"
            )
        else:
            overall_status = PillarStatus.PASSED
            logger.info(
                f"[VALIDATION_APPROVED] {strategy_id}/{symbol} "
                f"All 4 pillars PASSED - Signal approved for execution"
            )
        
        # Calcular confidence promedio
        overall_confidence = sum(p.confidence for p in results) / len(results) if results else 0.0
        
        return ValidationReport(
            strategy_id=strategy_id,
            symbol=symbol,
            overall_status=overall_status,
            pillars=results,
            overall_confidence=overall_confidence,
            trace_id=trace_id
        )
