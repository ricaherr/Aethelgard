import { useState, useEffect } from 'react';
import { MarketRegime } from './types/aethelgard';
import {
    LayoutDashboard,
    Cpu,
    Activity,
    Settings,
    Bell,
    Search,
    Zap,
    Briefcase,
    ScanEye,
    Satellite
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// Hooks
import { useAethelgard } from './hooks/useAethelgard';

// Components
import { MarketStatus } from './components/trader/MarketStatus';
import { AlphaSignals } from './components/trader/AlphaSignals';
import { CerebroConsole } from './components/trader/CerebroConsole';
import { DiagnosticDrawer } from './components/diagnostic/DiagnosticDrawer';
import { EdgeHub } from './components/edge/EdgeHub';
import { ConfigHub } from './components/config/ConfigHub';
import { PortfolioView } from './components/portfolio/PortfolioView';
import { GlassPanel } from './components/common/GlassPanel';
import { AnalysisPage } from './components/analysis';
import { SatelliteLink } from './components/satellite/SatelliteLink';
import { MonitorPage } from './components/diagnostic/MonitorPage';

function App() {
    const [activeTab, setActiveTab] = useState('trader');
    const [isDiagOpen, setIsDiagOpen] = useState(false);

    // Real-time data from Cerebro Brain
    const { regime, signals, thoughts, status, metrics, sendCommand, runAudit } = useAethelgard();

    const [riskStatus, setRiskStatus] = useState<any>(null);

    useEffect(() => {
        const fetchRisk = async () => {
            try {
                const res = await fetch('/api/risk/status');
                if (res.ok) {
                    const data = await res.json();
                    setRiskStatus(data);
                }
            } catch (err) {
                console.error('Error fetching risk status:', err);
            }
        };
        fetchRisk();
        const interval = setInterval(fetchRisk, 20000); // 20s update
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="min-h-screen w-full flex bg-[#050505] text-white/90 font-sans overflow-hidden">
            {/* Sidebar Navigation */}
            <nav className="w-16 lg:w-20 glass border-r border-white/5 flex flex-col items-center py-8 gap-8 z-50">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-aethelgard-green to-aethelgard-blue flex items-center justify-center shadow-lg shadow-aethelgard-green/20 group cursor-pointer">
                    <span className="font-outfit font-bold text-dark text-xl group-hover:scale-110 transition-transform">A</span>
                </div>

                <div className="flex flex-col gap-6 mt-12">
                    <NavIcon
                        icon={<LayoutDashboard size={22} />}
                        active={activeTab === 'trader'}
                        onClick={() => setActiveTab('trader')}
                        label="Trader"
                    />
                    <NavIcon
                        icon={<Activity size={22} />}
                        active={activeTab === 'analysis'}
                        onClick={() => setActiveTab('analysis')}
                        label="Análisis"
                    />
                    <NavIcon
                        icon={<Briefcase size={22} />}
                        active={activeTab === 'portfolio'}
                        onClick={() => setActiveTab('portfolio')}
                        label="Portfolio"
                    />
                    <NavIcon
                        icon={<Cpu size={22} />}
                        active={activeTab === 'edge'}
                        onClick={() => setActiveTab('edge')}
                        label="EDGE"
                    />
                    <NavIcon
                        icon={<Satellite size={22} />}
                        active={activeTab === 'satellite'}
                        onClick={() => setActiveTab('satellite')}
                        label="Satellite Link"
                    />
                    <NavIcon
                        icon={<ScanEye size={22} />}
                        active={activeTab === 'monitor'}
                        onClick={() => setActiveTab('monitor')}
                        label="Monitor"
                    />
                </div>

                <div className="mt-auto">
                    <NavIcon
                        icon={<Settings size={22} />}
                        active={activeTab === 'settings'}
                        onClick={() => setActiveTab('settings')}
                        label="Settings"
                    />
                </div>
            </nav>

            <main className="flex-1 flex flex-col relative h-screen">
                {/* Decorative Background Elements */}
                <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-aethelgard-green/5 blur-[120px] rounded-full -translate-y-1/2 translate-x-1/2 pointer-events-none" />
                <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-aethelgard-blue/5 blur-[120px] rounded-full translate-y-1/2 -translate-x-1/2 pointer-events-none" />

                {/* Header */}
                <header className="h-20 flex items-center justify-between px-8 z-40">
                    <div className="flex flex-col">
                        <h1 className="font-outfit text-xl font-bold tracking-tight text-white/90">Executive Command Center</h1>
                        <p className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-bold">Aethelgard Autonomous Ecosystem v2.0</p>
                    </div>

                    <div className="flex items-center gap-8">
                        {/* Search / Context */}
                        <div className="hidden md:flex items-center gap-3 px-4 py-2 rounded-xl bg-white/5 border border-white/5 group focus-within:border-aethelgard-green/30 transition-all">
                            <Search size={14} className="text-white/20 group-focus-within:text-aethelgard-green/50" />
                            <input
                                type="text"
                                placeholder="Search instrument..."
                                className="bg-transparent border-none outline-none text-xs w-48 text-white/60 placeholder:text-white/20"
                            />
                        </div>

                        {/* Notification / Alert */}
                        <div className="relative cursor-pointer hover:scale-110 transition-transform">
                            <Bell size={20} className="text-white/40" />
                            <div className="absolute -top-1 -right-0.5 w-2 h-2 rounded-full bg-red-500 border-2 border-dark" />
                        </div>

                        {/* Global Connectivity */}
                        <div className="flex items-center gap-3 pl-6 border-l border-white/5">
                            <div className="text-right flex flex-col justify-center">
                                <span className="text-[10px] font-bold text-white/20 uppercase tracking-widest leading-none mb-1">Cerebro Link</span>
                                <span className={`text-[9px] font-mono font-bold ${status.connected ? 'text-aethelgard-green' : 'text-red-500'}`}>
                                    {status.connected ? 'STABLE' : 'OFFLINE'}
                                </span>
                            </div>
                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${status.connected ? 'bg-aethelgard-green/10' : 'bg-red-500/10'}`}>
                                <Zap size={16} className={status.connected ? 'text-aethelgard-green' : 'text-red-500'} />
                            </div>
                        </div>
                    </div>
                </header>

                {/* Main Content Viewport */}
                <div className="flex-1 p-8 overflow-y-auto scrollbar-hide">
                    <AnimatePresence mode="wait">
                        {activeTab === 'trader' && (
                            <motion.div
                                key="trader-view"
                                initial={{ opacity: 0, scale: 0.99 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 1.01 }}
                                className="grid grid-cols-12 gap-6 h-full"
                            >
                                {/* Left Column: Context & Intelligence */}
                                <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">
                                    <MarketStatus regime={regime} metrics={metrics} />
                                    <CerebroConsole
                                        thoughts={thoughts}
                                        status={status}
                                        onExpand={() => setActiveTab('monitor')}
                                    />
                                </div>

                                {/* Right Column: Signal Execution Hub */}
                                <div className="col-span-12 xl:col-span-8 flex flex-col gap-6">
                                    {/* Quick Stats Banner */}
                                    <div className="grid grid-cols-4 gap-4">
                                        <StatBadge label="Total Alpha" value="24.8%" trend="+2.4%" />
                                        <StatBadge label="Active Trades" value="3" trend="Stable" />
                                        <StatBadge label="Edge Accuracy" value="68%" trend="+5%" />
                                        <StatBadge
                                            label="Risk Factor"
                                            value={riskStatus?.risk_mode || 'NORMAL'}
                                            trend={riskStatus ? `${riskStatus.current_risk_pct.toFixed(2)}%` : 'Safe'}
                                        />
                                    </div>

                                    {/* Main Opportunity Stream */}
                                    <AlphaSignals signals={signals} />
                                </div>
                            </motion.div>
                        )}
                        {activeTab === 'analysis' && (
                            <motion.div
                                key="analysis-view"
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                className="h-full"
                            >
                                <AnalysisPage />
                            </motion.div>
                        )}

                        {activeTab === 'portfolio' && (
                            <motion.div
                                key="portfolio-view"
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                className="h-full"
                            >
                                <PortfolioView />
                            </motion.div>
                        )}

                        {activeTab === 'edge' && (
                            <motion.div
                                key="edge-view"
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                className="h-full"
                            >
                                <EdgeHub metrics={metrics} regime={regime} />
                            </motion.div>
                        )}

                        {activeTab === 'settings' && (
                            <motion.div
                                key="settings-view"
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -20 }}
                                className="h-full"
                            >
                                <ConfigHub />
                            </motion.div>
                        )}

                        {activeTab === 'satellite' && (
                            <motion.div
                                key="satellite-view"
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 1.05 }}
                                className="h-full"
                            >
                                <SatelliteLink />
                            </motion.div>
                        )}
                        {activeTab === 'monitor' && (
                            <motion.div
                                key="monitor-view"
                                initial={{ opacity: 0, scale: 0.98 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 1.02 }}
                                className="h-full"
                            >
                                <MonitorPage status={status} runAudit={runAudit} />
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* Diagnostic Drawer Overlay */}
                <DiagnosticDrawer
                    isOpen={isDiagOpen}
                    onClose={() => setIsDiagOpen(false)}
                    status={status}
                />
            </main>
        </div>
    );
}

function NavIcon({ icon, active = false, onClick, label }: any) {
    return (
        <div className="relative group">
            <button
                onClick={onClick}
                className={`p-3 rounded-xl transition-all duration-300 ${active
                    ? 'bg-aethelgard-green/10 text-aethelgard-green border border-aethelgard-green/20 shadow-[0_0_15px_rgba(0,255,65,0.1)]'
                    : 'text-white/20 hover:text-white/80 hover:bg-white/5'
                    }`}
            >
                {icon}
            </button>
            <div className="absolute left-full ml-4 px-2 py-1 rounded bg-white/10 backdrop-blur-md text-[10px] text-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-[100] border border-white/5">
                {label}
            </div>
        </div>
    );
}

function StatBadge({ label, value, trend }: { label: string, value: string, trend: string }) {
    return (
        <GlassPanel className="p-4 flex flex-col justify-center gap-1 border-white/5">
            <span className="text-[10px] text-white/30 uppercase tracking-widest font-bold">{label}</span>
            <div className="flex items-baseline gap-2">
                <span className="text-xl font-outfit font-bold text-white/80">{value}</span>
                <span className={`text-[10px] font-mono ${trend.startsWith('+') ? 'text-aethelgard-green' : 'text-white/20'}`}>
                    {trend}
                </span>
            </div>
        </GlassPanel>
    );
}

export default App;
