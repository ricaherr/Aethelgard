import { Search, Bell, Zap, Database, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../../hooks/useAuth';
import { useAethelgard } from '../../hooks/useAethelgard';

export function TerminalHeader() {
    const { tenantId, logout } = useAuth();
    const { status } = useAethelgard();

    return (
        <header className="h-20 flex items-center justify-between px-8 z-40 border-b border-white/5 glass bg-transparent">
            <div className="flex flex-col">
                <h1 className="font-outfit text-xl font-bold tracking-tight text-white/90 flex items-center gap-3">
                    Executive Command Center
                    {tenantId && (
                        <span className="px-2 py-0.5 rounded-md bg-aethelgard-cyan/10 border border-aethelgard-cyan/20 text-[10px] text-aethelgard-cyan font-mono tracking-widest uppercase">
                            TENANT: {tenantId}
                        </span>
                    )}
                </h1>
                <p className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-bold">Aethelgard Autonomous Ecosystem v2.0</p>
            </div>

            <div className="flex items-center gap-8">
                {/* Search / Context */}
                <div className="hidden md:flex items-center gap-3 px-4 py-2 rounded-xl bg-white/5 border border-white/5 group focus-within:border-aethelgard-cyan/30 transition-all">
                    <Search size={14} className="text-white/20 group-focus-within:text-aethelgard-cyan/50" />
                    <input
                        type="text"
                        placeholder="Search instrument..."
                        className="bg-transparent border-none outline-none text-xs w-48 text-white/60 placeholder:text-white/20"
                    />
                </div>

                {/* DB Sync Status (Tenant Isolation) */}
                <div className="flex items-center gap-2 cursor-help group">
                    <div className="flex flex-col text-right">
                        <span className="text-[10px] text-white/30 uppercase tracking-widest font-bold">Persistence</span>
                        <span className="text-[9px] font-mono font-bold text-aethelgard-cyan">SYNCED</span>
                    </div>
                    <Database size={16} className="text-aethelgard-cyan group-hover:scale-110 transition-transform" />
                </div>

                {/* Notification / Alert */}
                <div className="relative cursor-pointer hover:scale-110 transition-transform">
                    <Bell size={20} className="text-white/40" />
                    <div className="absolute -top-1 -right-0.5 w-2 h-2 rounded-full bg-aethelgard-red border-2 border-dark animate-pulse" />
                </div>

                {/* Global Connectivity */}
                <div className="flex items-center gap-3 pl-6 border-l border-white/5">
                    <div className="text-right flex flex-col justify-center">
                        <span className="text-[10px] font-bold text-white/20 uppercase tracking-widest leading-none mb-1">Cerebro Link</span>
                        <span className={`text-[9px] font-mono font-bold ${status.connected ? 'text-aethelgard-cyan' : 'text-aethelgard-red'}`}>
                            {status.connected ? 'STABLE' : 'OFFLINE'}
                        </span>
                    </div>
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${status.connected ? 'bg-aethelgard-cyan/10 border border-aethelgard-cyan/20' : 'bg-aethelgard-red/10 border border-aethelgard-red/20'}`}>
                        <Zap size={16} className={status.connected ? 'text-aethelgard-cyan' : 'text-aethelgard-red'} />
                    </div>
                </div>

                {/* Logout Button */}
                <div className="relative group ml-4">
                    <button
                        onClick={logout}
                        className="w-10 h-10 rounded-xl flex items-center justify-center border border-white/5 bg-white/5 text-white/40 hover:text-aethelgard-red hover:border-aethelgard-red/30 hover:bg-aethelgard-red/5 transition-all outline-none"
                    >
                        <LogOut size={18} />
                    </button>

                    {/* Premium Tooltip */}
                    <div className="absolute top-full right-0 mt-3 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                        <motion.div
                            initial={{ opacity: 0, y: -5 }}
                            whileHover={{ opacity: 1, y: 0 }}
                            className="bg-[#0A0A0A] border border-white/10 px-3 py-1.5 rounded-lg shadow-2xl"
                        >
                            <span className="text-[10px] font-mono text-white/60 whitespace-nowrap tracking-widest uppercase">
                                Terminate Session
                            </span>
                        </motion.div>
                    </div>
                </div>
            </div>
        </header>
    );
}
