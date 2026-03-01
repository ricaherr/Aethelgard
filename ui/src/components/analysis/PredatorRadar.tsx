import React, { useCallback, useEffect, useState } from 'react';
import { Radar, AlertTriangle, Eye } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import InfoTooltip from './InfoTooltip';

interface PredatorRadarProps {
    symbol?: string;
    timeframe?: string;
}

interface PredatorSnapshot {
    symbol: string;
    anchor: string | null;
    timeframe: string;
    state: 'DORMANT' | 'TRACKING' | 'PREDATOR_ACTIVE' | 'UNMAPPED' | 'OFFLINE';
    detected: boolean;
    divergence_strength: number;
    signal_bias: 'BUY' | 'SELL' | 'NEUTRAL';
    message: string;
    timestamp: string;
}

const stateClasses: Record<string, string> = {
    DORMANT: 'text-gray-400 border-gray-700/70 bg-gray-900/60',
    TRACKING: 'text-yellow-300 border-yellow-700/60 bg-yellow-950/20',
    PREDATOR_ACTIVE: 'text-rose-300 border-rose-700/60 bg-rose-950/20',
    UNMAPPED: 'text-gray-400 border-gray-700/70 bg-gray-900/60',
    OFFLINE: 'text-gray-500 border-gray-800 bg-gray-900/40'
};

const biasClasses: Record<string, string> = {
    BUY: 'text-emerald-300',
    SELL: 'text-rose-300',
    NEUTRAL: 'text-gray-300'
};

const PredatorRadar: React.FC<PredatorRadarProps> = ({ symbol = 'EURUSD', timeframe = 'M5' }) => {
    const { apiFetch } = useApi();
    const [snapshot, setSnapshot] = useState<PredatorSnapshot | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchRadar = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/analysis/predator-radar?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
            if (!res.ok) {
                return;
            }
            const data = await res.json();
            setSnapshot(data);
        } catch (error) {
            console.error('Predator Radar fetch error:', error);
        } finally {
            setLoading(false);
        }
    }, [apiFetch, symbol, timeframe]);

    useEffect(() => {
        fetchRadar();
        const interval = setInterval(fetchRadar, 15000);
        return () => clearInterval(interval);
    }, [fetchRadar]);

    const state = snapshot?.state || 'OFFLINE';
    const strength = Math.max(0, Math.min(100, snapshot?.divergence_strength || 0));
    const classes = stateClasses[state] || stateClasses.OFFLINE;
    const bias = snapshot?.signal_bias || 'NEUTRAL';

    return (
        <div className={`animate-in fade-in duration-500 border rounded-xl px-4 py-3 min-w-[280px] ${classes}`}>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <Radar className={`w-4 h-4 ${state === 'PREDATOR_ACTIVE' ? 'animate-pulse' : ''}`} />
                    <span className="text-[10px] font-bold tracking-[0.18em] uppercase">Predator Radar</span>
                    <InfoTooltip
                        title="Predator Radar"
                        content="Fuerza de divergencia inter-mercado (SmT). Detecta barrido de liquidez en mercado correlacionado con estancamiento del activo base."
                    />
                </div>
                {snapshot?.detected ? <AlertTriangle className="w-3.5 h-3.5 text-rose-300" /> : <Eye className="w-3.5 h-3.5 text-gray-500" />}
            </div>

            <div className="flex items-end justify-between mb-2">
                <div>
                    <p className="text-[10px] text-gray-400 uppercase tracking-wider">
                        {snapshot?.symbol || symbol} vs {snapshot?.anchor || 'N/A'}
                    </p>
                    <p className="text-xs font-bold text-white">{state.replace('_', ' ')}</p>
                </div>
                <div className="text-right">
                    <p className="text-[10px] text-gray-500 uppercase">Bias</p>
                    <p className={`text-sm font-bold ${biasClasses[bias] || biasClasses.NEUTRAL}`}>{bias}</p>
                </div>
            </div>

            <div className="w-full h-1.5 rounded-full bg-black/40 overflow-hidden mb-2">
                <div
                    className={`h-full transition-all duration-700 ${strength >= 70 ? 'bg-rose-400' : strength >= 45 ? 'bg-yellow-400' : 'bg-cyan-400'}`}
                    style={{ width: `${strength}%` }}
                />
            </div>

            <div className="flex items-center justify-between">
                <p className="text-[10px] text-gray-400 truncate max-w-[190px]">{snapshot?.message || (loading ? 'Sincronizando radar...' : 'Sin señal de divergencia')}</p>
                <p className="text-xs font-mono text-white">{strength.toFixed(1)}</p>
            </div>
        </div>
    );
};

export default PredatorRadar;
