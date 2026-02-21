import { motion, AnimatePresence } from 'framer-motion';
import { X, BrainCircuit, Activity, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react';
import { TuningLog } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';

const formatDate = (dateStr: string) => {
    try {
        const date = new Date(dateStr);
        return new Intl.DateTimeFormat('en-US', {
            month: 'short',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        }).format(date);
    } catch (e) {
        return dateStr;
    }
};

interface NeuralHistoryPanelProps {
    isOpen: boolean;
    onClose: () => void;
    logs: TuningLog[];
}

export function NeuralHistoryPanel({ isOpen, onClose, logs }: NeuralHistoryPanelProps) {
    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 px-4 py-8 md:p-8 flex justify-end"
                    />

                    {/* Panel */}
                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                        className="fixed top-0 right-0 h-full w-full max-w-xl bg-aethelgard-deep-blue/95 border-l border-white/10 z-[60] shadow-2xl flex flex-col overflow-hidden"
                    >
                        {/* Header */}
                        <div className="p-8 border-b border-white/5 flex items-center justify-between bg-gradient-to-r from-aethelgard-green/5 to-transparent">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-aethelgard-green/10 rounded-2xl border border-aethelgard-green/20">
                                    <BrainCircuit className="text-aethelgard-green" size={24} />
                                </div>
                                <div>
                                    <h2 className="text-xl font-outfit font-bold text-white uppercase tracking-wider">Neural History</h2>
                                    <p className="text-white/40 text-xs">Autonomous self-calibration and learning logs.</p>
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-2 hover:bg-white/5 rounded-xl transition-colors text-white/40 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                            {logs.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-white/20 gap-4 opacity-50">
                                    <Activity size={48} />
                                    <p className="font-bold uppercase tracking-[0.2em] text-sm">No neural events recorded yet.</p>
                                </div>
                            ) : (
                                <div className="space-y-8">
                                    {logs.map((log, idx) => (
                                        <NeuralEventCard key={log.id || idx} log={log} />
                                    ))}
                                </div>
                            )}
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}

function NeuralEventCard({ log }: { log: TuningLog }) {
    const isAggressive = log.adjustment_factor < 0.8;
    const isConservative = log.adjustment_factor > 1.2;

    return (
        <div className="relative pl-8 border-l border-white/5">
            {/* Timeline Dot */}
            <div className={`absolute left-[-5px] top-0 w-2.5 h-2.5 rounded-full shadow-[0_0_8px] ${isAggressive ? 'bg-orange-500 shadow-orange-500/40' :
                isConservative ? 'bg-aethelgard-green shadow-aethelgard-green/40' : 'bg-blue-500 shadow-blue-500/40'
                }`} />

            <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest leading-none">
                        {formatDate(log.timestamp)}
                    </span>
                    <div className={`px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider ${isAggressive ? 'bg-orange-500/10 text-orange-500 border border-orange-500/20' :
                        isConservative ? 'bg-aethelgard-green/10 text-aethelgard-green border border-aethelgard-green/20' :
                            'bg-blue-500/10 text-blue-500 border border-blue-500/20'
                        }`}>
                        {isAggressive ? 'Aggressive Shift' : isConservative ? 'Strategic Tightening' : 'Balance Adjust'}
                    </div>
                </div>

                <GlassPanel className="p-5 border-white/5 hover:border-white/10 transition-all group overflow-hidden">
                    <div className="flex flex-col gap-4">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <h4 className="text-sm font-bold text-white/90 mb-1 flex items-center gap-2">
                                    {log.trigger === 'consecutive_losses' && <AlertTriangle size={14} className="text-orange-500" />}
                                    {log.trigger === 'high_win_rate' && <TrendingUp size={14} className="text-aethelgard-green" />}
                                    {log.trigger.replace(/_/g, ' ').toUpperCase()}
                                </h4>
                                <p className="text-[11px] text-white/40">
                                    System detected anomaly in performance vectors. Initiating self-correction.
                                </p>
                            </div>
                            <div className="text-right">
                                <span className="text-xs font-mono text-white/60 block">Factor</span>
                                <span className="text-lg font-outfit font-black text-white">{log.adjustment_factor.toFixed(2)}x</span>
                            </div>
                        </div>

                        {/* Parameter Dels */}
                        <div className="grid grid-cols-2 gap-3 mt-2">
                            <ParamBlock label="ADX Threshold" oldV={log.old_params.adx_threshold} newV={log.new_params.adx_threshold} />
                            <ParamBlock label="Elephant Mult" oldV={log.old_params.elephant_atr_multiplier} newV={log.new_params.elephant_atr_multiplier} precision={2} />
                            <ParamBlock label="Min Score" oldV={log.old_params.min_signal_score} newV={log.new_params.min_signal_score} />
                            <ParamBlock label="Risk %" oldV={log.old_params.risk_per_trade * 100} newV={log.new_params.risk_per_trade * 100} precision={2} suffix="%" />
                        </div>

                        {/* Context Stats */}
                        <div className="flex items-center gap-6 pt-4 border-t border-white/5">
                            <div className="flex flex-col">
                                <span className="text-[9px] text-white/30 uppercase font-black">Success Rate</span>
                                <span className="text-xs font-mono text-white/80">{(log.stats.win_rate * 100).toFixed(1)}%</span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-[9px] text-white/30 uppercase font-black">Trade Count</span>
                                <span className="text-xs font-mono text-white/80">{log.stats.total_trades}</span>
                            </div>
                        </div>
                    </div>
                </GlassPanel>
            </div>
        </div>
    );
}

function ParamBlock({ label, oldV, newV, precision = 1, suffix = '' }: { label: string, oldV: number, newV: number, precision?: number, suffix?: string }) {
    const isIncrease = newV > oldV;
    const isDecrease = newV < oldV;

    return (
        <div className="p-2 rounded-lg bg-white/[0.02] border border-white/5 flex flex-col gap-1">
            <span className="text-[9px] text-white/40 font-bold uppercase">{label}</span>
            <div className="flex items-center gap-2">
                <span className="text-[10px] text-white/30 font-mono italic">{oldV.toFixed(precision)}{suffix}</span>
                <ChevronRight size={10} className="text-white/20" />
                <span className={`text-xs font-mono font-bold ${isIncrease ? 'text-aethelgard-green' : isDecrease ? 'text-orange-500' : 'text-white/80'
                    }`}>
                    {newV.toFixed(precision)}{suffix}
                </span>
            </div>
        </div>
    );
}
