import React from 'react';
import { Target, TrendingUp, TrendingDown, ChevronRight } from 'lucide-react';
import { HeatmapData } from '../../hooks/useHeatmapData';

interface TopOpportunitiesProps {
    data: HeatmapData | null;
    loading: boolean;
    onViewChart: (signal: any) => void;
}

const TopOpportunities: React.FC<TopOpportunitiesProps> = ({ data, loading, onViewChart }) => {
    if (loading && !data) return null;
    if (!data || !data.cells.length) return null;

    // Filter and sort opportunities by confluence strength
    // We only want a few top ones
    const opportunities = data.cells
        .filter(c => c.confluence)
        .sort((a, b) => (b.confluence_strength || 0) - (a.confluence_strength || 0))
        .slice(0, 3); // Top 3

    if (opportunities.length === 0) return null;

    return (
        <div className="animate-in fade-in slide-in-from-right-4 duration-700 bg-gray-900/40 backdrop-blur-md border border-gray-800/50 p-2 px-4 rounded-xl flex items-center gap-4">
            <div className="flex items-center gap-2 pr-4 border-r border-gray-800/50">
                <Target className="w-3.5 h-3.5 text-emerald-500" />
                <h3 className="text-[9px] font-black text-gray-500 uppercase tracking-widest leading-none">Alpha</h3>
            </div>

            <div className="flex items-center gap-3">
                {opportunities.map((opp, idx) => {
                    const isBullish = opp.confluence === 'BULLISH';
                    return (
                        <div
                            key={`${opp.symbol}-${idx}`}
                            onClick={() => onViewChart({ symbol: opp.symbol })}
                            className="flex items-center gap-2 bg-gray-800/40 hover:bg-gray-800/80 border border-gray-700/50 hover:border-blue-500/30 p-1.5 px-3 rounded-lg cursor-pointer transition-all group"
                        >
                            <div className={`p-1 rounded ${isBullish ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
                                {isBullish ? <TrendingUp className="w-3 h-3 text-emerald-400" /> : <TrendingDown className="w-3 h-3 text-rose-400" />}
                            </div>
                            <div className="flex flex-col">
                                <span className="text-[11px] font-bold text-white leading-none">{opp.symbol}</span>
                                <div className="flex items-center gap-1 mt-0.5">
                                    <span className={`text-[8px] font-bold uppercase tracking-tighter ${isBullish ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {opp.confluence?.slice(0, 4)}
                                    </span>
                                    <span className="text-[8px] text-gray-500 font-mono">{opp.confluence_strength}x</span>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default TopOpportunities;
