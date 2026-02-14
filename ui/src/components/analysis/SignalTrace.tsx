import React, { useEffect, useState } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { GitBranch, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';

interface PipelineEvent {
    id: number;
    signal_id: string;
    stage: string;
    timestamp: string;
    decision: string | null;
    reason: string | null;
    metadata: any;
}

interface SignalTraceProps {
    signalId: string;
}

const stageIcons: Record<string, any> = {
    CREATED: Clock,
    STRATEGY_ANALYSIS: GitBranch,
    RISK_VALIDATION: AlertTriangle,
    EXECUTED: CheckCircle,
    REJECTED: XCircle,
};

const stageColors: Record<string, string> = {
    CREATED: 'text-blue-400',
    STRATEGY_ANALYSIS: 'text-purple-400',
    RISK_VALIDATION: 'text-yellow-400',
    EXECUTED: 'text-aethelgard-green',
    REJECTED: 'text-red-400',
};

const decisionColors: Record<string, string> = {
    APPROVED: 'bg-aethelgard-green/20 text-aethelgard-green border-aethelgard-green/30',
    REJECTED: 'bg-red-500/20 text-red-400 border-red-500/30',
    PENDING: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
};

const SignalTrace: React.FC<SignalTraceProps> = ({ signalId }) => {
    const [trace, setTrace] = useState<PipelineEvent[]>([]);
    const [signalInfo, setSignalInfo] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchTrace = () => {
        setLoading(true);
        setError(null);
        fetch(`/api/signal/${signalId}/trace`)
            .then(res => {
                if (!res.ok) {
                    if (res.status === 404) {
                        throw new Error('No se encontró trazabilidad para esta señal');
                    }
                    throw new Error('Error al obtener trazabilidad');
                }
                return res.json();
            })
            .then(data => {
                setTrace(data.trace || []);
                setSignalInfo(data.signal_info);
            })
            .catch(err => {
                setError(err.message || 'No se pudo cargar la trazabilidad.');
                console.error('[SignalTrace] Error:', err);
            })
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        if (signalId) {
            fetchTrace();
        }
    }, [signalId]);

    return (
        <GlassPanel className="w-full h-full flex flex-col gap-4">
            <div className="flex items-center gap-3 mb-2">
                <GitBranch className="text-aethelgard-blue" size={22} />
                <h2 className="font-bold text-lg">Trazabilidad de Señal</h2>
                <span className="ml-auto font-mono text-xs text-white/40">{signalId}</span>
            </div>

            {loading && <div className="text-white/60">Cargando trazabilidad...</div>}
            {error && (
                <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
                    <XCircle size={18} /> {error}
                    <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchTrace}>
                        Reintentar
                    </button>
                </div>
            )}

            {!loading && !error && signalInfo && (
                <div className="bg-white/5 border border-white/10 rounded-lg p-3 mb-2">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>
                            <span className="text-white/40">Símbolo:</span>{' '}
                            <span className="font-mono text-aethelgard-green">{signalInfo.symbol}</span>
                        </div>
                        <div>
                            <span className="text-white/40">Dirección:</span>{' '}
                            <span
                                className={`font-bold ${signalInfo.direction === 'BUY' ? 'text-aethelgard-green' : 'text-red-400'
                                    }`}
                            >
                                {signalInfo.direction}
                            </span>
                        </div>
                        <div>
                            <span className="text-white/40">Precio:</span>{' '}
                            <span className="font-mono">{signalInfo.price}</span>
                        </div>
                        <div>
                            <span className="text-white/40">Timeframe:</span>{' '}
                            <span className="font-mono">{signalInfo.timeframe}</span>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !error && trace.length > 0 && (
                <div className="flex flex-col gap-3 overflow-y-auto max-h-[500px]">
                    {trace.map((event, idx) => {
                        const Icon = stageIcons[event.stage] || Clock;
                        const stageColor = stageColors[event.stage] || 'text-white/60';
                        const decisionColor = event.decision
                            ? decisionColors[event.decision] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'
                            : '';

                        return (
                            <div
                                key={event.id}
                                className="relative bg-white/5 border border-white/10 rounded-lg p-4 hover:bg-white/10 transition-all"
                            >
                                {/* Timeline connector */}
                                {idx < trace.length - 1 && (
                                    <div className="absolute left-6 top-12 w-0.5 h-8 bg-white/20" />
                                )}

                                <div className="flex items-start gap-3">
                                    <div className={`p-2 rounded-lg bg-white/10 ${stageColor}`}>
                                        <Icon size={20} />
                                    </div>

                                    <div className="flex-1">
                                        <div className="flex items-center justify-between mb-1">
                                            <h3 className="font-bold text-base text-white/90">{event.stage}</h3>
                                            {event.decision && (
                                                <span className={`px-2 py-1 rounded text-xs font-bold border ${decisionColor}`}>
                                                    {event.decision}
                                                </span>
                                            )}
                                        </div>

                                        <div className="text-xs text-white/40 mb-2">
                                            {new Date(event.timestamp).toLocaleString()}
                                        </div>

                                        {event.reason && (
                                            <p className="text-sm text-white/70 mb-2">{event.reason}</p>
                                        )}

                                        {event.metadata && Object.keys(event.metadata).length > 0 && (
                                            <details className="text-xs">
                                                <summary className="cursor-pointer text-white/40 hover:text-white/60">
                                                    Ver metadata
                                                </summary>
                                                <pre className="mt-2 p-2 bg-black/30 rounded overflow-x-auto text-white/60">
                                                    {JSON.stringify(event.metadata, null, 2)}
                                                </pre>
                                            </details>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {!loading && !error && trace.length === 0 && (
                <div className="text-white/40 text-center py-8">
                    No hay trazabilidad disponible para esta señal
                </div>
            )}
        </GlassPanel>
    );
};

export default SignalTrace;
