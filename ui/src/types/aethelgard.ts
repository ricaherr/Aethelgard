export type MarketRegime = 'TREND' | 'RANGE' | 'CRASH' | 'NEUTRAL';
export type AssetType = 'forex' | 'metal' | 'crypto' | 'index';

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
}

export interface TuningLog {
    id: number;
    timestamp: string;
    trigger: string;
    adjustment_factor: number;
    old_params: Record<string, number>;
    new_params: Record<string, number>;
    stats: {
        total_trades: number;
        win_rate: number;
        consecutive_losses: number;
        [key: string]: any;
    };
}

