import { ChevronRight, ArrowUpRight, ArrowDownRight, Info } from 'lucide-react';
import { Signal } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';

interface AlphaSignalsProps {
    signals: Signal[];
}

export function AlphaSignals({ signals }: AlphaSignalsProps) {
    return (
        <GlassPanel className="flex-1 flex flex-col border-white/5">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-white/90 font-outfit font-bold tracking-tight text-lg">Opportunity Stream</h3>
                    <p className="text-white/30 text-[10px] uppercase tracking-[0.2em] mt-1">Real-time Alpha Generation</p>
                </div>
                <div className="flex gap-3">
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-white/5 border border-white/10">
                        <span className="text-[10px] font-bold text-white/40 uppercase">Filter:</span>
                        <span className="text-[10px] font-bold text-aethelgard-green uppercase">All Symbols</span>
                    </div>
                    <button className="px-3 py-1 rounded bg-aethelgard-gold/10 text-aethelgard-gold border border-aethelgard-gold/20 text-[10px] font-bold uppercase tracking-widest hover:bg-aethelgard-gold/20 transition-colors">
                        Auto-Execution: ON
                    </button>
                </div>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto scrollbar-hide pr-1">
                <AnimatePresence initial={false}>
                    {signals.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                            <Info size={48} className="mb-4" />
                            <p className="text-sm font-outfit uppercase tracking-widest">Scanning Markets for Alpha...</p>
                        </div>
                    ) : (
                        signals.map((signal) => (
                            <SignalItem key={signal.id} signal={signal} />
                        ))
                    )}
                </AnimatePresence>
            </div>
        </GlassPanel>
    );
}

function SignalItem({ signal }: { signal: Signal }) {
    const isBuy = signal.side === 'BUY';

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            whileHover={{ scale: 1.005, backgroundColor: 'rgba(255,255,255,0.03)' }}
            className="p-4 rounded-xl border border-white/5 bg-white/[0.01] flex items-center justify-between transition-all group"
        >
            <div className="flex items-center gap-10">
                <div className="w-24">
                    <div className="text-[9px] text-white/20 uppercase font-bold tracking-widest mb-1">Symbol</div>
                    <div className="text-base font-outfit font-bold text-white/90 tracking-tight">{signal.symbol}</div>
                </div>

                <div className="w-16">
                    <div className="text-[9px] text-white/20 uppercase font-bold tracking-widest mb-1">Side</div>
                    <div className={`flex items-center gap-1 text-sm font-bold ${isBuy ? 'text-aethelgard-green' : 'text-red-400'}`}>
                        {isBuy ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                        {signal.side}
                    </div>
                </div>

                <div className="w-24">
                    <div className="text-[9px] text-white/20 uppercase font-bold tracking-widest mb-1">Entry Price</div>
                    <div className="text-sm font-mono font-bold text-white/70">{signal.price.toLocaleString()}</div>
                </div>

                <div className="w-20 hidden md:block">
                    <div className="text-[9px] text-white/20 uppercase font-bold tracking-widest mb-1">Confidence</div>
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-aethelgard-blue">{signal.score.toFixed(1)}</span>
                        <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                            <div className="h-full bg-aethelgard-blue" style={{ width: `${signal.score * 10}%` }} />
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-6">
                <div className="text-right">
                    <div className="text-[9px] text-white/20 uppercase font-bold tracking-widest mb-1">Status</div>
                    <div className={`text-[10px] font-bold px-2 py-0.5 rounded ${signal.status === 'EXECUTED' ? 'bg-aethelgard-green/20 text-aethelgard-green' : 'bg-white/5 text-white/40'
                        }`}>
                        {signal.status}
                    </div>
                </div>
                <ChevronRight size={18} className="text-white/10 group-hover:text-aethelgard-green transition-colors" />
            </div>
        </motion.div>
    );
}
