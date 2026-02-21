import { useRef, useEffect } from 'react';
import { Terminal as TerminalIcon, Cpu, BrainCircuit, Activity, ShieldCheck, Zap, Box, Database, SignalHigh } from 'lucide-react';
import { CerebroThought } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '../../utils/cn';

interface CerebroConsoleProps {
    thoughts: CerebroThought[];
    status?: any;
    onExpand?: () => void;
}

const MODULE_ICONS: Record<string, any> = {
    'CORE': Activity,
    'SCANNER': SignalHigh,
    'ALPHA': Zap,
    'EXEC': Box,
    'DB': Database,
    'HEALTH': ShieldCheck,
    'INFRA': TerminalIcon,
    'MGMT': BrainCircuit
};

export function CerebroConsole({ thoughts, status, onExpand }: CerebroConsoleProps) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const cpuLoad = status?.cpu_load ?? 12;

    // Auto-scroll to bottom when new thoughts arrive
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [thoughts]);

    return (
        <GlassPanel className="h-[450px] flex flex-col border-aethelgard-green/10 bg-black/40">
            {/* Header Area */}
            <div className="flex items-center justify-between mb-4 px-2">
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <BrainCircuit size={18} className="text-aethelgard-green" />
                        <motion.div
                            animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                            transition={{ duration: 2, repeat: Infinity }}
                            className="absolute inset-0 bg-aethelgard-green rounded-full blur-md"
                        />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-[10px] font-outfit font-black tracking-[0.3em] text-white/90 uppercase italic">
                            Existential <span className="text-aethelgard-green">Flow</span>
                        </span>
                        <div className="flex items-center gap-1.5">
                            <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-green animate-pulse" />
                            <span className="text-[8px] font-mono text-aethelgard-green/60 uppercase">System_Active_v2</span>
                        </div>
                    </div>
                </div>
                <div className="flex gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-white/5" />
                    <div className="w-1.5 h-1.5 rounded-full bg-white/5" />
                    <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-green/40 shadow-[0_0_8px_rgba(0,255,65,0.4)]" />
                </div>
            </div>

            {/* Terminal Viewport */}
            <div className="flex-1 bg-black/60 rounded-xl overflow-hidden flex flex-col border border-white/5 shadow-inner">
                <div className="flex items-center justify-between px-4 py-2 bg-white/[0.02] border-b border-white/5">
                    <div className="flex items-center gap-2">
                        <TerminalIcon size={12} className="text-white/40" />
                        <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">Thought_Propagation.log</span>
                    </div>
                    <div className="flex gap-4">
                        <span className="text-[8px] font-mono text-white/20 uppercase tracking-tighter">Enc: L3-QUANTUM</span>
                    </div>
                </div>

                <div
                    ref={scrollRef}
                    className="flex-1 p-4 font-mono text-[10px] overflow-y-auto space-y-3 scrollbar-hide scroll-smooth"
                >
                    <AnimatePresence initial={false}>
                        {thoughts.length === 0 ? (
                            <div className="h-full flex flex-col items-center justify-center space-y-2 opacity-20">
                                <Activity size={24} className="animate-pulse" />
                                <p className="text-[10px] uppercase tracking-widest italic">Awaiting Cerebro Uplink...</p>
                            </div>
                        ) : (
                            thoughts.map((thought) => {
                                const Icon = MODULE_ICONS[thought.module] || TerminalIcon;
                                return (
                                    <motion.div
                                        key={thought.id}
                                        initial={{ opacity: 0, x: -5, scale: 0.98 }}
                                        animate={{ opacity: 1, x: 0, scale: 1 }}
                                        className="flex gap-3 group items-start"
                                    >
                                        <div className={cn(
                                            "mt-0.5 p-1 rounded-md border shrink-0 transition-all duration-500",
                                            thought.level === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-500' :
                                                thought.level === 'warning' ? 'bg-orange-500/10 border-orange-500/20 text-orange-400' :
                                                    thought.level === 'success' ? 'bg-aethelgard-green/10 border-aethelgard-green/20 text-aethelgard-green' :
                                                        'bg-white/5 border-white/10 text-white/40'
                                        )}>
                                            <Icon size={12} className={thought.level === 'error' ? 'animate-pulse' : ''} />
                                        </div>

                                        <div className="flex flex-col gap-0.5">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[8px] text-white/20 font-bold">
                                                    [{new Date(thought.timestamp).toLocaleTimeString([], { hour12: false })}]
                                                </span>
                                                <span className={cn(
                                                    "text-[9px] font-black uppercase tracking-widest",
                                                    thought.level === 'error' ? 'text-red-400' :
                                                        thought.level === 'warning' ? 'text-orange-400' :
                                                            thought.level === 'success' ? 'text-aethelgard-green' :
                                                                'text-white/40'
                                                )}>
                                                    {thought.module}
                                                </span>
                                            </div>
                                            <span className="text-white/70 leading-relaxed text-[10.5px] group-hover:text-white transition-colors">
                                                {thought.message}
                                            </span>
                                        </div>
                                    </motion.div>
                                );
                            })
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Footer Metrics & Actions */}
            <div className="mt-4 flex items-center justify-between px-2 pt-2 border-t border-white/5">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <Cpu size={14} className="text-white/30" />
                        <div className="flex flex-col">
                            <span className="text-[8px] text-white/20 uppercase font-black tracking-tighter">NPU Utilization</span>
                            <span className="text-[10px] text-white/60 font-mono font-bold leading-none">{cpuLoad.toFixed(1)}%</span>
                        </div>
                    </div>
                    <div className="w-24 h-1.5 bg-white/5 rounded-full overflow-hidden border border-white/5">
                        <motion.div
                            animate={{
                                width: `${Math.min(100, cpuLoad)}%`,
                                backgroundColor: cpuLoad > 80 ? 'rgba(239, 68, 68, 0.4)' : cpuLoad > 50 ? 'rgba(251, 146, 60, 0.4)' : 'rgba(0, 255, 65, 0.4)'
                            }}
                            transition={{ type: "spring", stiffness: 100 }}
                            className="h-full"
                        />
                    </div>
                </div>

                {onExpand && (
                    <button
                        onClick={onExpand}
                        className="group flex items-center gap-2 px-3 py-1.5 rounded-lg bg-aethelgard-green/5 border border-aethelgard-green/20 hover:bg-aethelgard-green/10 transition-all duration-300"
                    >
                        <span className="text-[9px] text-aethelgard-green/80 uppercase font-black tracking-[0.2em]">Verify Integrity</span>
                        <Activity size={10} className="text-aethelgard-green group-hover:scale-125 transition-transform" />
                    </button>
                )}
            </div>
        </GlassPanel>
    );
}
