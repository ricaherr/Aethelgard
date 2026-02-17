import React, { useState, useEffect } from 'react';
import { Power, RefreshCw, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';

export function AutoTradingControl() {
    const [autoTradingEnabled, setAutoTradingEnabled] = useState(false);
    const [loading, setLoading] = useState(true);
    const [toggling, setToggling] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchStatus = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/user/preferences');
            if (!response.ok) throw new Error('Failed to fetch preferences');
            const data = await response.json();
            setAutoTradingEnabled(data.preferences?.auto_trading_enabled === 1);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const toggleAutoTrading = async () => {
        setToggling(true);
        setError(null);
        try {
            const newState = !autoTradingEnabled;
            const response = await fetch('/api/auto-trading/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: 'default',
                    enabled: newState
                })
            });

            if (!response.ok) throw new Error('Failed to toggle auto-trading');

            const data = await response.json();
            setAutoTradingEnabled(data.auto_trading_enabled);

            // Refresh status to ensure UI is in sync
            await fetchStatus();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setToggling(false);
        }
    };

    useEffect(() => {
        fetchStatus();
    }, []);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between p-6 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-lg ${autoTradingEnabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        <Power size={24} />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-white">Auto-Trading</h3>
                        <p className="text-xs text-white/40 font-mono">
                            {autoTradingEnabled
                                ? 'System will execute signals automatically (>70% probability)'
                                : 'Manual execution only - signals will not auto-execute'}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={fetchStatus}
                        disabled={loading}
                        className="p-2 rounded-lg bg-white/5 border border-white/10 text-white/40 hover:text-white/80 hover:bg-white/10 transition-all disabled:opacity-50"
                        title="Refresh status"
                    >
                        <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
                    </button>

                    <button
                        onClick={toggleAutoTrading}
                        disabled={toggling || loading}
                        className={`relative w-16 h-8 rounded-full transition-all ${autoTradingEnabled ? 'bg-green-500' : 'bg-red-500/50'
                            } ${toggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                    >
                        <motion.div
                            animate={{ x: autoTradingEnabled ? 32 : 0 }}
                            className="absolute top-1 left-1 w-6 h-6 bg-white rounded-full shadow-md"
                        />
                    </button>
                </div>
            </div>

            {error && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex gap-3">
                    <AlertCircle size={16} className="shrink-0 mt-0.5" />
                    <span>{error}</span>
                </div>
            )}

            <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs">
                <p className="font-bold mb-2">ℹ️ Important Notes:</p>
                <ul className="space-y-1 list-disc list-inside text-white/60">
                    <li>Manual execution via "Execute" button works regardless of this setting</li>
                    <li>Auto-trading only applies to signals with probability &gt; 70%</li>
                    <li>Risk limits and lockdown mode still apply even when enabled</li>
                </ul>
            </div>
        </div>
    );
}
