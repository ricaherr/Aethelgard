export type MarketRegime = 'TREND' | 'RANGE' | 'VOLATILE' | 'SHOCK' | 'BULL' | 'BEAR' | 'CRASH' | 'NORMAL';
export type AssetType = 'forex' | 'metal' | 'crypto' | 'index';
export type ExecutionMode = 'LIVE' | 'SHADOW' | 'QUARANTINE';
export type RejectionReason = 'affinity' | 'whitelist' | 'budget' | 'freeze' | 'rollback' | 'quality' | 'other';

export interface Signal {
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    price: number;
    score: number;
    status: 'PENDING' | 'EXECUTED' | 'CANCELLED' | 'CLOSED';
    timestamp: string;
    magic_number: number;
    initial_risk_usd?: number;     // Risk preview (NEW)
    asset_type?: AssetType;         // Asset classification (NEW)
    execution_mode?: ExecutionMode; // LIVE | SHADOW | QUARANTINE (Darwinismo Algorítmico)
    ranking_score?: number;         // 0-100 score justifying signal quality/mode (Milestone 5)
    is_exploratory?: boolean;       // Tagged EXPLORATION_ON (generated in EDGE DEMO exploration cycle)
    rejection_reason?: RejectionReason; // Why the signal was rejected/quarantined
    demo_mode?: boolean;            // Signal generated in DEMO account mode
}

// Position metadata with risk calculation (NEW)
export interface PositionMetadata {
    ticket: number;
    symbol: string;
    type?: 'BUY' | 'SELL';           // Position type (inferred if not provided)
    entry_price: number;
    sl: number;
    tp: number;
    volume: number;
    profit_usd: number;
    initial_risk_usd: number;       // From RiskCalculator
    r_multiple: number;              // profit / initial_risk
    entry_regime: MarketRegime;
    entry_time: string;
    asset_type: AssetType;
    timeframe?: string;              // Trading timeframe (M5, H1, etc.)
    strategy?: string;               // Strategy name (RSI_MACD, etc.)
}

// Balance metadata (source indicator)
export interface BalanceMetadata {
    source: 'MT5_LIVE' | 'CACHED' | 'DEFAULT' | 'UNKNOWN' | 'ERROR';
    last_update: string;
    is_live: boolean;
}

// Risk summary for account (NEW)
export interface RiskSummary {
    total_risk_usd: number;
    account_balance: number;
    balance_metadata: BalanceMetadata;
    risk_percentage: number;
    max_allowed_risk_pct: number;
    positions_by_asset: Record<AssetType, { count: number; risk: number }>;
    warnings: string[];
}

// System modules status (NEW)
export interface ModulesStatus {
    modules: {
        scanner: boolean;
        executor: boolean;
        position_manager: boolean;
        risk_manager: boolean;
        monitor: boolean;
        notificator: boolean;
    };
    timestamp: string;
}

export interface SatelliteStatus {
    status: 'ONLINE' | 'OFFLINE' | 'MANUAL_DISABLED';
    latency: number;
    failures: number;
    supports_data?: boolean;
    supports_exec?: boolean;
    last_error?: string | null;
}

export interface SystemStatus {
    connected: boolean;
    lastUpdate: string;
    heartbeats: Record<string, string>;
    cpu_load?: number;
    satellites?: Record<string, SatelliteStatus>;
    sync_fidelity?: {
        score: number;
        status: 'OPTIMAL' | 'DEGRADED' | 'OUT_OF_SYNC';
        details: string;
    };
}

export interface EdgeMetrics {
    adx_strength: number;
    volatility: string;
    global_bias: string;
    confidence: number;
    active_agents: number;
    optimization_rate: number;
}

export interface CerebroThought {
    id: string;
    timestamp: string;
    level: 'info' | 'debug' | 'warning' | 'error' | 'success';
    message: string;
    module: string;
    metadata?: Record<string, any>;
}

export type EdgeEventType = 'PARAMETRIC_TUNING' | 'AUTONOMOUS_LEARNING';

export interface TuningLog {
    id: string | number;
    timestamp: string;
    type: EdgeEventType;
    trigger: string;
    // Parametric Fields
    adjustment_factor?: number;
    old_params?: Record<string, number>;
    new_params?: Record<string, number>;
    stats?: {
        total_trades: number;
        win_rate: number;
        consecutive_losses: number;
        [key: string]: any;
    };
    // Autonomous Learning Fields
    detection?: string;
    action_taken?: string;
    learning?: string;
    delta?: number;
    regime?: string;
    adjustment_made?: boolean;
    details?: string;
}

// ============================================================================
// SHADOW EVOLUTION v2.1: Multi-Instance Strategy Incubation Protocol (NEW)
// ============================================================================

export type HealthStatus = 'HEALTHY' | 'DEAD' | 'QUARANTINED' | 'MONITOR' | 'INCUBATING';
export type ShadowStatus = 'INCUBATING' | 'SHADOW_READY' | 'PROMOTED_TO_REAL' | 'DEAD' | 'QUARANTINED';
export type PillarStatus = 'PASS' | 'FAIL' | 'UNKNOWN';

export interface ExplorationState {
    active: boolean;
    assets_in_exploration: string[];
    budget_remaining: number;
    frozen_assets: string[];
    rollback_count: number;
    exploratory_pf: number;
    exploration_on_count: number;
    last_handshake?: string;
    handshake_logs?: string[];
}

// ============================================================================
// LOGIC_PENDING STRATEGY DIAGNOSTICS (ETI E3 — HU 3.1 / HU 3.2 / HU 3.7)
// ============================================================================

export type PendingCause =
    | 'MISSING_CLASS_FILE'
    | 'MISSING_LOGIC'
    | 'INVALID_LOGIC_JSON'
    | 'MISSING_SCHEMA_FILE'
    | 'NEEDS_IMPLEMENTATION'
    | 'UNKNOWN';

/** Modo de afinidad: 'fixed' = config estática protegida; 'dynamic' = aprendizaje reiniciable. */
export type AffinityMode = 'fixed' | 'dynamic';

export interface PendingStrategyDiagnosis {
    class_id: string;
    mnemonic: string;
    strategy_type: string;
    readiness: string;
    cause?: PendingCause;
    cause_detail?: string;
    suggestion?: string;
    auto_fixed?: boolean;
    /** Modo de afinidad de la estrategia. Determina si el reset de afinidad está disponible. */
    affinity_mode?: AffinityMode;
    last_checked?: string;
    description?: string;
}

export interface ShadowMetrics {
    // PILAR 1: PROFITABILIDAD
    profit_factor: number;
    win_rate: number;
    
    // PILAR 2: RESILIENCIA
    max_drawdown_pct: number;
    consecutive_losses_max: number;
    
    // PILAR 3: CONSISTENCIA
    equity_curve_cv: number;
    total_trades_executed: number;
    
    // 13 CONFIRMATORY METRICS
    calmar_ratio: number;
    trade_frequency_per_day: number;
    avg_slippage_pips: number;
    recovery_factor: number;
    avg_trade_duration_hours: number;
    risk_reward_ratio: number;
    zero_profit_days_pct: number;
    last_activity_hours_ago: number;
}

export interface ShadowInstance {
    instance_id: string;
    strategy_id: string;
    account_id: string;
    account_type: 'DEMO' | 'REAL';
    parameter_overrides: Record<string, any>;
    regime_filters: string[];
    birth_timestamp: string;
    created_at: string;
    health_status: HealthStatus;
    shadow_status: ShadowStatus;
    metrics: ShadowMetrics;
    last_evaluation: string;
    pilar1_status: PillarStatus;
    pilar2_status: PillarStatus;
    pilar3_status: PillarStatus;
    has_exploratory_signals?: boolean;
    exploratory_pf?: number;
    normal_pf?: number;
    edge_demo_frozen?: boolean;
}

export interface ActionEvent {
    id: string;
    timestamp: string;
    instance_id: string;
    action: 'PROMOTION' | 'DEMOTION' | 'QUARANTINE' | 'MONITOR' | 'FREEZE' | 'ROLLBACK';
    trace_id: string;
    message: string;
    metrics_snapshot: Partial<ShadowMetrics>;
}

export interface WebSocketShadowEvent {
    event_type: 'SHADOW_STATUS_UPDATE' | 'SHADOW_CONNECTION_ESTABLISHED' | 'EDGE_EXPLORATION_UPDATE';
    instance_id?: string;
    health_status?: HealthStatus;
    pilar1_status?: PillarStatus;
    pilar2_status?: PillarStatus;
    pilar3_status?: PillarStatus;
    metrics?: {
        profit_factor: number;
        win_rate: number;
        max_drawdown_pct: number;
        consecutive_losses_max: number;
        total_trades_executed: number;
    };
    action?: 'PROMOTE' | 'DEMOTE' | 'QUARANTINE' | 'MONITOR';
    trace_id?: string;
    tenant_id?: string;
    timestamp?: string;
    message?: string;
    has_exploratory_signals?: boolean;
    edge_demo_frozen?: boolean;
    exploration_state?: ExplorationState;
}

