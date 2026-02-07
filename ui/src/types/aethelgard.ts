export type MarketRegime = 'TREND' | 'RANGE' | 'CRASH' | 'NEUTRAL';

export interface Signal {
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    price: number;
    score: number;
    status: 'PENDING' | 'EXECUTED' | 'CANCELLED' | 'CLOSED';
    timestamp: string;
    magic_number: number;
}

export interface SystemStatus {
    connected: boolean;
    lastUpdate: string;
    heartbeats: Record<string, string>;
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
    level: 'info' | 'debug' | 'warning' | 'error';
    message: string;
    module: string;
}
