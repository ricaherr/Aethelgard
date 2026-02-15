import React from 'react';
import { Loader2, RefreshCw, Layers, ShieldAlert } from 'lucide-react';
import HeatmapCell from './HeatmapCell';
import { useHeatmapData } from '../../hooks/useHeatmapData';

interface HeatmapData {
    symbols: string[];
    timeframes: string[];
    cells: any[];
    timestamp: string;
}

const HeatmapView: React.FC = () => {
    const { data, loading, error, refetch } = useHeatmapData();

    if (loading && !data) {
        return (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
                <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
                <span className="text-gray-400 animate-pulse font-medium">Analyzing multi-timeframe Confluences...</span>
            </div>
        );
    }

    if (error && !data) {
        return (
            <div className="flex flex-col items-center justify-center py-20 gap-4 bg-red-900/10 rounded-xl border border-red-900/20">
                <ShieldAlert className="w-10 h-10 text-red-500" />
                <span className="text-red-400 font-medium">Resilience Error: {error}</span>
                <button
                    onClick={() => { refetch(); }}
                    className="px-4 py-2 bg-red-900/40 hover:bg-red-900/60 text-red-200 rounded-lg transition-colors border border-red-500/30"
                >
                    Retry Connection
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Header Info */}
            <div className="flex justify-between items-center bg-gray-900/20 p-4 rounded-xl border border-gray-800/50 backdrop-blur-sm">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-500/10 rounded-lg">
                        <Layers className="w-5 h-5 text-blue-400" />
                    </div>
                    <div>
                        <h2 className="text-sm font-bold text-white uppercase tracking-wider">Fractal Confluence Heatmap</h2>
                        <p className="text-[10px] text-gray-500 mt-0.5">Real-time regime & signal matrix across {data?.symbols.length} assets</p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-gray-500 uppercase font-bold tracking-tighter">Last Update</span>
                        <span className="text-[10px] text-blue-400 font-mono">
                            {data ? new Date(data.timestamp).toLocaleTimeString() : '--:--:--'}
                        </span>
                    </div>
                    <button
                        onClick={() => { refetch(); }}
                        className="p-2 hover:bg-gray-800 rounded-lg transition-colors group"
                    >
                        <RefreshCw className={`w-4 h-4 text-gray-400 group-hover:text-white ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Matrix Container */}
            <div className="overflow-x-auto pb-4 custom-scrollbar">
                <div className="min-w-max">
                    {/* Timeframe Headers */}
                    <div className="grid grid-cols-[140px_repeat(auto-fill,minmax(140px,1fr))] gap-3 mb-3">
                        <div className="flex items-center px-4">
                            <span className="text-[10px] font-black text-gray-600 uppercase tracking-[0.2em]">Instrument</span>
                        </div>
                        {data?.timeframes.map((tf: string) => (
                            <div key={tf} className="flex justify-center">
                                <span className="text-[10px] font-black text-gray-600 uppercase tracking-[0.2em]">{tf}</span>
                            </div>
                        ))}
                    </div>

                    {/* Rows */}
                    <div className="space-y-3">
                        {data?.symbols.map((symbol: string) => (
                            <div key={symbol} className="grid grid-cols-[140px_repeat(auto-fill,minmax(140px,1fr))] gap-3 items-stretch">
                                {/* Symbol Label */}
                                <div className="flex flex-col justify-center px-4 bg-gray-900/40 rounded-xl border border-gray-800/50">
                                    <span className="text-sm font-bold text-white tracking-tight">{symbol}</span>
                                    {/* Detect if overall confluence exists for this row */}
                                    {data.cells.find((c: any) => c.symbol === symbol && c.confluence) && (
                                        <span className={`text-[9px] font-bold mt-1 uppercase ${data.cells.find((c: any) => c.symbol === symbol && c.confluence)?.confluence === 'BULLISH'
                                            ? 'text-emerald-500'
                                            : 'text-rose-500'
                                            }`}>
                                            Confluence {data.cells.find((c: any) => c.symbol === symbol && c.confluence)?.confluence_strength}x
                                        </span>
                                    )}
                                </div>

                                {/* Cells for each timeframe */}
                                {data.timeframes.map((tf: string) => {
                                    const cell = data.cells.find((c: any) => c.symbol === symbol && c.timeframe === tf);
                                    if (!cell) return <div key={tf} className="h-24 bg-gray-900/20 rounded-xl border border-dashed border-gray-800" />;

                                    return (
                                        <HeatmapCell
                                            key={tf}
                                            {...cell}
                                        />
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-4 pt-4 border-t border-gray-800/50">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-emerald-900/60 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Bull Trend</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-rose-900/60 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Bear Trend</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-blue-900/40 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Range</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-orange-900/60 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Volatile</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-red-950/80 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Shock/Crash</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-gray-800/60 rounded" />
                    <span className="text-[10px] text-gray-400 uppercase">Normal</span>
                </div>
            </div>
        </div>
    );
};

export default HeatmapView;
