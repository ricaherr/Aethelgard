"""
Models for SHADOW EVOLUTION v2.1: Multi-Instance Strategy Incubation Protocol.

RULE DB-1: All table names use sys_ prefix
RULE ID-1: All decisions generate TRACE_ID_ with temporal pattern

Trace_ID Base: TRACE_HEALTH_{YYYYMMDD_HHMMSS}_{instance_id[:8]}
              TRACE_PROMOTION_REAL_{YYYYMMDD_HHMMSS}_{instance_id[:8]}
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from decimal import Decimal


class HealthStatus(str, Enum):
    """Instance health evaluation result after 3 Pilares check."""
    HEALTHY = "HEALTHY"           # 3/3 Pilares PASS
    DEAD = "DEAD"                 # Any Pilar fails permanently
    QUARANTINED = "QUARANTINED"   # Pilar weakness detected (7d cooldown)
    MONITOR = "MONITOR"           # Pilar needs observation (14d)
    INCUBATING = "INCUBATING"     # Bootstrap phase (0-15 trades)


class ShadowStatus(str, Enum):
    """Instance operational status in account."""
    INCUBATING = "INCUBATING"           # Created, waiting for data
    SHADOW_READY = "SHADOW_READY"       # Candidate for promotion (3/3 Pilares PASS)
    PROMOTED_TO_REAL = "PROMOTED_TO_REAL"  # Active in REAL account
    DEAD = "DEAD"                       # Excluded permanently
    QUARANTINED = "QUARANTINED"         # Suspended (waiting retest)


class PillarStatus(str, Enum):
    """Individual Pilar evaluation result."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ShadowMetrics:
    """Performance metrics for 3 Pilares evaluation + 13 confirmatory metrics."""
    
    # PILAR 1: PROFITABILIDAD (Gana dinero?)
    profit_factor: float = 0.0              # PnL_ganada / PnL_perdida
    win_rate: float = 0.0                   # % trades ganadores
    
    # PILAR 2: RESILIENCIA (Sobrevive stress?)
    max_drawdown_pct: float = 0.0           # Máxima caída (%)
    consecutive_losses_max: int = 0         # Máximo de pérdidas seguidas
    
    # PILAR 3: CONSISTENCIA (Es predecible?)
    equity_curve_cv: float = 0.0            # Coefficient of variation
    total_trades_executed: int = 0          # Número de trades
    
    # 13 CONFIRMATORY METRICS (apoyo a Pilares, no criterio principal)
    calmar_ratio: float = 0.0               # (5) Métrica 5
    trade_frequency_per_day: float = 0.0    # (6) Métrica 6
    avg_slippage_pips: float = 0.0          # (7) Métrica 7
    recovery_factor: float = 0.0            # (8) Métrica 8
    avg_trade_duration_hours: float = 0.0   # (9) Métrica 9
    risk_reward_ratio: float = 0.0          # (11) Métrica 11
    zero_profit_days_pct: float = 0.0       # (12) Métrica 12
    last_activity_hours_ago: float = 0.0    # (13) Métrica 13
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for DB storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ShadowMetrics":
        """Create instance from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class ShadowInstance:
    """
    SHADOW instance: Una configuración ejecutable en el pool DEMO.
    
    Gobernanza MULTI-INSTANCIA (RULE DB-1):
    - Cada instancia = estrategia + parámetros únicos
    - Todas ejecutan en PARALELO dentro MISMO account DEMO
    - Evaluación autónoma cada lunes (Darwinian selection)
    - Trace_ID para toda decisión (RULE ID-1)
    """
    
    instance_id: str                     # UUID único
    strategy_id: str                     # BRK_OPEN_0001, OliverVelez, etc.
    account_id: str                      # FK to account (DEMO = MT5_DEMO_001)
    account_type: str                    # DEMO o REAL (inmutable)
    
    parameter_overrides: Dict = field(default_factory=dict)  # {"risk_pct": 0.02}
    regime_filters: List[str] = field(default_factory=list)  # ["TREND_UP", "EXPANSION"]
    
    birth_timestamp: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    status: ShadowStatus = ShadowStatus.INCUBATING
    metrics: ShadowMetrics = field(default_factory=ShadowMetrics)
    
    promotion_trace_id: Optional[str] = None     # TRACE_PROMOTION_REAL_...
    backtest_trace_id: Optional[str] = None      # TRACE_BACKTEST_...
    health_trace_ids: List[str] = field(default_factory=list)  # [TRACE_HEALTH_...]
    
    def __post_init__(self) -> None:
        """Validations after initialization."""
        if not self.instance_id or not self.strategy_id:
            raise ValueError("instance_id and strategy_id are required")
        if self.account_type not in ("DEMO", "REAL"):
            raise ValueError(f"account_type must be DEMO or REAL, got {self.account_type}")
    
    def to_db_dict(self) -> Dict:
        """Convert to dictionary format for DB insertion."""
        return {
            "instance_id": self.instance_id,
            "strategy_id": self.strategy_id,
            "account_id": self.account_id,
            "account_type": self.account_type,
            "parameter_overrides": str(self.parameter_overrides),  # JSON string
            "regime_filters": ",".join(self.regime_filters),
            "birth_timestamp": self.birth_timestamp.isoformat(),
            "status": self.status.value,
            "total_trades_executed": self.metrics.total_trades_executed,
            "profit_factor": self.metrics.profit_factor,
            "win_rate": self.metrics.win_rate,
            "max_drawdown_pct": self.metrics.max_drawdown_pct,
            "consecutive_losses_max": self.metrics.consecutive_losses_max,
            "equity_curve_cv": self.metrics.equity_curve_cv,
            "promotion_trace_id": self.promotion_trace_id,
            "backtest_trace_id": self.backtest_trace_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_db_dict(cls, data: Dict) -> "ShadowInstance":
        """Create instance from DB row dict."""
        metrics = ShadowMetrics(
            profit_factor=data.get("profit_factor", 0.0),
            win_rate=data.get("win_rate", 0.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            consecutive_losses_max=data.get("consecutive_losses_max", 0),
            equity_curve_cv=data.get("equity_curve_cv", 0.0),
            total_trades_executed=data.get("total_trades_executed", 0),
        )
        
        return cls(
            instance_id=data["instance_id"],
            strategy_id=data["strategy_id"],
            account_id=data.get("account_id", ""),
            account_type=data["account_type"],
            parameter_overrides=eval(data.get("parameter_overrides", "{}")),
            regime_filters=data.get("regime_filters", "").split(",") if data.get("regime_filters") else [],
            birth_timestamp=datetime.fromisoformat(data.get("birth_timestamp", datetime.now().isoformat())),
            status=ShadowStatus(data.get("status", "INCUBATING")),
            metrics=metrics,
            promotion_trace_id=data.get("promotion_trace_id"),
            backtest_trace_id=data.get("backtest_trace_id"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
        )
    
    def evaluate_health(self) -> Tuple[HealthStatus, str]:
        """
        Evaluate instance health by 3 Pilares ONLY.
        
        Returns:
            (HealthStatus, reason_if_failure)
        """
        # PILAR 1: PROFITABILIDAD
        pillar1_alive = (
            self.metrics.profit_factor >= 1.5 and 
            self.metrics.win_rate >= 0.60
        )
        
        # PILAR 2: RESILIENCIA
        pillar2_alive = (
            self.metrics.max_drawdown_pct <= 12.0 and 
            self.metrics.consecutive_losses_max <= 3
        )
        
        # PILAR 3: CONSISTENCIA
        pillar3_alive = (
            self.metrics.total_trades_executed >= 15 and 
            self.metrics.equity_curve_cv <= 0.40
        )
        
        # Decision logic
        if not pillar1_alive and self.metrics.total_trades_executed >= 15:
            return HealthStatus.DEAD, f"Pilar 1 FALLIDO (PF={self.metrics.profit_factor}, WR={self.metrics.win_rate})"
        
        if not pillar2_alive:
            return HealthStatus.QUARANTINED, f"Pilar 2 COMPROMETIDO (DD={self.metrics.max_drawdown_pct}%, CL={self.metrics.consecutive_losses_max})"
        
        if not pillar3_alive:
            return HealthStatus.MONITOR, f"Pilar 3 BAJO REVISIÓN (Trades={self.metrics.total_trades_executed}, CV={self.metrics.equity_curve_cv})"
        
        if self.metrics.total_trades_executed < 15:
            return HealthStatus.INCUBATING, "Bootstrap phase (< 15 trades)"
        
        return HealthStatus.HEALTHY, "3/3 Pilares PASSED"
    
    def is_promotable_to_real(self) -> Tuple[bool, str]:
        """
        Check if instance can be promoted to REAL account.
        
        Requirements:
        - HealthStatus == HEALTHY
        - 3/3 Pilares must PASS
        
        Returns:
            (is_promotable, reason_if_not)
        """
        health_status, reason = self.evaluate_health()
        
        if health_status != HealthStatus.HEALTHY:
            return False, f"Cannot promote: {reason}"
        
        if self.metrics.total_trades_executed < 15:
            return False, "Not enough trades for reliable promotion"
        
        return True, "Ready for promotion to REAL"


@dataclass
class ShadowPerformanceHistory:
    """
    Daily performance snapshot for audit trail.
    Cada evaluación semanal graba 3 Pilares status.
    """
    id: Optional[int] = None
    instance_id: str = ""
    evaluation_date: datetime = field(default_factory=datetime.now)
    
    pillar1_status: PillarStatus = PillarStatus.UNKNOWN
    pillar2_status: PillarStatus = PillarStatus.UNKNOWN
    pillar3_status: PillarStatus = PillarStatus.UNKNOWN
    
    overall_health: HealthStatus = HealthStatus.INCUBATING
    event_trace_id: str = ""
    
    def to_db_dict(self) -> Dict:
        return {
            "instance_id": self.instance_id,
            "evaluation_date": self.evaluation_date.date().isoformat(),
            "pillar1_status": self.pillar1_status.value,
            "pillar2_status": self.pillar2_status.value,
            "pillar3_status": self.pillar3_status.value,
            "overall_health": self.overall_health.value,
            "event_trace_id": self.event_trace_id,
        }
    
    @classmethod
    def from_db_dict(cls, data: Dict) -> "ShadowPerformanceHistory":
        return cls(
            id=data.get("id"),
            instance_id=data["instance_id"],
            evaluation_date=datetime.fromisoformat(data.get("evaluation_date", datetime.now().isoformat())),
            pillar1_status=PillarStatus(data.get("pillar1_status", "UNKNOWN")),
            pillar2_status=PillarStatus(data.get("pillar2_status", "UNKNOWN")),
            pillar3_status=PillarStatus(data.get("pillar3_status", "UNKNOWN")),
            overall_health=HealthStatus(data.get("overall_health", "INCUBATING")),
            event_trace_id=data.get("event_trace_id", ""),
        )


@dataclass
class ShadowPromotionLog:
    """
    Immutable audit log for promotions to REAL.
    INSERT-ONLY, never modified or deleted (RULE DB-1).
    """
    promotion_id: Optional[int] = None
    instance_id: str = ""
    trace_id: str = ""  # TRACE_PROMOTION_REAL_20260312_...
    promotion_status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXECUTED
    
    pillar1_passed: bool = False
    pillar2_passed: bool = False
    pillar3_passed: bool = False
    
    approval_timestamp: datetime = field(default_factory=datetime.now)
    execution_timestamp: Optional[datetime] = None
    
    notes: str = ""
    
    def to_db_dict(self) -> Dict:
        return {
            "instance_id": self.instance_id,
            "trace_id": self.trace_id,
            "promotion_status": self.promotion_status,
            "pillar1_passed": bool(self.pillar1_passed),
            "pillar2_passed": bool(self.pillar2_passed),
            "pillar3_passed": bool(self.pillar3_passed),
            "approval_timestamp": self.approval_timestamp.isoformat(),
            "execution_timestamp": self.execution_timestamp.isoformat() if self.execution_timestamp else None,
            "notes": self.notes,
        }
    
    @classmethod
    def from_db_dict(cls, data: Dict) -> "ShadowPromotionLog":
        return cls(
            promotion_id=data.get("promotion_id"),
            instance_id=data["instance_id"],
            trace_id=data["trace_id"],
            promotion_status=data.get("promotion_status", "PENDING"),
            pillar1_passed=bool(data.get("pillar1_passed", False)),
            pillar2_passed=bool(data.get("pillar2_passed", False)),
            pillar3_passed=bool(data.get("pillar3_passed", False)),
            approval_timestamp=datetime.fromisoformat(data.get("approval_timestamp", datetime.now().isoformat())),
            execution_timestamp=datetime.fromisoformat(data["execution_timestamp"]) if data.get("execution_timestamp") else None,
            notes=data.get("notes", ""),
        )
