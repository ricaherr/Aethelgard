import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Save, RefreshCw, AlertTriangle, Shield, Sliders, Settings, Bell } from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { TelegramSetup } from './TelegramSetup';

type ConfigCategory = 'trading' | 'risk' | 'system' | 'notifications';

export function ConfigHub() {
    const [activeCategory, setActiveCategory] = useState<ConfigCategory>('trading');
    const [config, setConfig] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const fetchConfig = async (category: ConfigCategory) => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`/api/config/${category}`);
            if (!response.ok) throw new Error(`Error ${response.status}: ${category} config not found.`);
            const data = await response.json();
            setConfig(data.data);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (!config) return;
        setSaving(true);
        setError(null);
        setMessage(null);
        try {
            const response = await fetch(`/api/config/${activeCategory}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            if (!response.ok) throw new Error('Failed to save configuration.');

            setMessage(`✅ ${activeCategory.toUpperCase()} configuration saved to DB.`);
            setTimeout(() => setMessage(null), 3000);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => {
        fetchConfig(activeCategory);
    }, [activeCategory]);

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
                    <button
                        onClick={handleSave}
                        disabled={saving || loading || !config}
                        className={`flex items-center gap-2 px-6 py-3 rounded-xl font-bold font-outfit transition-all shadow-lg ${saving ? 'bg-white/20 text-white/40 cursor-not-allowed' : 'bg-aethelgard-green text-dark hover:scale-105 active:scale-95 shadow-aethelgard-green/20'
                            }`}
                    >
                        <Save size={18} />
                        {saving ? 'Saving...' : 'Commit Changes'}
                    </button>
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
                        active={activeCategory === 'notifications'}
                        onClick={() => setActiveCategory('notifications')}
                        icon={<Bell size={20} />}
                        title="Telegram Alerts"
                        description="Auto-Setup & Testing"
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

                                {/* Special case: Telegram/Notifications */}
                                {!loading && activeCategory === 'notifications' && (
                                    <TelegramSetup />
                                )}

                                {!loading && config && activeCategory !== 'notifications' && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
                                        {Object.entries(config).map(([key, value]) => {
                                            if (key.startsWith('_')) return null; // Skip comments
                                            if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                                                // Handle one level of nesting (e.g. confluence.weights)
                                                return (
                                                    <div key={key} className="col-span-full border-t border-white/5 pt-6 mt-4">
                                                        <h4 className="text-aethelgard-blue text-[10px] font-bold uppercase tracking-[0.3em] mb-4">{key} Cluster</h4>
                                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                                            {Object.entries(value).map(([subKey, subValue]) => (
                                                                <ConfigInput
                                                                    key={`${key}.${subKey}`}
                                                                    label={subKey}
                                                                    value={subValue}
                                                                    onChange={(v) => handleInputChange(`${key}.${subKey}`, v)}
                                                                />
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            }
                                            return (
                                                <ConfigInput
                                                    key={key}
                                                    label={key}
                                                    value={value}
                                                    onChange={(v) => handleInputChange(key, v)}
                                                />
                                            );
                                        })}
                                    </div>
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
