import { Activity, Database, Shield, HardDrive, Satellite, Wifi, Key, Terminal, Cpu, SignalHigh } from 'lucide-react';
import { SystemStatus } from '../../types/aethelgard';
import { motion } from 'framer-motion';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';

interface MonitorPageProps {
    status: SystemStatus;
}

export function MonitorPage({ status }: MonitorPageProps) {
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
                        {status.satellites && Object.entries(status.satellites).map(([id, sat]) => (
                            <div key={id} className="flex flex-col gap-2 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all cursor-crosshair group/sat">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className={cn(
                                            "w-2 h-2 rounded-full",
                                            sat.status === 'ONLINE' ? 'bg-aethelgard-green shadow-[0_0_8px_rgba(0,255,65,0.4)]' :
                                                sat.status === 'OFFLINE' ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]' : 'bg-white/10'
                                        )} />
                                        <span className="text-[11px] font-black text-white/90 uppercase tracking-tighter">{id}</span>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-1.5 opacity-40 group-hover/sat:opacity-100 transition-opacity">
                                            <Wifi size={12} />
                                            <span className="text-[10px] font-mono">{sat.latency.toFixed(0)}ms</span>
                                        </div>
                                        <span className={cn(
                                            "text-[9px] font-black uppercase",
                                            sat.status === 'ONLINE' ? 'text-aethelgard-green' : 'text-red-500'
                                        )}>
                                            {sat.status}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4 mt-1 opacity-40">
                                    <div className="flex gap-2">
                                        <span className={cn("text-[8px] font-black uppercase px-1 rounded-sm", sat.supports_data ? 'text-aethelgard-blue bg-aethelgard-blue/20' : 'text-white/10 bg-white/5')}>Market_Data</span>
                                        <span className={cn("text-[8px] font-black uppercase px-1 rounded-sm", sat.supports_exec ? 'text-purple-400 bg-purple-400/20' : 'text-white/10 bg-white/5')}>Execution</span>
                                    </div>
                                    {sat.last_error && (
                                        <span className="text-[8px] font-mono text-red-400 truncate max-w-[150px]">{sat.last_error}</span>
                                    )}
                                </div>
                            </div>
                        ))}
                        {(!status.satellites || Object.keys(status.satellites).length === 0) && (
                            <div className="h-full flex flex-col items-center justify-center opacity-20 py-10">
                                <Satellite size={32} />
                                <span className="text-[10px] font-black uppercase tracking-widest mt-2">No Satellites Linked</span>
                            </div>
                        )}
                    </div>
                </GlassPanel>

                {/* Sub-System Heartbeats */}
                <GlassPanel className="p-6 flex flex-col border-white/5">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <Activity size={18} className="text-aethelgard-green" />
                            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/60">Module Pulse Monitor</h3>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
                        {Object.entries(status.heartbeats)
                            .filter(([_, beat]) => typeof beat === 'string' || typeof beat === 'number')
                            .map(([module, beat]) => (
                                <div key={module} className="flex items-center justify-between p-4 rounded-xl bg-white/[0.01] border border-white/5 hover:bg-white/[0.03] transition-colors">
                                    <div className="flex items-center gap-4">
                                        <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-blue animate-pulse" />
                                        <div className="flex flex-col">
                                            <span className="text-[11px] font-bold text-white/80 uppercase tracking-widest">{module}</span>
                                            <span className="text-[8px] text-white/20 uppercase font-black">Sub-Module Live</span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-[10px] font-mono text-aethelgard-green/60">{beat.toString()}</span>
                                        <div className="p-1 rounded bg-white/5">
                                            <Activity size={10} className="text-white/20" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                    </div>

                    <button className="mt-6 w-full py-4 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-aethelgard-green/40 transition-all duration-500 group">
                        <div className="flex items-center justify-center gap-3 opacity-60 group-hover:opacity-100 transition-opacity">
                            <HardDrive size={16} />
                            <span className="text-[10px] font-black uppercase tracking-[0.3em]">Run Full Integrity Audit</span>
                        </div>
                    </button>
                </GlassPanel>
            </div>
        </motion.div>
    );
}
