import { Activity, Database, Shield, HardDrive, Satellite, Wifi, Key, Terminal, Cpu, SignalHigh, ShieldCheck, Zap, AlertTriangle, CheckCircle2, Search, ArrowRight, Info, Server, LineChart } from 'lucide-react';
import { SystemStatus, SatelliteStatus } from '../../types/aethelgard';
import { motion } from 'framer-motion';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import { useState } from 'react';
import { CerebroThought } from '../../types/aethelgard';
import { AuditLiveMonitor } from './AuditLiveMonitor';

interface MonitorPageProps {
    status: SystemStatus;
    thoughts: CerebroThought[];
    runAudit?: () => Promise<boolean>;
    runRepair: (stage: string) => Promise<boolean>;
}

export const MonitorPage = ({ status, thoughts, runAudit, runRepair }: MonitorPageProps) => {
    const [isAuditing, setIsAuditing] = useState(false);
    const [auditResult, setAuditResult] = useState<{ success: boolean, time: string } | null>(null);
    const [isLiveMonitorOpen, setIsLiveMonitorOpen] = useState(false);

    const handleAudit = async () => {
        if (!runAudit || isAuditing) return;

        setIsAuditing(true);
        setIsLiveMonitorOpen(true);
        const success = await runAudit();
        setIsAuditing(false);
        setAuditResult({ success, time: new Date().toLocaleTimeString() });
    };
    const cpuLoad = status.cpu_load ?? 0;

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-6 h-full p-2"
        >
            {/* Header / Global Status */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <GlassPanel className="p-6 flex flex-col gap-4 border-aethelgard-blue/20">
                    <div className="flex items-center gap-3">
                        <Activity size={20} className="text-aethelgard-blue" />
                        <h3 className="font-outfit font-bold text-lg">Core Connectivity</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-white/80">WebSocket Link</span>
                            <span className={cn(
                                "text-[10px] font-bold px-2 py-1 rounded-md tracking-widest",
                                status.connected ? 'bg-aethelgard-green/10 text-aethelgard-green border border-aethelgard-green/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'
                            )}>
                                {status.connected ? 'STABLE_UPLINK' : 'LINK_TERMINATED'}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-white/50">Heartbeat Frequency</span>
                            <span className="text-xs font-mono text-white/80">5000ms</span>
                        </div>
                    </div>
                </GlassPanel>

                <GlassPanel className="p-6 flex flex-col gap-4 border-aethelgard-green/20">
                    <div className="flex items-center gap-3">
                        <Cpu size={20} className="text-aethelgard-green" />
                        <h3 className="font-outfit font-bold text-lg">Compute Resource</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-white/80">CPU Global Load</span>
                            <span className="text-xs font-mono font-bold text-white">{cpuLoad.toFixed(1)}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                            <motion.div
                                animate={{ width: `${cpuLoad}%` }}
                                className={cn(
                                    "h-full rounded-full transition-colors duration-500",
                                    cpuLoad > 80 ? 'bg-red-500' : cpuLoad > 50 ? 'bg-orange-500' : 'bg-aethelgard-green'
                                )}
                            />
                        </div>
                    </div>
                </GlassPanel>

                <GlassPanel className="p-6 flex flex-col gap-4 border-aethelgard-gold/20">
                    <div className="flex items-center gap-3">
                        <Shield size={20} className="text-aethelgard-gold" />
                        <h3 className="font-outfit font-bold text-lg">Source Fidelity</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-white/80">Sync Score</span>
                            <span className="text-xs font-mono font-bold text-aethelgard-gold">
                                {((status.sync_fidelity?.score ?? 1.0) * 100).toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-[10px] text-white/40 leading-relaxed italic">
                            {status.sync_fidelity?.details || "Garantizando integridad de ejecución Omnichain."}
                        </p>
                    </div>
                </GlassPanel>
            </div>

            {/* Main Diagnostics Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1 min-h-0">
                {/* Satellite Network */}
                <GlassPanel className="p-6 flex flex-col border-white/5 group overflow-hidden">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <Satellite size={18} className="text-aethelgard-blue" />
                            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/60">Distributed Satellites</h3>
                        </div>
                        <div className="h-4 px-2 rounded-full bg-aethelgard-blue/10 border border-aethelgard-blue/20 flex items-center">
                            <span className="text-[8px] font-black text-aethelgard-blue uppercase">H-Freq Monitor</span>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-hide">
                        {status.satellites && Object.entries(status.satellites).map(([id, sat]: [string, any]) => {
                            const satellite = sat as SatelliteStatus;
                            return (
                                <div key={id} className="flex flex-col gap-2 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all cursor-crosshair group/sat">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={cn(
                                                "w-2 h-2 rounded-full",
                                                satellite.status === 'ONLINE' ? 'bg-aethelgard-green shadow-[0_0_8px_rgba(0,255,65,0.4)]' :
                                                    satellite.status === 'OFFLINE' ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]' : 'bg-white/10'
                                            )} />
                                            <span className="text-[11px] font-black text-white/90 uppercase tracking-tighter">{id}</span>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="flex items-center gap-1.5 opacity-40 group-hover/sat:opacity-100 transition-opacity">
                                                <Wifi size={12} />
                                                <span className="text-[10px] font-mono">{(satellite.latency || 0).toFixed(0)}ms</span>
                                            </div>
                                            <span className={cn(
                                                "text-[9px] font-black uppercase",
                                                satellite.status === 'ONLINE' ? 'text-aethelgard-green' : 'text-red-500'
                                            )}>
                                                {satellite.status}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4 mt-1 opacity-40">
                                        <div className="flex gap-2">
                                            <span className={cn("text-[8px] font-black uppercase px-1 rounded-sm", satellite.supports_data ? 'text-aethelgard-blue bg-aethelgard-blue/20' : 'text-white/10 bg-white/5')}>Market_Data</span>
                                            <span className={cn("text-[8px] font-black uppercase px-1 rounded-sm", satellite.supports_exec ? 'text-purple-400 bg-purple-400/20' : 'text-white/10 bg-white/5')}>Execution</span>
                                        </div>
                                        {satellite.last_error && (
                                            <span className="text-[8px] font-mono text-red-400 truncate max-w-[150px]">{satellite.last_error}</span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                        {(!status.satellites || Object.keys(status.satellites).length === 0) && (
                            <div className="h-full flex flex-col items-center justify-center opacity-20 py-10">
                                <Satellite size={32} />
                                <span className="text-[10px] font-black uppercase tracking-widest mt-2">No Satellites Linked</span>
                            </div>
                        )}
                    </div>
                </GlassPanel>

                {/* System Integrity Matrix (Phase 8 Evolution) */}
                <GlassPanel className="p-6 flex flex-col border-white/5 relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                        <Shield size={120} className="text-aethelgard-blue" />
                    </div>

                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <ShieldCheck size={18} className="text-aethelgard-blue" />
                            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/60">System Integrity Matrix</h3>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-green animate-pulse" />
                            <span className="text-[8px] font-black text-aethelgard-green uppercase tracking-widest">Live_Safe</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 flex-1">
                        {[
                            { id: 'ARC', label: 'Architecture', icon: <Cpu size={14} />, status: 'Optimized', color: 'text-aethelgard-blue' },
                            { id: 'DBV', label: 'Data Vault', icon: <Database size={14} />, status: 'Synchronized', color: 'text-aethelgard-green' },
                            { id: 'EMS', label: 'Edge EMS', icon: <Zap size={14} />, status: 'Active', color: 'text-purple-400' },
                            { id: 'RSK', label: 'Risk Shield', icon: <Shield size={14} />, status: 'Enforced', color: 'text-aethelgard-gold' },
                            { id: 'ALP', label: 'Alpha Intel', icon: <Activity size={14} />, status: 'Stable', color: 'text-aethelgard-blue' },
                            { id: 'SEC', label: 'Security', icon: <Key size={14} />, status: 'Locked', color: 'text-white' }
                        ].map((vector, i) => (
                            <motion.div
                                key={vector.id}
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ delay: i * 0.05 }}
                                className="flex flex-col gap-2 p-3 rounded-xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] transition-all hover:border-white/10 group/vector"
                            >
                                <div className="flex items-center justify-between">
                                    <div className={cn("p-1.5 rounded-lg bg-white/5", vector.color)}>
                                        {vector.icon}
                                    </div>
                                    <span className="text-[8px] font-mono text-white/20">V_{vector.id}</span>
                                </div>
                                <div>
                                    <div className="text-[10px] font-bold text-white/80 uppercase tracking-wider">{vector.label}</div>
                                    <div className={cn("text-[9px] font-black uppercase mt-0.5", vector.id === 'SEC' ? 'text-white/40' : 'text-aethelgard-green/80')}>
                                        {vector.status}
                                    </div>
                                </div>
                                <div className="w-full h-0.5 bg-white/5 rounded-full mt-1 overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: '100%' }}
                                        transition={{ duration: 1, delay: 0.5 + i * 0.1 }}
                                        className={cn("h-full", vector.id === 'SEC' ? 'bg-white/20' : 'bg-aethelgard-green/40')}
                                    />
                                </div>
                            </motion.div>
                        ))}
                    </div>

                    <button
                        onClick={handleAudit}
                        disabled={isAuditing}
                        className={`mt-4 w-full py-4 rounded-xl border transition-all duration-500 group flex flex-col items-center gap-1 overflow-hidden relative ${
                            isAuditing
                                ? 'bg-aethelgard-blue/5 border-aethelgard-blue/20 cursor-not-allowed'
                                : auditResult
                                    ? auditResult.success
                                        ? 'bg-aethelgard-green/10 border-aethelgard-green/40 hover:bg-aethelgard-green/20'
                                        : 'bg-red-500/10 border-red-500/40 hover:bg-red-500/20'
                                    : 'bg-white/5 border-white/10 hover:bg-aethelgard-blue/10 hover:border-aethelgard-blue/40'
                        }`}
                    >
                        {isAuditing && (
                            <motion.div
                                className="absolute inset-0 bg-gradient-to-r from-transparent via-aethelgard-blue/10 to-transparent"
                                animate={{ x: ['-100%', '100%'] }}
                                transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                            />
                        )}
                        <div className="flex items-center justify-center gap-3 relative z-10">
                            <ShieldCheck size={16} className={cn(
                                "transition-colors",
                                isAuditing
                                    ? "text-aethelgard-blue animate-pulse"
                                    : auditResult
                                        ? auditResult.success
                                            ? "text-aethelgard-green"
                                            : "text-red-500"
                                        : "text-white/40 group-hover:text-aethelgard-blue"
                            )} />
                            <span className={cn(
                                "text-[10px] font-black uppercase tracking-[0.3em] transition-colors",
                                isAuditing
                                    ? "text-aethelgard-blue"
                                    : auditResult
                                        ? auditResult.success
                                            ? "text-aethelgard-green"
                                            : "text-red-500"
                                        : "text-white/60 group-hover:text-white"
                            )}>
                                {isAuditing ? "Auditing System Integrity..." : auditResult ? (auditResult.success ? "✅ Validation Complete" : "❌ Validation Failed") : "Run Global Validation"}
                            </span>
                        </div>
                        {auditResult && !isAuditing && (
                            <div className="flex items-center gap-2 opacity-60">
                                <span className={cn("w-1 h-1 rounded-full", auditResult.success ? "bg-aethelgard-green" : "bg-red-500")} />
                                <span className="text-[8px] font-medium text-white tracking-widest uppercase">
                                    L_AUDIT: {auditResult.time}
                                </span>
                            </div>
                        )}
                    </button>
                </GlassPanel>
            </div>

            <AuditLiveMonitor
                isOpen={isLiveMonitorOpen}
                onClose={() => setIsLiveMonitorOpen(false)}
                thoughts={thoughts}
                runRepair={runRepair}
            />
        </motion.div>
    );
}
