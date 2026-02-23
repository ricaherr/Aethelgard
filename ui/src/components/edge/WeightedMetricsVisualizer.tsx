import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { MarketRegime } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { AlertCircle, TrendingUp } from 'lucide-react';

interface RegimeWeights {
    [regime: string]: {
        [metric: string]: number;
    };
}

interface WeightedMetricsVisualizerProps {
    currentRegime?: MarketRegime;
    height?: number;
}

export function WeightedMetricsVisualizer({
    currentRegime = 'TREND',
    height = 300
}: WeightedMetricsVisualizerProps) {
    const [weights, setWeights] = useState<RegimeWeights | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchRegimeConfigs();
    }, []);

    const fetchRegimeConfigs = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/regime_configs');
            if (!response.ok) throw new Error('Failed to fetch regime configs');

            const data = await response.json();
            const regimeWeights = data.regime_weights;
            setWeights(regimeWeights);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <GlassPanel className="p-6 w-full flex flex-col items-center justify-center" style={{ height }}>
                <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="w-6 h-6 border border-aethelgard-green/50 border-t-aethelgard-green rounded-full"
                />
                <p className="text-xs text-white/60 mt-3 uppercase tracking-wider">Loading regime weights...</p>
            </GlassPanel>
        );
    }

    if (error) {
        return (
            <GlassPanel className="p-6 w-full flex flex-col gap-3 border-red-500/20">
                <div className="flex items-center gap-2">
                    <AlertCircle size={18} className="text-red-400" />
                    <p className="text-xs font-bold text-red-400 uppercase tracking-wider">Error Loading Metrics</p>
                </div>
                <p className="text-[10px] text-white/50">{error}</p>
                <button
                    onClick={fetchRegimeConfigs}
                    className="text-[10px] px-2 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition-colors"
                >
                    Retry
                </button>
            </GlassPanel>
        );
    }

    const regimeColors: Record<string, string> = {
        TREND: 'from-aethelgard-green/40 to-aethelgard-green/20',
        RANGE: 'from-yellow-500/40 to-yellow-500/20',
        VOLATILE: 'from-orange-500/40 to-orange-500/20',
        SHOCK: 'from-red-500/40 to-red-500/20',
        BULL: 'from-green-500/40 to-green-500/20',
        BEAR: 'from-red-500/40 to-red-500/20',
        CRASH: 'from-red-700/40 to-red-700/20',
        NORMAL: 'from-white/10 to-white/5'
    };

    const regimeBorderColors: Record<string, string> = {
        TREND: 'border-aethelgard-green/40',
        RANGE: 'border-yellow-500/40',
        VOLATILE: 'border-orange-500/40',
        SHOCK: 'border-red-500/40',
        BULL: 'border-green-500/40',
        BEAR: 'border-red-500/40',
        CRASH: 'border-red-700/40',
        NORMAL: 'border-white/20'
    };

    const regimeTextColors: Record<string, string> = {
        TREND: 'text-aethelgard-green',
        RANGE: 'text-yellow-400',
        VOLATILE: 'text-orange-400',
        SHOCK: 'text-red-400',
        BULL: 'text-green-400',
        BEAR: 'text-red-400',
        CRASH: 'text-red-600',
        NORMAL: 'text-white/60'
    };

    return (
        <GlassPanel className="p-6 flex flex-col gap-6 border-aethelgard-green/10 h-full">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-sm font-bold text-white/90 uppercase tracking-widest mb-1">
                        <TrendingUp size={16} className="inline-block mr-2 text-aethelgard-green" />
                        Weighted Metrics by Regime
                    </h3>
                    <p className="text-[10px] text-white/50">Dynamic strategic allocation (Darwinismo Algorítmico)</p>
                </div>
            </div>

            {/* CSS-based Visualization: Horizontal Stacked Bars */}
            {weights ? (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                    className="flex-1 flex flex-col gap-6"
                >
                    {/* Stacked Bar Chart Visualization */}
                    <div className="space-y-4">
                        {Object.entries(weights).map(([regime, metrics]) => (
                            <motion.div
                                key={regime}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="flex flex-col gap-2"
                            >
                                <div className="flex items-center justify-between">
                                    <span className={`text-xs font-bold uppercase tracking-wider ${regimeTextColors[regime] || 'text-white/60'}`}>
                                        {regime}
                                    </span>
                                    <span className="text-[10px] text-white/40">Distribution</span>
                                </div>

                                {/* Stacked Bar */}
                                <div className="flex w-full h-8 rounded-lg overflow-hidden border border-white/10 bg-white/5">
                                    {Object.entries(metrics).map(([metric, weight], idx) => {
                                        const colors = [
                                            'bg-aethelgard-green/70',
                                            'bg-blue-500/70',
                                            'bg-purple-500/70',
                                            'bg-orange-500/70'
                                        ];
                                        return (
                                            <motion.div
                                                key={metric}
                                                initial={{ width: 0 }}
                                                animate={{ width: `${(weight as number) * 100}%` }}
                                                transition={{ duration: 0.6, delay: idx * 0.1 }}
                                                className={colors[idx % colors.length]}
                                                title={`${metric}: ${(((weight as number) || 0) * 100).toFixed(1)}%`}
                                            />
                                        );
                                    })}
                                </div>

                                {/* Metrics Labels */}
                                <div className="flex flex-wrap gap-2">
                                    {Object.entries(metrics).map(([metric, weight]) => (
                                        <span
                                            key={metric}
                                            className="text-[9px] px-2 py-1 rounded-full bg-white/5 border border-white/10 text-white/70"
                                        >
                                            {metric.replace(/_/g, ' ')}: <span className="font-bold text-aethelgard-green">{(((weight as number) || 0) * 100).toFixed(1)}%</span>
                                        </span>
                                    ))}
                                </div>
                            </motion.div>
                        ))}
                    </div>

                    {/* Current Regime Indicator */}
                    {weights && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className={`mt-4 p-3 rounded-lg bg-white/5 border ${regimeBorderColors[currentRegime]}`}
                        >
                            <p className="text-[10px] font-bold text-white/70 uppercase tracking-wider mb-2">
                                Current Regime: <span className={regimeTextColors[currentRegime] || 'text-white/60'}>{currentRegime}</span>
                            </p>
                            <div className="flex flex-wrap gap-2">
                                {Object.entries(weights[currentRegime] || {}).map(([metric, weight]) => (
                                    <motion.span
                                        key={metric}
                                        initial={{ opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        className="text-[9px] px-2 py-1 rounded-full bg-white/5 border border-white/10 text-white/70"
                                    >
                                        {metric.replace(/_/g, ' ')}: <span className="font-bold text-aethelgard-green">{(((weight as number) || 0) * 100).toFixed(1)}%</span>
                                    </motion.span>
                                ))}
                            </div>
                        </motion.div>
                    )}
                </motion.div>
            ) : (
                <div className="flex items-center justify-center py-8">
                    <p className="text-xs text-white/40 uppercase tracking-wider">No metrics available</p>
                </div>
            )}
        </GlassPanel>
    );
}
