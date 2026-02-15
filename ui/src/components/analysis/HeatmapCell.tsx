import React from 'react';
import { TrendingUp, TrendingDown, AlertCircle, Zap, Activity } from 'lucide-react';

interface HeatmapCellProps {
    symbol: string;
    timeframe: string;
    regime: string;
    metrics: any;
    signal?: {
        id: string;
        type: string;
        score: number;
    } | null;
    confluence?: 'BULLISH' | 'BEARISH' | null;
    isStale?: boolean;
    onClick?: () => void;
}

const HeatmapCell: React.FC<HeatmapCellProps> = ({
    symbol,
    timeframe,
    regime,
    metrics,
    signal,
    confluence,
    isStale,
    // onClick remains as prop for compatibility but is un-hooked from UI for now
}) => {
    // Determine background color based on regime
    const getRegimeColor = () => {
        if (isStale) return 'bg-gray-800/50 grayscale';

        switch (regime?.toUpperCase()) {
            case 'TREND':
                return metrics?.bias === 'BULLISH' ? 'bg-emerald-900/60' : 'bg-rose-900/60';
            case 'BULL':
                return 'bg-emerald-900/40';
            case 'BEAR':
                return 'bg-rose-900/40';
            case 'VOLATILE':
                return 'bg-orange-900/60';
            case 'SHOCK':
            case 'CRASH':
                return 'bg-red-950/80';
            case 'RANGE':
                return 'bg-blue-900/40';
            case 'NORMAL':
                return 'bg-gray-800/60';
            default:
                return 'bg-gray-800/40';
        }
    };

    // Confluence border
    const getConfluenceStyle = () => {
        if (!confluence) return 'border-gray-700/50';
        return confluence === 'BULLISH'
            ? 'border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.2)]'
            : 'border-rose-500/50 shadow-[0_0_10px_rgba(244,63,94,0.2)]';
    };

    return (
        <div
            className={`
                relative group p-3 rounded-lg border transition-all duration-300
                ${getRegimeColor()}
                ${getConfluenceStyle()}
            `}
        >
            {/* Header: Symbol & TF */}
            <div className="flex justify-between items-start mb-2">
                <span className="text-[10px] font-bold text-gray-400 tracking-wider uppercase">{timeframe}</span>
                {signal && (
                    <div className={`p-1 rounded-full ${signal.type === 'BUY' ? 'bg-emerald-500' : 'bg-rose-500'} animate-pulse shadow-lg`}>
                        {signal.type === 'BUY' ? <TrendingUp size={10} className="text-white" /> : <TrendingDown size={10} className="text-white" />}
                    </div>
                )}
            </div>

            {/* Content: Regime & Info */}
            <div className="flex flex-col gap-1">
                <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-white/90 truncate">
                        {regime}
                    </span>
                </div>

                {/* Metrics strip */}
                <div className="flex items-center gap-2 mt-1">
                    {metrics?.adx > 0 && (
                        <div className="flex items-center gap-0.5" title={`ADX: ${metrics.adx.toFixed(1)}`}>
                            <Zap size={10} className={metrics.adx > 25 ? "text-yellow-400" : "text-gray-500"} />
                            <span className="text-[9px] text-gray-400">{Math.round(metrics.adx)}</span>
                        </div>
                    )}
                    {metrics?.volatility > 0 && (
                        <div className="flex items-center gap-0.5" title={`Vol: ${metrics.volatility.toFixed(4)}`}>
                            <Activity size={10} className="text-blue-400" />
                            <span className="text-[9px] text-gray-400">{metrics.volatility.toFixed(1)}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Stale/Resilience indicator */}
            {isStale && (
                <div className="absolute top-1 right-1" title="Stale Data - Resilience Mode">
                    <AlertCircle size={10} className="text-orange-500" />
                </div>
            )}

            {/* Confluence hint */}
            {confluence && (
                <div className={`absolute bottom-1 right-1 w-1.5 h-1.5 rounded-full ${confluence === 'BULLISH' ? 'bg-emerald-400' : 'bg-rose-400'}`} />
            )}
        </div>
    );
};

export default HeatmapCell;
