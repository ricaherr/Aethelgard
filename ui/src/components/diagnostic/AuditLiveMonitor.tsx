import { motion, AnimatePresence } from 'framer-motion';
import { X, ShieldCheck, Zap, Loader2, CheckCircle2, AlertTriangle, Cpu, Database, Network, FileCode, Beaker } from 'lucide-react';
import { CerebroThought } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { useEffect, useState, useMemo } from 'react';
import { cn } from '../../utils/cn';

interface AuditLiveMonitorProps {
    isOpen: boolean;
    onClose: () => void;
    thoughts: CerebroThought[];
    runRepair: (stage: string) => Promise<boolean>;
}

interface AuditStage {
    id: string;
    label: string;
    icon: React.ReactNode;
    status: 'PENDING' | 'RUNNING' | 'OK' | 'FAIL';
    error?: string;
    repairing?: boolean;
}

const INITIAL_STAGES: AuditStage[] = [
    { id: 'Architecture', label: 'Architecture Topology', icon: <Cpu size={14} />, status: 'PENDING' },
    { id: 'QA Guard', label: 'QA Integrity Guard', icon: <ShieldCheck size={14} />, status: 'PENDING' },
    { id: 'Code Quality', label: 'Complexity Density', icon: <FileCode size={14} />, status: 'PENDING' },
    { id: 'UI Quality', label: 'React Ecosystem', icon: <Zap size={14} />, status: 'PENDING' },
    { id: 'Manifesto', label: 'Aethelgard Manifesto', icon: <FileCode size={14} />, status: 'PENDING' },
    { id: 'Patterns', label: 'Design Patterns', icon: <ShieldCheck size={14} />, status: 'PENDING' },
    { id: 'Core Tests', label: 'Core Consensus Tests', icon: <Beaker size={14} />, status: 'PENDING' },
    { id: 'Integration', label: 'Integration Bridges', icon: <Network size={14} />, status: 'PENDING' },
    { id: 'Connectivity', label: 'Broker Uplink', icon: <Network size={14} />, status: 'PENDING' },
    { id: 'System DB', label: 'Data Vault Integrity', icon: <Database size={14} />, status: 'PENDING' }
];

export function AuditLiveMonitor({ isOpen, onClose, thoughts, runRepair }: AuditLiveMonitorProps) {
    const [stages, setStages] = useState<AuditStage[]>(INITIAL_STAGES);
    const [isFinished, setIsFinished] = useState(false);
    const [isAuditSuccess, setIsAuditSuccess] = useState(true);
    const [autoCloseTimer, setAutoCloseTimer] = useState<number | null>(null);

    // Track audit progress from thoughts
    useEffect(() => {
        if (!isOpen) {
            setStages(INITIAL_STAGES);
            setIsFinished(false);
            setAutoCloseTimer(null);
            return;
        }

        const healthThoughts = thoughts.filter(t => t.module === 'HEALTH' && t.metadata?.stage);

        setStages(prev => prev.map(stage => {
            const stageThoughts = healthThoughts.filter(t => t.metadata?.stage === stage.id);
            if (stageThoughts.length === 0) return stage;

            const latest = stageThoughts[0]; // thoughts are unshifted, so index 0 is newest
            if (latest.metadata?.status === 'OK') return { ...stage, status: 'OK', error: undefined };
            if (latest.metadata?.status === 'FAIL') return { ...stage, status: 'FAIL', error: latest.metadata?.error };
            if (latest.metadata?.status === 'STARTING') return { ...stage, status: 'RUNNING' };
            return stage;
        }));

        // Check if finished via metadata
        const finishedThought = thoughts.find(t =>
            t.module === 'HEALTH' && t.metadata?.status === 'FINISHED'
        );

        if (finishedThought && !isFinished) {
            const isSuccess = !!finishedThought.metadata?.success;
            setIsFinished(true);
            setIsAuditSuccess(isSuccess);

            // Milestone 5.6: Auto-close in 20s if success, persistent if fail
            if (isSuccess) {
                setAutoCloseTimer(20);
            } else {
                setAutoCloseTimer(null);
            }
        }
    }, [thoughts, isOpen, isFinished]);

    // Auto-close countdown
    useEffect(() => {
        if (autoCloseTimer === null) return;
        if (autoCloseTimer <= 0) {
            onClose();
            return;
        }

        const interval = setInterval(() => {
            setAutoCloseTimer(prev => (prev !== null ? prev - 1 : null));
        }, 1000);

        return () => clearInterval(interval);
    }, [autoCloseTimer, onClose]);

    const progress = useMemo(() => {
        const completed = stages.filter(s => s.status === 'OK' || s.status === 'FAIL').length;
        return (completed / stages.length) * 100;
    }, [stages]);

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
                    />

                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                        className="fixed top-0 right-0 h-full w-full max-w-lg bg-aethelgard-deep-blue/95 border-l border-white/10 z-[60] shadow-2xl flex flex-col overflow-hidden"
                    >
                        {/* Header */}
                        <div className="p-8 border-b border-white/5 bg-gradient-to-r from-aethelgard-blue/5 to-transparent">
                            <div className="flex items-center justify-between mb-6">
                                <div className="flex items-center gap-4">
                                    <div className="p-3 bg-aethelgard-blue/10 rounded-2xl border border-aethelgard-blue/20">
                                        <ShieldCheck className="text-aethelgard-blue" size={24} />
                                    </div>
                                    <div>
                                        <h2 className="text-xl font-outfit font-bold text-white uppercase tracking-wider">Live Audit</h2>
                                        <p className="text-white/40 text-[10px] uppercase font-bold tracking-widest mt-1">High-Fidelity Integrity Scan</p>
                                    </div>
                                </div>
                                <button
                                    onClick={onClose}
                                    className="p-2 hover:bg-white/5 rounded-xl transition-colors text-white/40 hover:text-white"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            {/* Progress Bar */}
                            <div className="space-y-2">
                                <div className="flex justify-between items-end">
                                    <span className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em]">Execution Progress</span>
                                    <span className="text-lg font-outfit font-black text-white">{Math.round(progress)}%</span>
                                </div>
                                <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                                    <motion.div
                                        className="h-full bg-aethelgard-blue shadow-[0_0_10px_rgba(59,130,246,0.5)]"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Stage List */}
                        <div className="flex-1 overflow-y-auto p-8 space-y-4 custom-scrollbar">
                            {stages.map((stage) => (
                                <StageCard
                                    key={stage.id}
                                    stage={stage}
                                    onRepair={async () => {
                                        setStages(prev => prev.map(s => s.id === stage.id ? { ...s, repairing: true } : s));
                                        const success = await runRepair(stage.id);
                                        if (success) {
                                            setStages(prev => prev.map(s => s.id === stage.id ? { ...s, status: 'OK', repairing: false, error: undefined } : s));
                                        } else {
                                            setStages(prev => prev.map(s => s.id === stage.id ? { ...s, repairing: false } : s));
                                        }
                                    }}
                                />
                            ))}
                        </div>

                        {/* Footer */}
                        <div className="p-8 border-t border-white/5 bg-black/20">
                            {isFinished ? (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex flex-col gap-4"
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <div className={cn(
                                                "w-2 h-2 rounded-full",
                                                isAuditSuccess ? "bg-aethelgard-green animate-pulse" : "bg-red-500"
                                            )} />
                                            <span className={cn(
                                                "text-xs font-bold uppercase tracking-widest",
                                                isAuditSuccess ? "text-aethelgard-green" : "text-red-500"
                                            )}>
                                                {isAuditSuccess ? "Audit Completed" : "Integrity Compromised"}
                                            </span>
                                        </div>
                                        {autoCloseTimer !== null && (
                                            <span className="text-[10px] font-mono text-white/30">Auto-closing in {autoCloseTimer}s</span>
                                        )}
                                    </div>
                                    <button
                                        onClick={onClose}
                                        className={cn(
                                            "w-full py-4 rounded-xl text-xs font-black uppercase tracking-[0.3em] transition-all",
                                            isAuditSuccess
                                                ? "bg-aethelgard-blue/20 border border-aethelgard-blue/40 text-aethelgard-blue hover:bg-aethelgard-blue/30"
                                                : "bg-red-500/10 border border-red-500/40 text-red-500 hover:bg-red-500/20"
                                        )}
                                    >
                                        DIMISS MONITOR
                                    </button>
                                </motion.div>
                            ) : (
                                <div className="flex items-center gap-3 text-white/30 font-mono text-[10px] uppercase tracking-widest animate-pulse">
                                    <Loader2 className="animate-spin" size={12} />
                                    Synchronizing integrity vectors...
                                </div>
                            )}
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}

function StageCard({ stage, onRepair }: { stage: AuditStage, onRepair: () => void }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const isRunning = stage.status === 'RUNNING' || stage.repairing;
    const isOk = stage.status === 'OK';
    const isFail = stage.status === 'FAIL';
    const isPending = stage.status === 'PENDING';

    const handleRepair = async (e: React.MouseEvent) => {
        e.stopPropagation();
        onRepair();
    };

    return (
        <div className="space-y-2">
            <GlassPanel
                onClick={() => isFail && setIsExpanded(!isExpanded)}
                className={cn(
                    "p-4 border-white/5 flex items-center justify-between group transition-all duration-500",
                    isFail ? "cursor-pointer hover:border-red-500/30" : "",
                    isRunning ? "border-aethelgard-blue/30 bg-aethelgard-blue/5" : "",
                    isOk ? "border-aethelgard-green/10" : "",
                    isFail ? "border-red-500/20 bg-red-500/5 shadow-[0_0_15px_rgba(239,68,68,0.05)]" : ""
                )}
            >
                <div className="flex items-center gap-4">
                    <div className={cn(
                        "p-2 rounded-lg transition-colors",
                        isRunning ? "text-aethelgard-blue bg-aethelgard-blue/10" :
                            isOk ? "text-aethelgard-green bg-aethelgard-green/10" :
                                isFail ? "text-red-500 bg-red-500/10" : "text-white/20 bg-white/5"
                    )}>
                        {stage.icon}
                    </div>
                    <div>
                        <h4 className={cn(
                            "text-[11px] font-bold uppercase tracking-wider",
                            isPending ? "text-white/20" : "text-white/80"
                        )}>
                            {stage.label}
                        </h4>
                        <span className="text-[9px] font-mono text-white/30 truncate block max-w-[200px]">
                            V_{stage.id.toUpperCase().replace(/\s/g, '_')}
                        </span>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {isRunning ? (
                        <div className="flex items-center gap-2">
                            <span className="text-[9px] font-mono text-aethelgard-blue uppercase animate-pulse">Processing</span>
                            <Loader2 className="animate-spin text-aethelgard-blue" size={12} />
                        </div>
                    ) : isOk ? (
                        <div className="flex items-center gap-2">
                            <span className="text-[9px] font-mono text-aethelgard-green uppercase">Verified</span>
                            <CheckCircle2 className="text-aethelgard-green" size={14} />
                        </div>
                    ) : isFail ? (
                        <div className="flex items-center gap-2">
                            <span className="text-[9px] font-mono text-red-500 uppercase">Compromised</span>
                            <AlertTriangle className="text-red-500" size={14} />
                        </div>
                    ) : (
                        <span className="text-[9px] font-mono text-white/10 uppercase italic">Pending</span>
                    )}
                </div>
            </GlassPanel>

            <AnimatePresence>
                {isExpanded && isFail && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                    >
                        <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20 m-1 flex flex-col gap-3">
                            <div className="flex items-start gap-2">
                                <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={12} />
                                <p className="text-[10px] text-red-200/60 font-mono leading-relaxed">
                                    {stage.error || "Inconsistencia de integridad detectada. El vector no cumple con los protocolos de seguridad de Aethelgard."}
                                </p>
                            </div>

                            <button
                                disabled
                                className="flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-white/5 text-white/20 text-[9px] font-black uppercase tracking-widest cursor-not-allowed border border-white/10"
                            >
                                <Zap size={10} className="opacity-50" />
                                Protocol Pending (L3_REPAIR)
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
