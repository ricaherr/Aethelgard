import { ChevronRight, ArrowUpRight, ArrowDownRight, Info, Power, Settings, AlertCircle, CheckCircle2, PauseCircle } from 'lucide-react';
import { Signal } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';
import { useEffect, useState } from 'react';
import { cn } from '../../utils/cn';

interface AlphaSignalsProps {
    signals: Signal[];
}

export function AlphaSignals({ signals, modulesStatus }: AlphaSignalsProps & { modulesStatus?: any }) {
    const scannerEnabled = modulesStatus?.modules?.scanner ?? true;

    return (
        <GlassPanel className="flex-1 flex flex-col border-white/5">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-white/90 font-outfit font-bold tracking-tight text-lg">Opportunity Stream</h3>
                    <p className="text-white/50 text-[10px] uppercase tracking-[0.2em] mt-1">Real-time Alpha Generation (Darwinismo Algorítmico)</p>
                </div>
                <div className="flex gap-3">
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-white/5 border border-white/10">
                        <span className="text-[10px] font-bold text-white/60 uppercase">Filter:</span>
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
                        <EmptyState scannerEnabled={scannerEnabled} />
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

function EmptyState({ scannerEnabled }: { scannerEnabled: boolean }) {
    if (!scannerEnabled) {
        return (
            <div className="h-full flex flex-col items-center justify-center py-20">
                <Power size={48} className="mb-4 text-orange-400/50" />
                <p className="text-sm font-outfit font-bold text-orange-400/80 uppercase tracking-widest mb-2">
                    Scanner Disabled
                </p>
                <p className="text-xs text-white/40 text-center max-w-md mb-4">
                    Signal discovery module is currently disabled. No new opportunities will be generated until enabled.
                </p>
                <div className="flex items-center gap-2 text-[10px] text-white/30">
                    <Settings size={14} />
                    <span>Go to Settings {'>'} System Modules to enable</span>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
            <Info size={48} className="mb-4" />
            <p className="text-sm font-outfit uppercase tracking-widest">Scanning Markets for Alpha...</p>
        </div>
    );
}

function SignalItem({ signal }: { signal: Signal }) {
    const isBuy = signal.side === 'BUY';
    const executionMode = signal.execution_mode || 'LIVE';
    const rankingScore = signal.ranking_score || signal.score * 20; // Fallback a score si no existe ranking_score

    // Mapeo de estilos para execution_mode
    const executionModeConfig = {
        'LIVE': {
            bgColor: 'bg-aethelgard-green/20',
            textColor: 'text-aethelgard-green',
            borderColor: 'border-aethelgard-green/30',
            icon: <CheckCircle2 size={12} />,
            label: 'LIVE'
        },
        'SHADOW': {
            bgColor: 'bg-yellow-500/20',
            textColor: 'text-yellow-400',
            borderColor: 'border-yellow-500/30',
            icon: <PauseCircle size={12} />,
            label: 'SHADOW'
        },
        'QUARANTINE': {
            bgColor: 'bg-red-600/20',
            textColor: 'text-red-400',
            borderColor: 'border-red-600/30',
            icon: <AlertCircle size={12} />,
            label: 'QUARANTINE'
        }
    };

    const modeConfig = executionModeConfig[executionMode as keyof typeof executionModeConfig] || executionModeConfig['LIVE'];

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            whileHover={{ scale: 1.005, backgroundColor: 'rgba(255,255,255,0.03)' }}
            className="p-4 rounded-xl border border-white/5 bg-white/[0.01] flex flex-col lg:flex-row items-start lg:items-center justify-between transition-all group gap-4 lg:gap-0"
        >
            {/* Left: Main Signal Info */}
            <div className="flex items-center gap-8 flex-1">
                <div className="w-24">
                    <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest mb-1">Symbol</div>
                    <div className="text-base font-outfit font-bold text-white/90 tracking-tight">{signal.symbol}</div>
                </div>

                <div className="w-16">
                    <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest mb-1">Side</div>
                    <div className={`flex items-center gap-1 text-sm font-bold ${isBuy ? 'text-aethelgard-green' : 'text-red-400'}`}>
                        {isBuy ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                        {signal.side}
                    </div>
                </div>

                <div className="w-24">
                    <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest mb-1">Entry Price</div>
                    <div className="text-sm font-mono font-bold text-white/70">{signal.price.toLocaleString()}</div>
                </div>

                <div className="w-20 hidden md:block">
                    <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest mb-1">Confidence</div>
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-aethelgard-blue">{signal.score.toFixed(1)}</span>
                        <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                            <div className="h-full bg-aethelgard-blue" style={{ width: `${Math.min(signal.score * 10, 100)}%` }} />
                        </div>
                    </div>
                </div>
            </div>

            {/* Right: Execution Mode + Ranking Score + Status */}
            <div className="flex items-center gap-4 lg:gap-6 flex-wrap lg:flex-nowrap justify-end w-full lg:w-auto">
                {/* Execution Mode Badge */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className={cn(
                        'flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[9px] font-bold uppercase tracking-widest',
                        modeConfig.bgColor,
                        modeConfig.textColor,
                        modeConfig.borderColor
                    )}
                    title={`Execution Mode: ${executionMode}`}
                >
                    {modeConfig.icon}
                    <span>{modeConfig.label}</span>
                </motion.div>

                {/* Ranking Score */}
                <motion.div
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="hidden sm:flex items-center gap-2 px-2 py-1 rounded-lg bg-white/5 border border-white/10"
                    title={`Ranking Score: Why this signal is ${executionMode}`}
                >
                    <span className="text-[9px] text-white/50 uppercase font-bold">Score:</span>
                    <motion.span
                        animate={{ scale: [1, 1.05, 1] }}
                        transition={{ duration: 2, repeat: Infinity }}
                        className="text-xs font-bold text-aethelgard-green"
                    >
                        {rankingScore.toFixed(0)}%
                    </motion.span>
                </motion.div>

                {/* Status */}
                <div className="text-right">
                    <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest mb-1">Status</div>
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
