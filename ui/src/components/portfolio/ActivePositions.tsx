import { TrendingUp, TrendingDown, Info } from 'lucide-react';
import { PositionMetadata } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';

interface ActivePositionsProps {
    positions: PositionMetadata[];
}

export function ActivePositions({ positions }: ActivePositionsProps) {
    const totalProfit = positions.reduce((sum, p) => sum + p.profit_usd, 0);
    const totalRisk = positions.reduce((sum, p) => sum + p.initial_risk_usd, 0);
    const avgRMultiple = positions.length > 0
        ? positions.reduce((sum, p) => sum + p.r_multiple, 0) / positions.length
        : 0;

    return (
        <GlassPanel className="h-full flex flex-col border-white/5">
            {/* Header with Stats */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-white/90 font-outfit font-bold tracking-tight text-lg">Active Positions</h3>
                    <p className="text-white/50 text-[10px] uppercase tracking-[0.2em] mt-1">
                        {positions.length} Open · Avg {avgRMultiple.toFixed(2)}R
                    </p>
                </div>
                <div className="flex gap-4">
                    <div className="text-right">
                        <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest">Total P/L</div>
                        <div className={`text-lg font-mono font-bold ${totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest">Total Risk</div>
                        <div className="text-lg font-mono font-bold text-orange-400">
                            ${totalRisk.toFixed(2)}
                        </div>
                    </div>
                </div>
            </div>

            {/* Positions List */}
            <div className="flex-1 space-y-3 overflow-y-auto scrollbar-hide pr-1">
                <AnimatePresence initial={false}>
                    {positions.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                            <Info size={48} className="mb-4" />
                            <p className="text-sm font-outfit uppercase tracking-widest">No Active Positions</p>
                        </div>
                    ) : (
                        positions.map((position) => (
                            <PositionCard key={position.ticket} position={position} />
                        ))
                    )}
                </AnimatePresence>
            </div>
        </GlassPanel>
    );
}

function PositionCard({ position }: { position: PositionMetadata }) {
    const isProfit = position.profit_usd >= 0;
    const rColor =
        position.r_multiple >= 1 ? 'text-green-400' :
        position.r_multiple >= 0 ? 'text-yellow-400' :
        'text-red-400';

    const assetBadge = {
        forex: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
        metal: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
        crypto: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
        index: 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            whileHover={{ scale: 1.005, backgroundColor: 'rgba(255,255,255,0.03)' }}
            className="p-4 rounded-xl border border-white/5 bg-white/[0.01] transition-all group"
        >
            {/* Header: Symbol + Asset Badge + R-Multiple */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                    <span className="text-base font-outfit font-bold text-white/90">{position.symbol}</span>
                    <span className={`text-[9px] px-2 py-0.5 rounded uppercase font-bold border ${assetBadge[position.asset_type]}`}>
                        {position.asset_type}
                    </span>
                </div>

                <div className="flex items-center gap-3">
                    <div className="text-right">
                        <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest">R-Multiple</div>
                        <div className={`text-lg font-bold ${rColor}`}>
                            {position.r_multiple >= 0 ? '+' : ''}{position.r_multiple.toFixed(2)}R
                        </div>
                    </div>
                    {isProfit ? <TrendingUp size={18} className="text-green-400" /> : <TrendingDown size={18} className="text-red-400" />}
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-4 gap-3 text-xs">
                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Entry</div>
                    <div className="font-mono text-white/70">{position.entry_price.toLocaleString()}</div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Profit</div>
                    <div className={`font-mono font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                        {isProfit ? '+' : ''}${position.profit_usd.toFixed(2)}
                    </div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Risk</div>
                    <div className="font-mono font-bold text-orange-400">
                        ${position.initial_risk_usd.toFixed(2)}
                    </div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Volume</div>
                    <div className="font-mono text-white/70">
                        {position.volume.toFixed(2)}
                    </div>
                </div>
            </div>

            {/* Footer: SL/TP + Regime */}
            <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between text-[10px]">
                <div className="flex gap-4">
                    <span className="text-white/40">
                        SL: <span className="text-red-400 font-mono">{position.sl.toLocaleString()}</span>
                    </span>
                    <span className="text-white/40">
                        TP: <span className="text-green-400 font-mono">{position.tp.toLocaleString()}</span>
                    </span>
                </div>
                <div className="text-white/40">
                    Regime: <span className="text-aethelgard-blue font-bold">{position.entry_regime}</span>
                </div>
            </div>
        </motion.div>
    );
}
