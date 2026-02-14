import React, { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp } from 'lucide-react';
import { SignalCard } from './SignalCard';

interface Signal {
    id: string;
    symbol: string;
    direction: 'BUY' | 'SELL';
    score: number;
    timeframe: string;
    strategy: string;
    entry_price: number;
    sl: number;
    tp: number;
    r_r: number;
    regime: string;
    timestamp: string;
    status: string;
    has_trace: boolean;
    confluences?: string[];
}

interface SignalFeedProps {
    filters: any;
    onExecuteSignal?: (signalId: string) => void;
    onViewChart?: (symbol: string) => void;
    onViewTrace?: (signalId: string) => void;
}

export const SignalFeed: React.FC<SignalFeedProps> = ({
    filters,
    onExecuteSignal,
    onViewChart,
    onViewTrace
}) => {
    const [signals, setSignals] = useState<Signal[]>([]);
    const [loading, setLoading] = useState(true);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

    useEffect(() => {
        fetchSignals();

        if (autoRefresh) {
            const interval = setInterval(() => {
                fetchSignals();
            }, 30000);

            return () => clearInterval(interval);
        }
    }, [autoRefresh, filters]);

    const fetchSignals = async () => {
        try {
            setLoading(true);
            console.log('[SignalFeed] Fetching with filters:', JSON.stringify(filters));

            // Construir query params - BACKEND hace el filtrado
            const params = new URLSearchParams();
            params.append('limit', '100');

            // Time filter -> minutes param
            let minutes = 43200; // Default: 30 días
            if (filters.time && Array.isArray(filters.time) && filters.time.length > 0) {
                if (filters.time.includes('15min')) minutes = 15;
                else if (filters.time.includes('today')) minutes = 1440;
                else if (filters.time.includes('week')) minutes = 10080;
                console.log(`[SignalFeed] Time filter active: ${filters.time}, using minutes: ${minutes}`);
            }
            params.append('minutes', minutes.toString());

            // Symbols filter -> symbols param (comma-separated)
            if (filters.symbols && Array.isArray(filters.symbols) && filters.symbols.length > 0) {
                const symbolString = filters.symbols.join(',');
                params.append('symbols', symbolString);
                console.log(`[SignalFeed] Symbols filter active: ${symbolString}`);
            }

            // Timeframes filter -> timeframes param
            if (filters.timeframes && Array.isArray(filters.timeframes) && filters.timeframes.length > 0) {
                const tfString = filters.timeframes.join(',');
                params.append('timeframes', tfString);
                console.log(`[SignalFeed] Timeframes filter active: ${tfString}`);
            }

            // Regime filter -> regimes param
            if (filters.regime && Array.isArray(filters.regime) && filters.regime.length > 0) {
                const regimeString = filters.regime.join(',');
                params.append('regimes', regimeString);
                console.log(`[SignalFeed] Regime filter active: ${regimeString}`);
            }

            // Strategy filter -> strategies param
            if (filters.strategy && Array.isArray(filters.strategy) && filters.strategy.length > 0) {
                const strategyString = filters.strategy.join(',');
                params.append('strategies', strategyString);
                console.log(`[SignalFeed] Strategy filter active: ${strategyString}`);
            }

            // Status filter -> status param
            if (filters.status && Array.isArray(filters.status) && filters.status.length > 0) {
                const statusString = filters.status.join(',');
                params.append('status', statusString);
                console.log(`[SignalFeed] Status filter active: ${statusString}`);
            }

            const url = `/api/signals?${params.toString()}`;
            console.log('[SignalFeed] Final Request URL:', url);

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('[SignalFeed] API Response data:', data);

            // BACKEND ya filtró, solo aplicar filtro de probabilidad en cliente
            let filtered = data.signals || [];

            // Probability filter (solo en cliente porque es cálculo sobre score)
            if (filters.probability && Array.isArray(filters.probability) && filters.probability.length > 0) {
                filtered = filtered.filter((s: Signal) => {
                    const score = s.score * 100;
                    return filters.probability.some((range: string) => {
                        if (range === '90+') return score >= 90;
                        if (range === '80-90') return score >= 80 && score < 90;
                        if (range === '70-80') return score >= 70 && score < 80;
                        return false;
                    });
                });
            }

            filtered.sort((a: Signal, b: Signal) => b.score - a.score);

            console.log('Final signals:', filtered.length);

            setSignals(filtered);
            setLastUpdate(new Date());
        } catch (error) {
            console.error('Error fetching signals:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleRefresh = () => {
        fetchSignals();
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-blue-400" />
                    <h2 className="text-xl font-bold text-white">Signal Feed</h2>
                    <span className="px-2 py-1 bg-gray-700 text-gray-300 text-sm rounded">
                        {signals.length} signals
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">Auto-refresh</span>
                        <button
                            onClick={() => setAutoRefresh(!autoRefresh)}
                            className={`relative w-12 h-6 rounded-full transition-colors ${autoRefresh ? 'bg-blue-600' : 'bg-gray-600'
                                }`}
                        >
                            <div
                                className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${autoRefresh ? 'translate-x-6' : 'translate-x-0'
                                    }`}
                            />
                        </button>
                    </div>
                    <button
                        onClick={handleRefresh}
                        disabled={loading}
                        className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        <span className="text-sm">Refresh</span>
                    </button>
                </div>
            </div>

            <div className="text-xs text-gray-500">
                Last update: {lastUpdate.toLocaleTimeString('en-US')}
            </div>

            {loading && signals.length === 0 ? (
                <div className="flex items-center justify-center p-12">
                    <div className="text-gray-400">Loading signals...</div>
                </div>
            ) : signals.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 bg-gray-800 rounded-lg border border-gray-700">
                    <TrendingUp className="w-12 h-12 text-gray-600 mb-3" />
                    <p className="text-gray-400 text-center">
                        No signals match the selected filters
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        Try adjusting your filters or check if the scanner is running
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {signals.map((signal) => (
                        <SignalCard
                            key={signal.id}
                            signal={signal}
                            onExecute={onExecuteSignal}
                            onViewChart={onViewChart}
                            onViewTrace={onViewTrace}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};
