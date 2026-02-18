import React from 'react';
import { TrendingUp, TrendingDown, Clock, Target, Shield, BarChart3, LineChart, ListTree, Play } from 'lucide-react';

interface SignalCardProps {
    signal: {
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
        live_status?: 'OPEN' | 'CLOSED';
        pnl?: number;
        has_chart?: boolean;
    };
    onExecute?: (signalId: string) => void;
    onViewChart?: (signal: any) => void;
    onViewTrace?: (signalId: string) => void;
}

export const SignalCard: React.FC<SignalCardProps> = ({
    signal,
    onExecute,
    onViewChart,
    onViewTrace
}) => {
    const getScoreColor = (score: number) => {
        if (score >= 0.90) return 'text-green-400 bg-green-900/30';
        if (score >= 0.80) return 'text-yellow-400 bg-yellow-900/30';
        return 'text-orange-400 bg-orange-900/30';
    };

    const getDirectionColor = (direction: string) => {
        return direction === 'BUY' ? 'text-green-400' : 'text-red-400';
    };

    const getDirectionIcon = (direction: string) => {
        return direction === 'BUY' ? (
            <TrendingUp className="w-5 h-5" />
        ) : (
            <TrendingDown className="w-5 h-5" />
        );
    };

    const timeAgo = (timestamp: string) => {
        const now = new Date().getTime();
        const then = new Date(timestamp).getTime();
        const diff = Math.floor((now - then) / 1000 / 60); // minutos

        if (diff < 1) return 'Ahora';
        if (diff < 60) return `${diff}min`;
        if (diff < 1440) return `${Math.floor(diff / 60)}h`;
        return `${Math.floor(diff / 1440)}d`;
    };

    return (
        <div className="bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 transition-all p-4">
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${signal.direction === 'BUY' ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                        <div className={getDirectionColor(signal.direction)}>
                            {getDirectionIcon(signal.direction)}
                        </div>
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="font-bold text-white text-lg">{signal.symbol}</h3>
                            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${getScoreColor(signal.score || 0)}`}>
                                {((signal.score || 0) * 100).toFixed(0)}%
                            </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-gray-400 mt-1">
                            <span>{signal.timeframe}</span>
                            <span>•</span>
                            <span>{signal.strategy}</span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {timeAgo(signal.timestamp)}
                            </span>
                        </div>
                    </div>
                </div>
                <div className={`px-3 py-1 rounded-lg text-xs font-semibold ${signal.regime === 'TREND' ? 'bg-purple-900/30 text-purple-400' :
                    signal.regime === 'RANGE' ? 'bg-blue-900/30 text-blue-400' :
                        'bg-orange-900/30 text-orange-400'
                    }`}>
                    {signal.regime}
                </div>
            </div>

            {/* Price Levels */}
            <div className="grid grid-cols-4 gap-3 mb-3">
                <div className="bg-gray-750 rounded-lg p-2">
                    <div className="text-xs text-gray-400 mb-1">Entry</div>
                    <div className="text-sm font-semibold text-white">{(signal.entry_price || 0).toFixed(5)}</div>
                </div>
                <div className="bg-gray-750 rounded-lg p-2">
                    <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                        <Shield className="w-3 h-3" />
                        SL
                    </div>
                    <div className="text-sm font-semibold text-red-400">{(signal.sl || 0).toFixed(5)}</div>
                </div>
                <div className="bg-gray-750 rounded-lg p-2">
                    <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                        <Target className="w-3 h-3" />
                        TP
                    </div>
                    <div className="text-sm font-semibold text-green-400">{(signal.tp || 0).toFixed(5)}</div>
                </div>
                <div className="bg-gray-750 rounded-lg p-2">
                    <div className="text-xs text-gray-400 mb-1">R:R</div>
                    <div className="text-sm font-semibold text-blue-400">1:{(signal.r_r || 0).toFixed(1)}</div>
                </div>
            </div>

            {/* Confluences */}
            {signal.confluences && signal.confluences.length > 0 && (
                <div className="mb-3">
                    <div className="text-xs text-gray-400 mb-2 flex items-center gap-1">
                        <BarChart3 className="w-3 h-3" />
                        Confluencias
                    </div>
                    <div className="flex flex-wrap gap-1">
                        {signal.confluences.map((conf, idx) => (
                            <span
                                key={idx}
                                className="px-2 py-1 bg-gray-750 text-xs text-gray-300 rounded"
                            >
                                {conf}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {/* Live Status Indicator (EdgeTuner Feedback) */}
            {signal.live_status && (
                <div className={`mb-3 p-2 rounded-lg flex justify-between items-center ${signal.live_status === 'OPEN'
                    ? 'bg-blue-900/20 border border-blue-500/30'
                    : 'bg-gray-700/50 border border-gray-600/30 opacity-80'
                    }`}>
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${signal.live_status === 'OPEN' ? 'bg-blue-400 animate-pulse' : 'bg-gray-500'}`} />
                        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-300">
                            {signal.live_status === 'OPEN' ? 'Operación en curso' : 'Trade Finalizado'}
                        </span>
                    </div>
                    {signal.pnl !== undefined && (
                        <span className={`text-sm font-mono font-bold ${signal.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {signal.pnl >= 0 ? '+' : ''}{signal.pnl.toFixed(2)}
                            <span className="text-[8px] ml-1 opacity-60">USD</span>
                        </span>
                    )}
                </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
                <button
                    onClick={() => onExecute?.(signal.id)}
                    disabled={signal.status.toUpperCase() !== 'PENDING'}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 font-medium rounded-lg transition-colors ${signal.status.toUpperCase() === 'PENDING'
                        ? 'bg-blue-600 hover:bg-blue-700 text-white'
                        : 'bg-gray-700 text-gray-500 cursor-not-allowed'
                        }`}
                >
                    <Play className="w-4 h-4" />
                    Execute
                </button>
                <button
                    onClick={() => onViewTrace?.(signal.id)}
                    disabled={!signal.has_trace}
                    className={`px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors ${signal.has_trace ? 'text-indigo-400' : 'text-gray-600 cursor-not-allowed opacity-50'
                        }`}
                    title={signal.has_trace ? "Trace" : "No trace data available"}
                >
                    <ListTree className="w-4 h-4" />
                </button>
                <button
                    onClick={() => onViewChart?.(signal)}
                    disabled={signal.has_chart === false}
                    className={`px-4 py-2 rounded-lg transition-colors ${signal.has_chart === false
                        ? 'bg-gray-700 text-gray-600 cursor-not-allowed opacity-50'
                        : 'bg-gray-700 hover:bg-gray-600 text-blue-400'
                        }`}
                    title={signal.has_chart === false ? "Gráfica no disponible para este símbolo" : "Ver Gráfica"}
                >
                    <LineChart className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
};
