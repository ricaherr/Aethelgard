import React, { useEffect, useState } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { BookOpen, CheckCircle, XCircle, TrendingUp, BarChart3, Shield } from 'lucide-react';

interface Strategy {
    name: string;
    description: string;
    enabled?: boolean;
    membership_required?: string;
    required_regime?: string[];
    timeframes?: string[];
    category?: string;
    difficulty?: string;
    risk_level?: string;
    regimes?: string[];
}

const StrategyExplorer: React.FC = () => {
    const [registered, setRegistered] = useState<Strategy[]>([]);
    const [educational, setEducational] = useState<Strategy[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'registered' | 'educational'>('registered');

    const fetchStrategies = () => {
        setLoading(true);
        setError(null);
        fetch('/api/strategies/library')
            .then(res => {
                if (!res.ok) throw new Error('Error al obtener biblioteca de estrategias');
                return res.json();
            })
            .then(data => {
                setRegistered(data.registered || []);
                setEducational(data.educational || []);
            })
            .catch(err => {
                setError('No se pudo cargar la biblioteca de estrategias.');
                console.error('[StrategyExplorer] Error:', err);
            })
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        fetchStrategies();
    }, []);

    const strategies = activeTab === 'registered' ? registered : educational;

    return (
        <GlassPanel className="w-full h-full flex flex-col gap-4">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                    <BookOpen className="text-aethelgard-blue" size={22} />
                    <h2 className="font-bold text-lg">Explorador de Estrategias</h2>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setActiveTab('registered')}
                        className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'registered'
                                ? 'bg-aethelgard-green/20 text-aethelgard-green border border-aethelgard-green/30'
                                : 'bg-white/5 text-white/60 hover:bg-white/10'
                            }`}
                    >
                        Registradas ({registered.length})
                    </button>
                    <button
                        onClick={() => setActiveTab('educational')}
                        className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'educational'
                                ? 'bg-aethelgard-blue/20 text-aethelgard-blue border border-aethelgard-blue/30'
                                : 'bg-white/5 text-white/60 hover:bg-white/10'
                            }`}
                    >
                        Biblioteca ({educational.length})
                    </button>
                </div>
            </div>

            {loading && <div className="text-white/60">Cargando estrategias...</div>}
            {error && (
                <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
                    <XCircle size={18} /> {error}
                    <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchStrategies}>
                        Reintentar
                    </button>
                </div>
            )}

            {!loading && !error && (
                <div className="flex flex-col gap-3 overflow-y-auto max-h-[600px]">
                    {strategies.length === 0 ? (
                        <div className="text-white/40 text-center py-8">No hay estrategias disponibles</div>
                    ) : (
                        strategies.map((strategy, idx) => (
                            <div
                                key={idx}
                                className="bg-white/5 border border-white/10 rounded-lg p-4 hover:bg-white/10 transition-all"
                            >
                                <div className="flex items-start justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <TrendingUp size={18} className="text-aethelgard-green" />
                                        <h3 className="font-bold text-base text-white/90">{strategy.name}</h3>
                                    </div>
                                    {strategy.enabled !== undefined && (
                                        <span
                                            className={`px-2 py-1 rounded text-xs font-bold ${strategy.enabled
                                                    ? 'bg-aethelgard-green/20 text-aethelgard-green'
                                                    : 'bg-red-500/20 text-red-400'
                                                }`}
                                        >
                                            {strategy.enabled ? (
                                                <>
                                                    <CheckCircle size={12} className="inline mr-1" /> ACTIVA
                                                </>
                                            ) : (
                                                <>
                                                    <XCircle size={12} className="inline mr-1" /> INACTIVA
                                                </>
                                            )}
                                        </span>
                                    )}
                                </div>

                                <p className="text-sm text-white/60 mb-3">{strategy.description}</p>

                                <div className="flex flex-wrap gap-2 text-xs">
                                    {strategy.category && (
                                        <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded border border-purple-500/30">
                                            <BarChart3 size={12} className="inline mr-1" />
                                            {strategy.category}
                                        </span>
                                    )}
                                    {strategy.difficulty && (
                                        <span className="px-2 py-1 bg-yellow-500/20 text-yellow-300 rounded border border-yellow-500/30">
                                            {strategy.difficulty}
                                        </span>
                                    )}
                                    {strategy.risk_level && (
                                        <span className="px-2 py-1 bg-orange-500/20 text-orange-300 rounded border border-orange-500/30">
                                            <Shield size={12} className="inline mr-1" />
                                            {strategy.risk_level}
                                        </span>
                                    )}
                                    {(strategy.timeframes || []).length > 0 && (
                                        <span className="px-2 py-1 bg-blue-500/20 text-blue-300 rounded border border-blue-500/30">
                                            TF: {strategy.timeframes?.join(', ')}
                                        </span>
                                    )}
                                    {(strategy.required_regime || strategy.regimes || []).length > 0 && (
                                        <span className="px-2 py-1 bg-aethelgard-green/20 text-aethelgard-green rounded border border-aethelgard-green/30">
                                            Regímenes: {(strategy.required_regime || strategy.regimes)?.join(', ')}
                                        </span>
                                    )}
                                    {strategy.membership_required && (
                                        <span className="px-2 py-1 bg-pink-500/20 text-pink-300 rounded border border-pink-500/30 uppercase">
                                            {strategy.membership_required}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            )}
        </GlassPanel>
    );
};

export default StrategyExplorer;
