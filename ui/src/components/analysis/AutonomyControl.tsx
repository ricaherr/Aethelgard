import React, { useState, useEffect, useCallback } from 'react';
import { Power, Shield, AlertTriangle, Settings } from 'lucide-react';
import { useApi } from '../../hooks/useApi';

interface AutonomyControlProps {
    onConfigChange?: (config: any) => void;
}

export const AutonomyControl: React.FC<AutonomyControlProps> = ({ onConfigChange }) => {
    const { apiFetch } = useApi();
    const [autoTradingEnabled, setAutoTradingEnabled] = useState(false);
    const [maxRisk, setMaxRisk] = useState(1.0);
    const [maxDailyTrades, setMaxDailyTrades] = useState(10);
    const [requireConfirmation, setRequireConfirmation] = useState(true);
    const [loading, setLoading] = useState(true);

    const fetchPreferences = useCallback(async () => {
        try {
            const response = await apiFetch('/api/user/preferences?user_id=default');
            if (response.ok) {
                const prefs = await response.json();
                setAutoTradingEnabled(prefs.auto_trading_enabled || false);
                setMaxRisk(prefs.auto_trading_max_risk || 1.0);
                setMaxDailyTrades(prefs.max_daily_trades || 10);
                setRequireConfirmation(prefs.require_confirmation !== false);
            }
        } catch (error) {
            console.error('Error fetching preferences:', error);
        } finally {
            setLoading(false);
        }
    }, [apiFetch]);

    useEffect(() => {
        fetchPreferences();
    }, [fetchPreferences]);

    const toggleAutoTrading = async () => {
        const newValue = !autoTradingEnabled;

        try {
            const response = await apiFetch('/api/auto-trading/toggle', {
                method: 'POST',
                body: JSON.stringify({
                    user_id: 'default',
                    enabled: newValue
                })
            });

            if (response.ok) {
                setAutoTradingEnabled(newValue);
                onConfigChange?.({ auto_trading_enabled: newValue });
            }
        } catch (error) {
            console.error('Error toggling auto-trading:', error);
        }
    };

    const updatePreference = async (key: string, value: any) => {
        try {
            await apiFetch('/api/user/preferences', {
                method: 'POST',
                body: JSON.stringify({
                    user_id: 'default',
                    [key]: value
                })
            });
            onConfigChange?.({ [key]: value });
        } catch (error) {
            console.error('Error updating preference:', error);
        }
    };

    if (loading) {
        return (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-gray-400">Cargando configuración...</div>
            </div>
        );
    }

    return (
        <div className="bg-gray-800 rounded-lg border border-gray-700">
            <div className="p-4 border-b border-gray-700">
                <div className="flex items-center gap-2">
                    <Settings className="w-5 h-5 text-purple-400" />
                    <h3 className="font-semibold text-white">Control de Autonomía</h3>
                </div>
            </div>

            <div className="p-4 space-y-4">
                {/* Auto-Trading Toggle */}
                <div className="flex items-center justify-between p-4 bg-gray-750 rounded-lg">
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${autoTradingEnabled ? 'bg-green-600' : 'bg-gray-700'}`}>
                            <Power className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <div className="font-medium text-white">Auto-Trading</div>
                            <div className="text-xs text-gray-400">
                                {autoTradingEnabled ? 'Sistema ejecutando automáticamente' : 'Ejecución manual requerida'}
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={toggleAutoTrading}
                        className={`relative w-14 h-7 rounded-full transition-colors ${autoTradingEnabled ? 'bg-green-600' : 'bg-gray-600'
                            }`}
                    >
                        <div
                            className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition-transform ${autoTradingEnabled ? 'translate-x-7' : 'translate-x-0'
                                }`}
                        />
                    </button>
                </div>

                {/* Risk Limit */}
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
                            <Shield className="w-4 h-4 text-blue-400" />
                            Riesgo Máximo por Trade
                        </label>
                        <span className="text-sm font-semibold text-white">{maxRisk}%</span>
                    </div>
                    <input
                        type="range"
                        min="0.5"
                        max="3"
                        step="0.1"
                        value={maxRisk}
                        onChange={(e) => {
                            const value = parseFloat(e.target.value);
                            setMaxRisk(value);
                            updatePreference('auto_trading_max_risk', value);
                        }}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                    <div className="flex justify-between text-xs text-gray-500">
                        <span>0.5%</span>
                        <span>3%</span>
                    </div>
                </div>

                {/* Max Daily Trades */}
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-yellow-400" />
                            Límite Diario de Trades
                        </label>
                        <span className="text-sm font-semibold text-white">{maxDailyTrades}</span>
                    </div>
                    <input
                        type="range"
                        min="1"
                        max="50"
                        step="1"
                        value={maxDailyTrades}
                        onChange={(e) => {
                            const value = parseInt(e.target.value);
                            setMaxDailyTrades(value);
                            updatePreference('max_daily_trades', value);
                        }}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-yellow-600"
                    />
                    <div className="flex justify-between text-xs text-gray-500">
                        <span>1</span>
                        <span>50</span>
                    </div>
                </div>

                {/* Require Confirmation */}
                <div className="flex items-center justify-between p-3 bg-gray-750 rounded-lg">
                    <div className="text-sm text-gray-300">
                        Requerir confirmación para acciones críticas
                    </div>
                    <button
                        onClick={() => {
                            const newValue = !requireConfirmation;
                            setRequireConfirmation(newValue);
                            updatePreference('require_confirmation', newValue);
                        }}
                        className={`relative w-12 h-6 rounded-full transition-colors ${requireConfirmation ? 'bg-blue-600' : 'bg-gray-600'
                            }`}
                    >
                        <div
                            className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${requireConfirmation ? 'translate-x-6' : 'translate-x-0'
                                }`}
                        />
                    </button>
                </div>

                {/* Warning */}
                {autoTradingEnabled && (
                    <div className="flex items-start gap-2 p-3 bg-yellow-900/20 border border-yellow-600/30 rounded-lg">
                        <AlertTriangle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                        <div className="text-xs text-yellow-200">
                            <strong>Auto-trading activo:</strong> El sistema ejecutará trades automáticamente según las señales detectadas y los límites configurados.
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
