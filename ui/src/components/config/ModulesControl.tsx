import { useState, useEffect, useCallback } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { Shield, Power, Loader2, CheckCircle, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';
import { useApi } from '../../hooks/useApi';

interface ModulesStatus {
    modules: {
        scanner: boolean;
        executor: boolean;
        position_manager: boolean;
        risk_manager: boolean;
        monitor: boolean;
        notificator: boolean;
    };
    timestamp: string;
}

const MODULE_DESCRIPTIONS = {
    scanner: 'ScannerEngine - Autonomous multi-timeframe signal discovery',
    executor: 'Executor - Automated trade execution and position management',
    position_manager: 'TradeClosureListener - Real-time position tracking and lifecycle',
    risk_manager: 'RiskManager - Critical protection system (cannot disable)',
    monitor: 'EdgeMonitor - Performance tracking and statistics logging',
    notificator: 'Notificator - Telegram notifications and alerts'
};

const MODULE_ICONS = {
    scanner: '🔍',
    executor: '⚡',
    position_manager: '📊',
    risk_manager: '🛡️',
    monitor: '📈',
    notificator: '📢'
};

interface ModulesControlProps {
    data?: any;
    onRefresh: () => void;
}

export function ModulesControl({ data, onRefresh }: ModulesControlProps) {
    const { apiFetch } = useApi();
    const [modules, setModules] = useState<ModulesStatus | null>(null);
    const [toggling, setToggling] = useState<string | null>(null);
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    useEffect(() => {
        if (data) {
            setModules(data);
        }
    }, [data]);

    const toggleModule = async (moduleName: string, currentState: boolean) => {
        // Risk manager cannot be disabled
        if (moduleName === 'risk_manager' && currentState) {
            setMessage({ type: 'error', text: 'Risk Manager cannot be disabled for safety' });
            setTimeout(() => setMessage(null), 3000);
            return;
        }

        setToggling(moduleName);
        try {
            const res = await apiFetch('/api/modules/toggle', {
                method: 'POST',
                body: JSON.stringify({
                    module: moduleName,
                    enabled: !currentState
                })
            });

            const data = await res.json();

            if (res.ok) {
                setMessage({ type: 'success', text: data.message });
                onRefresh(); // Refresh via parent Hub
            } else {
                setMessage({ type: 'error', text: data.detail || 'Failed to toggle module' });
            }
        } catch (error) {
            setMessage({ type: 'error', text: 'Network error' });
        } finally {
            setToggling(null);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Power size={24} className="text-aethelgard-blue" />
                    <div>
                        <h2 className="text-xl font-outfit font-bold text-white/90">System Modules</h2>
                        <p className="text-white/50 text-xs uppercase tracking-[0.2em] mt-1">
                            Enable/disable trading system components
                        </p>
                    </div>
                </div>

                {modules && (
                    <div className="text-xs text-white/40">
                        Last updated: {new Date(modules.timestamp).toLocaleTimeString()}
                    </div>
                )}
            </div>

            {/* Message Banner */}
            {message && (
                <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className={`p-4 rounded-lg border flex items-center gap-2 ${message.type === 'success'
                        ? 'bg-green-500/10 border-green-500/20 text-green-300'
                        : 'bg-red-500/10 border-red-500/20 text-red-300'
                        }`}
                >
                    {message.type === 'success' ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
                    <span className="text-sm">{message.text}</span>
                </motion.div>
            )}

            {/* Modules Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {modules?.modules && Object.entries(modules.modules).map(([moduleName, enabled]) => (
                    <ModuleCard
                        key={moduleName}
                        name={moduleName}
                        enabled={enabled}
                        toggling={toggling === moduleName}
                        onToggle={() => toggleModule(moduleName, enabled)}
                    />
                ))}
            </div>

            {/* Safety Notice */}
            <GlassPanel className="border-orange-500/20 bg-orange-500/5">
                <div className="flex items-start gap-3">
                    <Shield size={20} className="text-orange-400 flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-orange-200/80 space-y-1">
                        <p className="font-bold">Safety Notice:</p>
                        <p>Risk Manager is permanently enabled and cannot be disabled. This protects against excessive drawdown and lockdown violations.</p>
                        <p className="text-orange-300/60 mt-2">Disabling Executor will prevent new trades but won't close existing positions. Position Manager tracks open trades.</p>
                    </div>
                </div>
            </GlassPanel>
        </div>
    );
}

interface ModuleCardProps {
    name: string;
    enabled: boolean;
    toggling: boolean;
    onToggle: () => void;
}

function ModuleCard({ name, enabled, toggling, onToggle }: ModuleCardProps) {
    const isRiskManager = name === 'risk_manager';
    const description = MODULE_DESCRIPTIONS[name as keyof typeof MODULE_DESCRIPTIONS];
    const icon = MODULE_ICONS[name as keyof typeof MODULE_ICONS];

    return (
        <GlassPanel className={`border-white/10 ${enabled ? 'bg-green-500/5 border-green-500/20' : 'bg-white/[0.02]'}`}>
            <div className="flex items-center justify-between">
                {/* Module Info */}
                <div className="flex items-center gap-3 flex-1">
                    <div className="text-2xl">{icon}</div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2">
                            <h3 className="font-outfit font-bold text-white/90 capitalize">
                                {name.replace('_', ' ')}
                            </h3>
                            {enabled && <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />}
                        </div>
                        <p className="text-[10px] text-white/50 mt-1 leading-relaxed">
                            {description}
                        </p>
                    </div>
                </div>

                {/* Toggle Switch */}
                <button
                    onClick={onToggle}
                    disabled={toggling || (isRiskManager && enabled)}
                    className={`
                        relative w-14 h-7 rounded-full transition-all duration-300 flex-shrink-0
                        ${enabled ? 'bg-green-500' : 'bg-white/10'}
                        ${isRiskManager && enabled ? 'opacity-50 cursor-not-allowed' : 'hover:opacity-80'}
                        ${toggling ? 'cursor-wait opacity-50' : ''}
                    `}
                >
                    <motion.div
                        className="absolute top-1 w-5 h-5 bg-white rounded-full shadow-lg flex items-center justify-center"
                        animate={{ left: enabled ? '30px' : '4px' }}
                        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                    >
                        {toggling && <Loader2 size={12} className="animate-spin text-gray-600" />}
                    </motion.div>
                </button>
            </div>
        </GlassPanel>
    );
}
