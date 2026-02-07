import { Terminal as TerminalIcon, Cpu, BrainCircuit } from 'lucide-react';
import { CerebroThought } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';

interface CerebroConsoleProps {
    thoughts: CerebroThought[];
}

export function CerebroConsole({ thoughts }: CerebroConsoleProps) {
    return (
        <GlassPanel className="h-[400px] flex flex-col border-aethelgard-green/10">
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
                    <span className="text-xs font-outfit font-bold tracking-widest text-white/80 uppercase">Cerebro Existential Flow</span>
                </div>
                <div className="flex gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-white/5" />
                    <div className="w-2 h-2 rounded-full bg-white/5" />
                    <div className="w-2 h-2 rounded-full bg-aethelgard-green/40 shadow-[0_0_8px_rgba(0,255,65,0.4)]" />
                </div>
            </div>

            <div className="flex-1 bg-black/40 rounded-xl overflow-hidden flex flex-col border border-white/5">
                <div className="flex items-center gap-2 px-4 py-2 bg-white/5 border-b border-white/5">
                    <TerminalIcon size={12} className="text-white/60" />
                    <span className="text-[10px] font-mono text-white/60 uppercase tracking-widest">Autonomous_Thought_Stream.log</span>
                </div>

                <div className="flex-1 p-4 font-mono text-[11px] overflow-y-auto space-y-2 scrollbar-hide">
                    <AnimatePresence initial={false}>
                        {thoughts.length === 0 ? (
                            <p className="text-white/50 italic">Waiting for Aethelgard thoughts...</p>
                        ) : (
                            thoughts.map((thought, index) => (
                                <motion.div
                                    key={thought.id}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="flex gap-3 group"
                                >
                                    <span className="text-white/40 shrink-0">[{new Date(thought.timestamp).toLocaleTimeString()}]</span>
                                    <span className={cn(
                                        "shrink-0 font-bold uppercase tracking-wider",
                                        thought.level === 'error' ? 'text-red-500' :
                                            thought.level === 'warning' ? 'text-aethelgard-gold' :
                                                'text-aethelgard-green'
                                    )}>
                                        {thought.module}
                                    </span>
                                    <span className="text-white/70 group-hover:text-white transition-colors">
                                        {thought.message}
                                    </span>
                                </motion.div>
                            ))
                        )}
                    </AnimatePresence>
                </div>
            </div>

            <div className="mt-4 flex items-center justify-between px-2">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <Cpu size={12} className="text-white/50" />
                        <span className="text-[9px] text-white/50 uppercase font-mono">Core Load: 12%</span>
                    </div>
                    <div className="w-32 h-1 bg-white/5 rounded-full overflow-hidden">
                        <motion.div
                            animate={{ width: ['10%', '15%', '12%'] }}
                            className="h-full bg-aethelgard-green/40"
                        />
                    </div>
                </div>
                <button className="text-[9px] text-aethelgard-green/60 uppercase font-bold hover:text-aethelgard-green transition-colors tracking-widest">
                    Expand Trace →
                </button>
            </div>
        </GlassPanel>
    );
}

// Ensure cn is available if not globally defined or use a simple join
function cn(...classes: any[]) {
    return classes.filter(Boolean).join(' ');
}
