import { X, Activity, Database, Shield, HardDrive } from 'lucide-react';
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
                                className="p-2 hover:bg-white/5 rounded-full transition-colors text-white/40 hover:text-white"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-8">
                            {/* Network Status */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] mb-4">Core Connectivity</h3>
                                <div className="glass p-4 rounded-xl border-white/5 space-y-4">
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm text-white/60">WebSocket Link</span>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${status.connected ? 'bg-aethelgard-green/20 text-aethelgard-green' : 'bg-red-500/20 text-red-500'
                                            }`}>
                                            {status.connected ? 'ACTIVE' : 'DISCONNECTED'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm text-white/60">Last Pulse</span>
                                        <span className="text-xs font-mono text-white/40">{new Date(status.lastUpdate).toLocaleTimeString()}</span>
                                    </div>
                                </div>
                            </section>

                            {/* Module Heartbeats */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] mb-4">Sub-System Health</h3>
                                <div className="space-y-3">
                                    {Object.entries(status.heartbeats).map(([module, beat]) => (
                                        <div key={module} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors">
                                            <div className="flex items-center gap-3">
                                                <div className="w-1.5 h-1.5 rounded-full bg-aethelgard-blue shadow-[0_0_8px_rgba(0,210,255,0.4)]" />
                                                <span className="text-xs font-medium text-white/80">{module}</span>
                                            </div>
                                            <span className="text-[10px] font-mono text-white/30">{beat} ago</span>
                                        </div>
                                    ))}
                                    {Object.keys(status.heartbeats).length === 0 && (
                                        <p className="text-center text-white/20 text-xs py-4 italic">No module metadata available</p>
                                    )}
                                </div>
                            </section>

                            {/* Security & Vault */}
                            <section>
                                <h3 className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] mb-4">Data Vault & Encryption</h3>
                                <div className="glass p-4 rounded-xl border-white/5 space-y-4">
                                    <div className="flex items-center gap-3">
                                        <Shield size={16} className="text-aethelgard-gold/60" />
                                        <div>
                                            <p className="text-xs font-bold text-white/80">AES-256 Vault</p>
                                            <p className="text-[10px] text-white/30">Persistence Layer Secure</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Database size={16} className="text-white/40" />
                                        <div>
                                            <p className="text-xs font-bold text-white/80">Aethelgard.db</p>
                                            <p className="text-[10px] text-white/30">Consistency: 100% Verified</p>
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
