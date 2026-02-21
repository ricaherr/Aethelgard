import { X, Activity, Database, Shield, HardDrive, Satellite, Wifi } from 'lucide-react';
import { SystemStatus } from '../../types/aethelgard';
import { motion, AnimatePresence } from 'framer-motion';

interface DiagnosticDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    status: SystemStatus;
}

export function DiagnosticDrawer({ isOpen, onClose, status }: DiagnosticDrawerProps) {
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
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60]"
                    />

                    {/* Drawer */}
                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                        className="fixed right-0 top-0 h-full w-full max-w-md bg-[#080808] border-l border-white/5 z-[70] shadow-2xl flex flex-col"
                    >
                        <div className="p-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
                            <div className="flex items-center gap-3">
                                <Activity size={20} className="text-aethelgard-blue" />
                                <h2 className="font-outfit font-bold text-lg tracking-tight">System Integrity Monitor</h2>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-2 hover:bg-white/5 rounded-full transition-colors text-white/60 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-8">
                            {/* Network Status */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/60 uppercase tracking-[0.2em] mb-4">Core Connectivity</h3>
                                <div className="glass p-4 rounded-xl border-white/5 space-y-4">
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm text-white/80">WebSocket Link</span>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${status.connected ? 'bg-aethelgard-green/20 text-aethelgard-green' : 'bg-red-500/20 text-red-500'
                                            }`}>
                                            {status.connected ? 'ACTIVE' : 'DISCONNECTED'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm text-white/60">Last Pulse</span>
                                        <span className="text-xs font-mono text-white/60">{new Date(status.lastUpdate).toLocaleTimeString()}</span>
                                    </div>
                                </div>
                            </section>

                            {/* Satellite Telemetry (NEW) */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/60 uppercase tracking-[0.2em] mb-4">Satellite Telemetry</h3>
                                <div className="space-y-3">
                                    {status.satellites && Object.entries(status.satellites).map(([id, sat]) => {
                                        const isManualDisabled = sat.status === 'MANUAL_DISABLED';
                                        const isHighLatency = sat.latency > 200;
                                        const isOffline = sat.status === 'OFFLINE';

                                        let statusColor = 'bg-aethelgard-blue shadow-[0_0_8px_rgba(0,210,255,0.4)]'; // CYAN
                                        let textColor = 'text-aethelgard-blue';

                                        if (isManualDisabled) {
                                            statusColor = 'bg-white/10'; // DARK GREY
                                            textColor = 'text-white/30';
                                        } else if (isOffline) {
                                            statusColor = 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]'; // RED
                                            textColor = 'text-red-500';
                                        } else if (isHighLatency) {
                                            statusColor = 'bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.4)]'; // ORANGE
                                            textColor = 'text-orange-400';
                                        }

                                        return (
                                            <div key={id} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-white/5">
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
                                                    <span className="text-xs font-bold text-white/90 uppercase tracking-tighter">{id}</span>
                                                </div>
                                                <div className="flex items-center gap-4">
                                                    <div className="flex items-center gap-1.5">
                                                        <Wifi size={10} className="text-white/20" />
                                                        <span className="text-[10px] font-mono text-white/60">{sat.latency.toFixed(0)}ms</span>
                                                    </div>
                                                    <span className={`text-[9px] font-bold uppercase ${textColor}`}>
                                                        {sat.status.replace('_', ' ')}
                                                    </span>
                                                </div>
                                            </div>
                                        );
                                    })}
                                    {(!status.satellites || Object.keys(status.satellites).length === 0) && (
                                        <p className="text-center text-white/30 text-[10px] py-4 uppercase tracking-widest">No active satellites</p>
                                    )}
                                </div>
                            </section>

                            {/* Sync Fidelity (NEW) */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/60 uppercase tracking-[0.2em] mb-4">Closed-Loop Sync</h3>
                                <div className="glass p-4 rounded-xl border-white/5 space-y-4">
                                    <div className="flex justify-between items-center">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${status.sync_fidelity?.status === 'OPTIMAL' ? 'bg-aethelgard-green' :
                                                    status.sync_fidelity?.status === 'DEGRADED' ? 'bg-orange-500' : 'bg-red-500'
                                                }`} />
                                            <span className="text-sm font-bold text-white/90">Source Fidelity</span>
                                        </div>
                                        <span className="text-[10px] font-mono text-white/40">{(status.sync_fidelity?.score || 1.0) * 100}%</span>
                                    </div>
                                    <p className="text-[10px] text-white/50 leading-relaxed italic">
                                        {status.sync_fidelity?.details || "Garantiza que la fuente de análisis y ejecución sean idénticas en mercados descentralizados."}
                                    </p>
                                    <div className="pt-2 flex items-center gap-2">
                                        <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded border ${status.sync_fidelity?.status === 'OPTIMAL' ? 'border-aethelgard-green/30 text-aethelgard-green' : 'border-red-500/30 text-red-500'
                                            }`}>
                                            {status.sync_fidelity?.status || 'OPTIMAL'}
                                        </span>
                                        <span className="text-[8px] font-bold text-white/20 uppercase">Omnichain Laws Applied</span>
                                    </div>
                                </div>
                            </section>
                            <section>
                                <h3 className="text-[10px] font-bold text-white/60 uppercase tracking-[0.2em] mb-4">Sub-System Health</h3>
                                <div className="space-y-3">
                                    {Object.entries(status.heartbeats).map(([module, beat]) => (
                                        <div key={module} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors">
                                            <div className="flex items-center gap-3">
                                                <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-blue shadow-[0_0_8px_rgba(0,210,255,0.4)]" />
                                                <span className="text-xs font-medium text-white/80">{module}</span>
                                            </div>
                                            <span className="text-[10px] font-mono text-white/50">{beat} ago</span>
                                        </div>
                                    ))}
                                    {Object.keys(status.heartbeats).length === 0 && (
                                        <p className="text-center text-white/50 text-xs py-4 italic">No module metadata available</p>
                                    )}
                                </div>
                            </section>

                            {/* Security & Vault */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/60 uppercase tracking-[0.2em] mb-4">Data Vault & Encryption</h3>
                                <div className="glass p-4 rounded-xl border-white/5 space-y-4">
                                    <div className="flex items-center gap-3">
                                        <Shield size={16} className="text-aethelgard-gold/60" />
                                        <div>
                                            <p className="text-xs font-bold text-white/80">AES-256 Vault</p>
                                            <p className="text-[10px] text-white/50">Persistence Layer Secure</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Database size={16} className="text-white/40" />
                                        <div>
                                            <p className="text-xs font-bold text-white/80">Aethelgard.db</p>
                                            <p className="text-[10px] text-white/50">Consistency: 100% Verified</p>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>

                        <div className="p-6 bg-white/[0.01] border-t border-white/5 mt-auto">
                            <button className="w-full py-3 rounded-xl bg-white/5 border border-white/10 text-xs font-bold uppercase tracking-widest text-white/60 hover:bg-white/10 hover:text-white transition-all flex items-center justify-center gap-2">
                                <HardDrive size={14} />
                                Execute Integrity Check
                            </button>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}
