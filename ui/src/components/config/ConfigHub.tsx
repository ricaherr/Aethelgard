import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Save, RefreshCw, AlertTriangle, Shield, Sliders, Settings, Bell, Power, Server } from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { NotificationManager } from './NotificationManager';
import { ModulesControl } from './ModulesControl';
import { AutoTradingControl } from './AutoTradingControl';
import { InstrumentsEditor } from './InstrumentsEditor';
import { BackupSettings } from './BackupSettings';
import { ConnectivityHub } from './ConnectivityHub';
import { useApi } from '../../hooks/useApi';

type ConfigCategory = 'trading' | 'risk' | 'system' | 'notifications' | 'modules' | 'instruments' | 'backups' | 'connectivity';

const CATEGORY_ENDPOINTS: Record<string, string> = {
    'trading': '/api/config/trading',
    'risk': '/api/config/risk',
    'system': '/api/config/system',
    'notifications': '/api/notifications/settings',
    'backups': '/api/backup/settings',
    'instruments': '/api/instruments?all=true',
    'modules': '/api/modules/status'
};

export function ConfigHub() {
    const { apiFetch } = useApi();
    const [activeCategory, setActiveCategory] = useState<ConfigCategory>('trading');
    const [config, setConfig] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [retryCount, setRetryCount] = useState(0);

    const isSpecialCategory = ['notifications', 'modules', 'instruments', 'backups', 'connectivity'].includes(activeCategory);
    const usesGenericSave = !isSpecialCategory;

    const fetchConfig = useCallback(async (category: ConfigCategory, isRetry = false) => {
        const endpoint = CATEGORY_ENDPOINTS[category as string];
        if (!endpoint) {
            if (category === 'connectivity') {
                setLoading(false);
                setConfig(null);
            }
            return;
        }

        if (!isRetry) {
            setLoading(true);
            setError(null);
            setRetryCount(0);
        }

        try {
            const response = await apiFetch(endpoint);
            if (response.ok) {
                const data = await response.json();

                // Normalización de datos por categoría
                if (category === 'notifications' || category === 'backups') {
                    setConfig(data.settings || {});
                } else if (category === 'modules') {
                    setConfig(data);
                } else if (category === 'instruments') {
                    setConfig(data.markets || {});
                } else {
                    setConfig(data.data || {});
                }

                setLoading(false);
                setRetryCount(0);
            } else {
                throw new Error(`Error ${response.status}: Failed to load ${category}`);
            }
        } catch (err: any) {
            console.warn(`[ConfigHub] Fetch for ${category} failed:`, err);
            if (retryCount < 10) {
                const nextRetry = retryCount + 1;
                setRetryCount(nextRetry);
                const delay = nextRetry <= 3 ? 20000 : 60000;
                setError(`Reintentando ${category}... (${nextRetry}/10)`);
                setTimeout(() => fetchConfig(category, true), delay);
            } else {
                setError(`Falla crítica en '${category}'. Ingrese a modo manual.`);
                setLoading(false);
            }
        }
    }, [apiFetch, retryCount]);

    const handleSave = async () => {
        if (!config && activeCategory !== 'connectivity') return;
        setSaving(true);
        setError(null);
        setMessage(null);
        try {
            let endpoint = `/api/config/${activeCategory}`;
            let body = config;

            if (activeCategory === 'backups') {
                endpoint = '/api/backup/settings';
            } else if (activeCategory === 'notifications') {
                // Notificaciones se guardan por proveedor usualmente, pero aquí guardamos la base
                endpoint = '/api/config/notifications';
            }

            const response = await apiFetch(endpoint, {
                method: 'POST',
                body: JSON.stringify(body)
            });

            if (!response.ok) throw new Error('Falló el guardado en el Data Vault.');

            setMessage(`✅ ${activeCategory.toUpperCase()} sincronizado correctamente.`);
            setTimeout(() => setMessage(null), 3000);
            await fetchConfig(activeCategory);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => {
        fetchConfig(activeCategory);
    }, [fetchConfig, activeCategory]);

    const handleInputChange = (key: string, value: any) => {
        setConfig((prev: any) => {
            const keys = key.split('.');
            if (keys.length === 1) return { ...prev, [key]: value };

            // Handle nested objects (like confluence.weights)
            const newConfig = { ...prev };
            let current = newConfig;
            for (let i = 0; i < keys.length - 1; i++) {
                current[keys[i]] = { ...current[keys[i]] };
                current = current[keys[i]];
            }
            current[keys[keys.length - 1]] = value;
            return newConfig;
        });
    };

    return (
        <div className="flex flex-col h-full gap-6">
            <header className="flex justify-between items-center mb-2">
                <div>
                    <h2 className="text-3xl font-outfit font-bold tracking-tight text-white/90">Configuration Hub</h2>
                    <p className="text-sm text-white/40 font-mono">Control Center / DB-First Persistence</p>
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={() => fetchConfig(activeCategory)}
                        className="p-3 rounded-xl bg-white/5 border border-white/5 text-white/40 hover:text-white/80 hover:bg-white/10 transition-all"
                        title="Reload from DB"
                    >
                        <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
                    </button>
                    {usesGenericSave && (
                        <button
                            onClick={handleSave}
                            disabled={saving || loading || !config}
                            className={`flex items-center gap-2 px-6 py-3 rounded-xl font-bold font-outfit transition-all shadow-lg ${saving ? 'bg-white/20 text-white/40 cursor-not-allowed' : 'bg-aethelgard-green text-dark hover:scale-105 active:scale-95 shadow-aethelgard-green/20'
                                }`}
                        >
                            <Save size={18} />
                            {saving ? 'Saving...' : 'Commit Changes'}
                        </button>
                    )}
                </div>
            </header>

            <div className="grid grid-cols-12 gap-8 flex-1">
                {/* Side Selector */}
                <div className="col-span-12 lg:col-span-3 space-y-4">
                    <TabButton
                        active={activeCategory === 'trading'}
                        onClick={() => setActiveCategory('trading')}
                        icon={<Sliders size={20} />}
                        title="Trading Strategy"
                        description="ADX, Elephant & SMAs"
                    />
                    <TabButton
                        active={activeCategory === 'risk'}
                        onClick={() => setActiveCategory('risk')}
                        icon={<Shield size={20} />}
                        title="Risk Shield"
                        description="Limits & Lockdown"
                    />
                    <TabButton
                        active={activeCategory === 'system'}
                        onClick={() => setActiveCategory('system')}
                        icon={<Settings size={20} />}
                        title="System Core"
                        description="Paths & CPU Scalability"
                    />
                    <TabButton
                        active={activeCategory === 'instruments'}
                        onClick={() => setActiveCategory('instruments')}
                        icon={<Sliders size={20} />}
                        title="Instruments"
                        description="Gestión de instrumentos"
                    />
                    <TabButton
                        active={activeCategory === 'backups'}
                        onClick={() => setActiveCategory('backups')}
                        icon={<Shield size={20} />}
                        title="Backups"
                        description="DB recovery policy"
                    />
                    <TabButton
                        active={activeCategory === 'notifications'}
                        onClick={() => setActiveCategory('notifications')}
                        icon={<Bell size={20} />}
                        title="Notification Hub"
                        description="Multi-Channel Alerts"
                    />
                    <TabButton
                        active={activeCategory === 'modules'}
                        onClick={() => setActiveCategory('modules')}
                        icon={<Power size={20} />}
                        title="System Modules"
                        description="Feature Toggles"
                    />
                    <TabButton
                        active={activeCategory === 'connectivity'}
                        onClick={() => setActiveCategory('connectivity')}
                        icon={<Server size={20} />}
                        title="Connectivity Hub"
                        description="Satellite management"
                    />

                    {error && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex gap-3 animate-pulse">
                            <AlertTriangle size={16} className="shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}

                    {message && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="p-4 rounded-xl bg-aethelgard-green/10 border border-aethelgard-green/20 text-aethelgard-green text-xs font-bold"
                        >
                            {message}
                        </motion.div>
                    )}
                </div>

                {/* Main Viewport */}
                <div className="col-span-12 lg:col-span-9">
                    <GlassPanel premium className="h-full min-h-[500px] flex flex-col p-8 overflow-y-auto">
                        <AnimatePresence mode="wait">
                            <motion.div
                                key={activeCategory}
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                className="space-y-8"
                            >
                                {loading && (
                                    <div className="flex flex-col items-center justify-center h-64 text-white/20 gap-4">
                                        <RefreshCw size={48} className="animate-spin" />
                                        <p className="text-sm font-mono uppercase tracking-widest">Accessing Data Vault...</p>
                                    </div>
                                )}

                                {/* Special case: Notification Manager */}
                                {!loading && activeCategory === 'notifications' && (
                                    <NotificationManager config={config} onRefresh={() => fetchConfig('notifications')} />
                                )}

                                {/* Special case: System Modules */}
                                {!loading && activeCategory === 'modules' && (
                                    <ModulesControl data={config} onRefresh={() => fetchConfig('modules')} />
                                )}

                                {/* Special case: Instruments Editor */}
                                {!loading && activeCategory === 'instruments' && (
                                    <InstrumentsEditor data={config} onRefresh={() => fetchConfig('instruments')} />
                                )}

                                {/* Special case: Backup Settings */}
                                {!loading && activeCategory === 'backups' && (
                                    <BackupSettings config={config} onRefresh={() => fetchConfig('backups')} />
                                )}

                                {/* Special case: Connectivity Hub */}
                                {!loading && activeCategory === 'connectivity' && (
                                    <ConnectivityHub />
                                )}

                                {!loading && config && !['notifications', 'modules', 'instruments', 'backups', 'connectivity'].includes(activeCategory) && (
                                    <>
                                        {/* Auto-Trading Control (only in trading category) */}
                                        {activeCategory === 'trading' && (
                                            <div className="mb-8">
                                                <AutoTradingControl />
                                            </div>
                                        )}

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
                                            {(() => {
                                                const renderRecursive = (data: any, path: string = '') => {
                                                    return Object.entries(data).map(([key, value]) => {
                                                        if (key.startsWith('_')) return null; // Skip comments/metadata
                                                        const fullKey = path ? `${path}.${key}` : key;

                                                        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                                                            // Cluster for nested objects
                                                            return (
                                                                <div key={fullKey} className="col-span-full border-t border-white/5 pt-6 mt-4">
                                                                    <div className="flex items-center gap-3 mb-4">
                                                                        <div className="h-[1px] flex-1 bg-white/5"></div>
                                                                        <h4 className="text-aethelgard-blue text-[10px] font-bold uppercase tracking-[0.3em] whitespace-nowrap">
                                                                            {key.replace(/_/g, ' ')} Cluster
                                                                        </h4>
                                                                        <div className="h-[1px] flex-1 bg-white/5"></div>
                                                                    </div>
                                                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 px-4">
                                                                        {renderRecursive(value, fullKey)}
                                                                    </div>
                                                                </div>
                                                            );
                                                        }

                                                        return (
                                                            <ConfigInput
                                                                key={fullKey}
                                                                label={key}
                                                                value={value}
                                                                onChange={(v) => handleInputChange(fullKey, v)}
                                                            />
                                                        );
                                                    });
                                                };
                                                return renderRecursive(config);
                                            })()}
                                        </div>
                                    </>
                                )}
                            </motion.div>
                        </AnimatePresence>
                    </GlassPanel>
                </div>
            </div>
        </div>
    );
}

function TabButton({ active, onClick, icon, title, description }: any) {
    return (
        <button
            onClick={onClick}
            className={`w-full p-4 rounded-xl border flex items-center gap-4 text-left transition-all ${active
                ? 'bg-aethelgard-blue/10 border-aethelgard-blue/30 text-white shadow-lg shadow-aethelgard-blue/10'
                : 'bg-white/2 label-transparent border-white/5 text-white/40 hover:bg-white/5'
                }`}
        >
            <div className={`p-2 rounded-lg ${active ? 'bg-aethelgard-blue/20 text-aethelgard-blue' : 'bg-white/5'}`}>
                {icon}
            </div>
            <div>
                <p className="font-bold text-sm">{title}</p>
                <p className="text-[10px] opacity-60 uppercase tracking-widest leading-none mt-1">{description}</p>
            </div>
        </button>
    );
}

function ConfigInput({ label, value, onChange }: { label: string, value: any, onChange: (v: any) => void }) {
    const isNumber = typeof value === 'number';
    const isBoolean = typeof value === 'boolean';

    // Clean label (replace underscores with spaces)
    const cleanLabel = label.replace(/_/g, ' ');

    return (
        <div className="flex flex-col gap-2 group">
            <label className="text-[10px] font-bold text-white/30 uppercase tracking-[0.2em] group-hover:text-white/60 transition-colors uppercase">
                {cleanLabel}
            </label>

            {isBoolean ? (
                <div
                    onClick={() => onChange(!value)}
                    className={`w-12 h-6 rounded-full p-1 cursor-pointer transition-colors ${value ? 'bg-aethelgard-green' : 'bg-white/10'}`}
                >
                    <motion.div
                        animate={{ x: value ? 24 : 0 }}
                        className="w-4 h-4 bg-white rounded-full shadow-md"
                    />
                </div>
            ) : (
                <input
                    type={isNumber ? "number" : "text"}
                    step={isNumber ? "any" : undefined}
                    value={value ?? ''}
                    onChange={(e) => onChange(isNumber ? parseFloat(e.target.value) : e.target.value)}
                    className="bg-white/5 border border-white/5 rounded-lg px-3 py-2 text-sm font-mono text-white/70 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none transition-all focus:shadow-[0_0_15px_rgba(0,186,255,0.05)]"
                />
            )}
        </div>
    );
}
