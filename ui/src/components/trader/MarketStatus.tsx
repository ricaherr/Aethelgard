import { Zap } from 'lucide-react';
import { MarketRegime, EdgeMetrics } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion } from 'framer-motion';

interface MarketStatusProps {
    regime: MarketRegime;
    metrics: EdgeMetrics;
}

export function MarketStatus({ regime, metrics }: MarketStatusProps) {
    const getRegimeColor = (r: MarketRegime) => {
        switch (r) {
            case 'TREND': return 'text-aethelgard-green';
            case 'RANGE': return 'text-aethelgard-blue';
            case 'CRASH': return 'text-red-500';
            default: return 'text-white/60';
        }
    };

    return (
        <GlassPanel premium className="relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-10 transition-opacity duration-700">
                <Zap size={160} />
            </div>

            <h3 className="text-white/60 text-xs font-bold uppercase tracking-[0.2em] mb-4">Market Identity</h3>

            <div className="flex items-end gap-3 mb-8">
                <motion.span
                    key={regime}
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    className={`text-6xl font-outfit font-bold tracking-tighter ${getRegimeColor(regime)}`}
                >
                    {regime}
                </motion.span>
                <span className="text-white/50 text-sm mb-2 font-mono">CONF: {metrics.confidence}%</span>
            </div>

            <div className="space-y-4">
                <MetricItem label="System Bias" value={metrics.global_bias} />
                <MetricItem label="Volatility Index" value={metrics.volatility} />
                <MetricItem label="ADX Power" value={metrics.adx_strength.toString()} />
            </div>

            <div className="mt-8 pt-6 border-t border-white/5 flex items-center justify-between">
                <div className="flex -space-x-2">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="w-6 h-6 rounded-full border border-dark bg-aethelgard-green/20 flex items-center justify-center">
                            <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-green animate-pulse" />
                        </div>
                    ))}
                </div>
                <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest">Autonomous Consensus active</span>
            </div>
        </GlassPanel>
    );
}

function MetricItem({ label, value }: { label: string, value: string }) {
    return (
        <div className="flex justify-between items-center group/item">
            <span className="text-white/50 text-xs group-hover/item:text-white/80 transition-colors uppercase tracking-wider">{label}</span>
            <span className="text-white/90 font-mono font-bold text-sm tracking-widest">{value}</span>
        </div>
    );
}
