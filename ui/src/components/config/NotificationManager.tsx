import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, MessageCircle, Mail, Send, CheckCircle, Shield, AlertTriangle, Info } from 'lucide-react';
import { TelegramSetup } from './TelegramSetup';

type Provider = 'telegram' | 'whatsapp' | 'email';

export function NotificationManager() {
    const [activeProvider, setActiveProvider] = useState<Provider>('telegram');
    const [settings, setSettings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchAllSettings = async () => {
        try {
            const response = await fetch('/api/notifications/settings');
            if (response.ok) {
                const data = await response.json();
                setSettings(data.settings || []);
            }
        } catch (err) {
            console.error('Error fetching notification settings:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAllSettings();
    }, []);

    const isProviderEnabled = (providerName: string) => {
        return settings.find(s => s.provider === providerName)?.enabled;
    };

    return (
        <div className="space-y-6">
            <header className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-aethelgard-blue/20 rounded-lg text-aethelgard-blue">
                        <Bell size={24} />
                    </div>
                    <div>
                        <h3 className="text-2xl font-outfit font-bold text-white/90">Notification Manager</h3>
                        <p className="text-sm text-white/40">Configure your preferred alert channels</p>
                    </div>
                </div>
            </header>

            {/* Provider Selector Tabs */}
            <div className="flex gap-2 p-1 bg-white/5 rounded-xl border border-white/5">
                <TabButton
                    active={activeProvider === 'telegram'}
                    onClick={() => setActiveProvider('telegram')}
                    icon={<Send size={16} />}
                    label="Telegram"
                    enabled={isProviderEnabled('telegram')}
                />
                <TabButton
                    active={activeProvider === 'whatsapp'}
                    onClick={() => setActiveProvider('whatsapp')}
                    icon={<MessageCircle size={16} />}
                    label="WhatsApp"
                    enabled={isProviderEnabled('whatsapp')}
                    badge="Coming Soon"
                />
                <TabButton
                    active={activeProvider === 'email'}
                    onClick={() => setActiveProvider('email')}
                    icon={<Mail size={16} />}
                    label="Email"
                    enabled={isProviderEnabled('email')}
                    badge="Coming Soon"
                />
            </div>

            <div className="mt-8">
                <AnimatePresence mode="wait">
                    {activeProvider === 'telegram' && (
                        <motion.div
                            key="telegram"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                        >
                            <TelegramSetup />
                        </motion.div>
                    )}

                    {activeProvider === 'whatsapp' && (
                        <motion.div
                            key="whatsapp"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            className="space-y-6"
                        >
                            <div className="p-8 rounded-2xl bg-white/2 border border-white/5 flex flex-col items-center justify-center text-center gap-4">
                                <div className="p-4 bg-aethelgard-green/10 rounded-full text-aethelgard-green">
                                    <MessageCircle size={48} />
                                </div>
                                <h4 className="text-xl font-bold text-white/90">Integración con WhatsApp (Twilio)</h4>
                                <p className="text-sm text-white/40 max-w-md">
                                    Próximamente podrás recibir alertas directamente en tu WhatsApp utilizando la API de Twilio.
                                </p>
                                <div className="mt-4 px-4 py-2 bg-aethelgard-blue/10 border border-aethelgard-blue/20 rounded-lg flex items-center gap-2">
                                    <Info size={16} className="text-aethelgard-blue" />
                                    <span className="text-xs font-bold text-aethelgard-blue uppercase tracking-widest">En Desarrollo</span>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {activeProvider === 'email' && (
                        <motion.div
                            key="email"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            className="space-y-6"
                        >
                            <div className="p-8 rounded-2xl bg-white/2 border border-white/5 flex flex-col items-center justify-center text-center gap-4">
                                <div className="p-4 bg-aethelgard-blue/10 rounded-full text-aethelgard-blue">
                                    <Mail size={48} />
                                </div>
                                <h4 className="text-xl font-bold text-white/90">Alertas vía Email (SMTP)</h4>
                                <p className="text-sm text-white/40 max-w-md">
                                    Configura tu servidor SMTP para recibir reportes diarios y alertas críticas en tu bandeja de entrada.
                                </p>
                                <div className="mt-4 px-4 py-2 bg-aethelgard-blue/10 border border-aethelgard-blue/20 rounded-lg flex items-center gap-2">
                                    <Info size={16} className="text-aethelgard-blue" />
                                    <span className="text-xs font-bold text-aethelgard-blue uppercase tracking-widest">En Desarrollo</span>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

function TabButton({ active, onClick, icon, label, enabled, badge }: any) {
    return (
        <button
            onClick={onClick}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg transition-all relative ${active
                ? 'bg-aethelgard-blue text-white shadow-lg shadow-aethelgard-blue/20'
                : 'text-white/40 hover:bg-white/5 hover:text-white/60'
                }`}
        >
            {icon}
            <span className="text-sm font-bold font-outfit">{label}</span>
            {enabled && !active && (
                <div className="absolute top-1 right-1 w-2 h-2 bg-aethelgard-green rounded-full shadow-sm" />
            )}
            {badge && (
                <span className={`absolute -top-2 -right-1 px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-tighter ${active ? 'bg-white text-aethelgard-blue' : 'bg-white/10 text-white/40'
                    }`}>
                    {badge}
                </span>
            )}
        </button>
    );
}
