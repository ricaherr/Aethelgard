import { motion } from 'framer-motion';
import {
    Cpu,
    BrainCircuit,
    Zap,
    Target,
    RefreshCcw,
    ShieldCheck,
    BarChart3,
    Search
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import { MarketRegime, EdgeMetrics, TuningLog } from '../../types/aethelgard';
import { useAethelgard } from '../../hooks/useAethelgard';
import { useState } from 'react';
import { NeuralHistoryPanel } from './NeuralHistoryPanel';
import { RegimeBadge } from './RegimeBadge';
import { WeightedMetricsVisualizer } from './WeightedMetricsVisualizer';

interface EdgeHubProps {
    metrics: EdgeMetrics;
    regime: MarketRegime;
}

export function EdgeHub({ metrics, regime }: EdgeHubProps) {
    const { getTuningLogs } = useAethelgard();
    const [isLogsOpen, setIsLogsOpen] = useState(false);
    const [tuningLogs, setTuningLogs] = useState<TuningLog[]>([]);

    const handleOpenLogs = async () => {
        const logs = await getTuningLogs(50);
        setTuningLogs(logs);
        setIsLogsOpen(true);
    };

    return (
        <div className="flex flex-col gap-8 animate-in fade-in duration-500">
            {/* Enhanced Header: With RegimeBadge */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-2xl font-outfit font-bold text-white/95 flex items-center gap-3">
                        <BrainCircuit className="text-aethelgard-green" size={28} />
                        EDGE Intelligence Hub
                    </h2>
                    <p className="text-white/60 text-sm mt-1">Autonomous monitoring and self-calibration engine active (Darwinismo Algorítmico).</p>
                </div>

                <div className="flex items-center gap-3 flex-col sm:flex-row">
                    {/* RegimeBadge: Premium Visual Indicator */}
                    <RegimeBadge 
                        regime={regime} 
                        size="large" 
                        showLabel={true} 
                        animated={true}
                    />
                    
                    <div className="flex items-center gap-3 px-4 py-2 bg-white/5 rounded-2xl border border-white/10">
                        <div className="w-2 h-2 rounded-full bg-aethelgard-green animate-pulse" />
                        <span className="text-xs font-bold text-white/80 tracking-widest uppercase">Self-Learning: ON</span>
                    </div>
                </div>
            </div>

            {/* Main Intelligence Grid */}
            <div className="grid grid-cols-12 gap-6">
                {/* Left: Autonomy Stats */}
                <div className="col-span-12 lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-6">
                    <GlassPanel className="p-6 flex flex-col gap-6" premium>
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-white/90 uppercase tracking-widest flex items-center gap-2">
                                <Target size={16} className="text-aethelgard-green" />
                                Confidence Radar
                            </h3>
                            <span className="text-[10px] font-mono text-white/40">Real-time Analysis</span>
                        </div>

                        <div className="flex flex-col items-center justify-center py-4 relative">
                            <div className="w-48 h-48 rounded-full border-4 border-white/5 flex items-center justify-center relative">
                                {/* Simulated Radar Effect */}
                                <div className="absolute inset-0 rounded-full border border-aethelgard-green/20 animate-ping" />
                                <div className="flex flex-col items-center">
                                    <span className="text-5xl font-outfit font-black text-white">{metrics.confidence}%</span>
                                    <span className="text-[10px] font-bold text-aethelgard-green uppercase tracking-widest">Calculated Edge</span>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 w-full mt-8 gap-4">
                                <StatRow label="Global Bias" value={metrics.global_bias} />
                                <StatRow label="ADX Strength" value={metrics.adx_strength.toFixed(2)} />
                                <StatRow label="Volatility" value={metrics.volatility} />
                                <StatRow label="Optimization" value={`${metrics.optimization_rate}%`} />
                            </div>
                        </div>
                    </GlassPanel>

                    <div className="flex flex-col gap-6">
                        <GlassPanel className="p-5 flex-1 border-white/5">
                            <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-[0.2em] mb-4">Autonomous Agents</h3>
                            <div className="flex flex-col gap-3">
                                <AgentItem name="Pattern Brain" status="Active" load={42} color="green" />
                                <AgentItem name="Risk Sentry" status="Monitoring" load={12} color="blue" />
                                <AgentItem name="Order Orchestrator" status="Standby" load={0} color="gray" />
                                <AgentItem name="Sentiment Analyzer" status="Scanning" load={68} color="purple" />
                            </div>
                        </GlassPanel>

                        <GlassPanel className="p-5 flex-1 border-white/5 bg-gradient-to-br from-white/[0.02] to-transparent">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-[0.2em]">Tuner Activity</h3>
                                <RefreshCcw size={12} className="text-white/20 animate-spin-slow" />
                            </div>
                            <div className="space-y-3">
                                <div className="p-3 rounded-lg bg-white/5 border border-white/5">
                                    <p className="text-[11px] text-white/80 leading-relaxed font-medium">
                                        Adjusted <span className="text-aethelgard-green font-bold text-[10px]">ADX_THRESHOLD</span> from 25 to 22.4 based on recent range persistence.
                                    </p>
                                    <span className="text-[9px] text-white/30 mt-2 block">14 minutes ago</span>
                                </div>
                            </div>
                        </GlassPanel>
                    </div>
                </div>

                {/* Right: Intelligence Insights */}
                <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
                    <GlassPanel className="p-6 border-aethelgard-green/10 flex flex-col gap-6 bg-gradient-to-b from-aethelgard-green/[0.03] to-transparent">
                        <div>
                            <h3 className="text-sm font-bold text-white/90 uppercase tracking-widest mb-1">Cerebro Insights</h3>
                            <p className="text-[11px] text-white/60">AI-generated context for the current regime.</p>
                        </div>

                        <div className="flex flex-col gap-4">
                            <InsightCard
                                icon={<BarChart3 size={16} />}
                                title="Regime Persistence"
                                desc={`The current ${regime} regime shows 84% persistence over the last 48 hours. Expect stability.`}
                            />
                            <InsightCard
                                icon={<ShieldCheck size={16} />}
                                title="Risk Distribution"
                                desc="Low correlation detected across major forex pairs. Diversification coefficient: 0.92."
                            />
                            <InsightCard
                                icon={<Zap size={16} />}
                                title="Execution Priority"
                                desc="High priority on Swing setups due to strong H4 trend structure."
                            />
                        </div>

                        <button
                            onClick={handleOpenLogs}
                            className="w-full py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-white/60 hover:bg-white/10 hover:text-white transition-all active:scale-[0.98] mt-auto"
                        >
                            View Detailed Learning Logs
                        </button>
                    </GlassPanel>
                </div>

                {/* WeightedMetricsVisualizer: Full Width - Darwinismo Algorítmico Visualization */}
                <div className="col-span-12">
                    <WeightedMetricsVisualizer 
                        currentRegime={regime}
                        height={350}
                    />
                </div>

            </div>

            <NeuralHistoryPanel
                isOpen={isLogsOpen}
                onClose={() => setIsLogsOpen(false)}
                logs={tuningLogs}
            />
        </div>
    );
}

function StatRow({ label, value }: { label: string, value: string | number }) {
    return (
        <div className="flex justify-between items-center py-2 border-b border-white/5">
            <span className="text-[10px] text-white/50 font-medium uppercase tracking-wider">{label}</span>
            <span className="text-[11px] text-white/90 font-bold font-mono">{value}</span>
        </div>
    );
}

function AgentItem({ name, status, load, color }: { name: string, status: string, load: number, color: string }) {
    const colors: Record<string, string> = {
        green: 'bg-aethelgard-green',
        blue: 'bg-blue-500',
        purple: 'bg-purple-500',
        gray: 'bg-white/20'
    };

    return (
        <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
                <div className={cn("w-1.5 h-1.5 rounded-full shadow-[0_0_8px]", colors[color])} />
                <div className="flex flex-col">
                    <span className="text-[11px] font-bold text-white/90">{name}</span>
                    <span className="text-[9px] text-white/40 uppercase font-bold tracking-tighter">{status}</span>
                </div>
            </div>
            <div className="flex-1 max-w-[80px]">
                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                    <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${load}%` }}
                        className={cn("h-full", colors[color])}
                    />
                </div>
            </div>
        </div>
    );
}

function InsightCard({ icon, title, desc }: { icon: any, title: string, desc: string }) {
    return (
        <div className="flex gap-4 p-4 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors group">
            <div className="text-aethelgard-green mt-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
                {icon}
            </div>
            <div className="flex flex-col gap-1">
                <h4 className="text-[11px] font-bold text-white/90">{title}</h4>
                <p className="text-[10px] leading-relaxed text-white/60">{desc}</p>
            </div>
        </div>
    );
}
