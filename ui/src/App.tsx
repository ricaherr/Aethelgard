import { useState, useEffect } from 'react';
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

// New Core Layout & Auth
import { AuthProvider } from './contexts/AuthContext';
import { AethelgardProvider } from './contexts/AethelgardContext';
import { AuthGuard } from './components/auth/AuthGuard';
import { MainLayout } from './components/layout/MainLayout';

function App() {
    return (
        <AuthProvider>
            <AethelgardProvider>
                <AuthGuard>
                    <AuthenticatedView />
                </AuthGuard>
            </AethelgardProvider>
        </AuthProvider>
    );
}

function AuthenticatedView() {
    const [activeTab, setActiveTab] = useState('trader');
    const [isDiagOpen, setIsDiagOpen] = useState(false);

    // Real-time data from Cerebro Brain - Only starts when this component mounts
    const { regime, signals, thoughts, status, metrics, riskStatus, modulesStatus, sendCommand, runAudit, runRepair } = useAethelgard();

    return (
        <MainLayout activeTab={activeTab} setActiveTab={setActiveTab}>
            <AnimatePresence mode="wait">
                {activeTab === 'trader' && (
                    <motion.div
                        key="trader-view"
                        initial={{ opacity: 0, scale: 0.99 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 1.01 }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                                    trend={riskStatus?.current_risk_pct !== undefined ? `${riskStatus.current_risk_pct.toFixed(2)}%` : 'Safe'}
                                />
                            </div>

                            {/* Main Opportunity Stream */}
                            <AlphaSignals signals={signals} modulesStatus={modulesStatus} />
                        </div>
                    </motion.div>
                )}
                {activeTab === 'analysis' && (
                    <motion.div
                        key="analysis-view"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                        transition={{ duration: 0.3, ease: 'easeOut' }}
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
                        transition={{ duration: 0.3, ease: 'easeOut' }}
                        className="h-full"
                    >
                        <MonitorPage status={status} thoughts={thoughts} runAudit={runAudit} runRepair={runRepair} />
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Diagnostic Drawer Overlay */}
            <DiagnosticDrawer
                isOpen={isDiagOpen}
                onClose={() => setIsDiagOpen(false)}
                status={status}
            />
        </MainLayout>
    );
}

function StatBadge({ label, value, trend }: { label: string, value: string, trend: string }) {
    return (
        <GlassPanel className="p-4 flex flex-col justify-center gap-1 border-white/5 hover:border-aethelgard-cyan/20 transition-colors">
            <span className="text-[10px] text-white/30 uppercase tracking-widest font-bold">{label}</span>
            <div className="flex items-baseline gap-2">
                <span className="text-xl font-outfit font-bold text-white/80">{value}</span>
                <span className={`text-[10px] font-mono ${trend.startsWith('+') ? 'text-aethelgard-cyan' : 'text-white/20'}`}>
                    {trend}
                </span>
            </div>
        </GlassPanel>
    );
}

export default App;
