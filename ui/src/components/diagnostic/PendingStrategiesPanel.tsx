/**
 * PendingStrategiesPanel — HU 3.2
 *
 * Muestra todas las estrategias en estado LOGIC_PENDING con su diagnóstico,
 * causa, sugerencia y acciones disponibles (reintentar, promover, descartar).
 *
 * Trace_ID: ETI-E3-HU3.2
 */
import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    AlertTriangle, RefreshCw, Trash2, Zap, ChevronDown, ChevronUp,
    Clock, Lightbulb, FileCode, FlaskConical, CheckCircle2, Loader2
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import { PendingStrategyDiagnosis } from '../../types/aethelgard';
import { useApi } from '../../hooks/useApi';

const API_BASE = '/api/v3/strategy-pending';

const CAUSE_LABELS: Record<string, string> = {
    MISSING_CLASS_FILE: 'Archivo faltante',
    MISSING_LOGIC: 'Sin lógica definida',
    INVALID_LOGIC_JSON: 'JSON inválido',
    MISSING_SCHEMA_FILE: 'Schema faltante',
    NEEDS_IMPLEMENTATION: 'Pendiente de implementar',
    UNKNOWN: 'Causa desconocida',
};

const CAUSE_COLORS: Record<string, string> = {
    MISSING_CLASS_FILE: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
    MISSING_LOGIC: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
    INVALID_LOGIC_JSON: 'text-red-400 bg-red-400/10 border-red-400/20',
    MISSING_SCHEMA_FILE: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
    NEEDS_IMPLEMENTATION: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
    UNKNOWN: 'text-white/40 bg-white/5 border-white/10',
};

export const PendingStrategiesPanel = () => {
    const { apiFetch } = useApi();
    const [strategies, setStrategies] = useState<PendingStrategyDiagnosis[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [lastFetch, setLastFetch] = useState<string | null>(null);

    const fetchPending = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await apiFetch(`${API_BASE}/`);
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || res.statusText);
            }
            const data: PendingStrategyDiagnosis[] = await res.json();
            setStrategies(data);
            setLastFetch(new Date().toLocaleTimeString());
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [apiFetch]);

    const handleAction = useCallback(async (
        classId: string,
        action: 'retry' | 'discard' | 'promote',
        reason?: string
    ) => {
        setActionLoading(`${classId}-${action}`);
        try {
            const res = await apiFetch(`${API_BASE}/${classId}/${action}`, {
                method: 'POST',
                body: JSON.stringify({ reason }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || res.statusText);
            }
            await fetchPending();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setActionLoading(null);
        }
    }, [apiFetch, fetchPending]);

    const isActing = (classId: string, action: string) =>
        actionLoading === `${classId}-${action}`;

    return (
        <GlassPanel className="p-6 flex flex-col border-yellow-500/15">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                        <AlertTriangle size={16} className="text-yellow-400" />
                    </div>
                    <div>
                        <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/70">
                            Logic Pending
                        </h3>
                        <p className="text-[9px] text-white/30 mt-0.5">
                            Estrategias bloqueadas · diagnóstico automático
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {lastFetch && (
                        <div className="flex items-center gap-1 opacity-40">
                            <Clock size={10} />
                            <span className="text-[9px] font-mono">{lastFetch}</span>
                        </div>
                    )}
                    <button
                        onClick={fetchPending}
                        disabled={loading}
                        className={cn(
                            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider border transition-all",
                            "bg-white/5 border-white/10 text-white/60 hover:border-yellow-400/30 hover:text-yellow-400",
                            loading && "cursor-wait opacity-50"
                        )}
                    >
                        {loading
                            ? <Loader2 size={12} className="animate-spin" />
                            : <RefreshCw size={12} />
                        }
                        {loading ? 'Cargando...' : 'Escanear'}
                    </button>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="mb-4 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">
                    {error}
                </div>
            )}

            {/* Empty state */}
            {!loading && strategies.length === 0 && !error && lastFetch && (
                <div className="flex flex-col items-center justify-center py-10 opacity-30">
                    <CheckCircle2 size={32} className="mb-2" />
                    <span className="text-[10px] font-black uppercase tracking-widest">
                        Sin estrategias bloqueadas
                    </span>
                </div>
            )}

            {!lastFetch && !loading && (
                <div className="flex flex-col items-center justify-center py-10 opacity-20">
                    <FlaskConical size={28} className="mb-2" />
                    <span className="text-[10px] font-black uppercase tracking-widest">
                        Pulsa escanear para iniciar diagnóstico
                    </span>
                </div>
            )}

            {/* Strategy cards */}
            <div className="space-y-3">
                <AnimatePresence initial={false}>
                    {strategies.map((s, i) => {
                        const isOpen = expanded === s.class_id;
                        const causeKey = s.cause ?? 'UNKNOWN';
                        const causeColor = CAUSE_COLORS[causeKey] ?? CAUSE_COLORS.UNKNOWN;
                        const causeLabel = CAUSE_LABELS[causeKey] ?? causeKey;

                        return (
                            <motion.div
                                key={s.class_id}
                                initial={{ opacity: 0, y: 6 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -6 }}
                                transition={{ delay: i * 0.04 }}
                                className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden"
                            >
                                {/* Card header */}
                                <div
                                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                                    onClick={() => setExpanded(isOpen ? null : s.class_id)}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="p-1.5 rounded-lg bg-white/5 text-white/30">
                                            <FileCode size={13} />
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-[11px] font-black text-white/90 uppercase tracking-tight">
                                                    {s.mnemonic}
                                                </span>
                                                <span className="text-[8px] font-mono text-white/20">
                                                    {s.class_id}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 mt-1">
                                                <span className="text-[8px] font-mono text-white/30 bg-white/5 px-1.5 rounded">
                                                    {s.strategy_type}
                                                </span>
                                                {s.cause && (
                                                    <span className={cn(
                                                        "text-[8px] font-black uppercase px-2 py-0.5 rounded border",
                                                        causeColor
                                                    )}>
                                                        {causeLabel}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-[8px] font-black uppercase text-yellow-400/60 tracking-wider">
                                            LOGIC_PENDING
                                        </span>
                                        {isOpen
                                            ? <ChevronUp size={14} className="text-white/30" />
                                            : <ChevronDown size={14} className="text-white/20" />
                                        }
                                    </div>
                                </div>

                                {/* Expanded content */}
                                <AnimatePresence initial={false}>
                                    {isOpen && (
                                        <motion.div
                                            initial={{ height: 0, opacity: 0 }}
                                            animate={{ height: 'auto', opacity: 1 }}
                                            exit={{ height: 0, opacity: 0 }}
                                            transition={{ duration: 0.2 }}
                                            className="overflow-hidden border-t border-white/5"
                                        >
                                            <div className="p-4 space-y-4">
                                                {/* Cause detail */}
                                                {s.cause_detail && (
                                                    <div className="flex gap-2 p-3 rounded-lg bg-red-500/5 border border-red-500/10">
                                                        <AlertTriangle size={12} className="text-red-400 mt-0.5 shrink-0" />
                                                        <p className="text-[10px] text-white/60 leading-relaxed">
                                                            {s.cause_detail}
                                                        </p>
                                                    </div>
                                                )}

                                                {/* Suggestion */}
                                                {s.suggestion && (
                                                    <div className="flex gap-2 p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                                                        <Lightbulb size={12} className="text-blue-400 mt-0.5 shrink-0" />
                                                        <p className="text-[10px] text-white/60 leading-relaxed">
                                                            {s.suggestion}
                                                        </p>
                                                    </div>
                                                )}

                                                {/* Description */}
                                                {s.description && (
                                                    <p className="text-[10px] text-white/30 italic px-1">
                                                        {s.description}
                                                    </p>
                                                )}

                                                {/* Last checked */}
                                                {s.last_checked && (
                                                    <div className="flex items-center gap-1.5 text-[9px] text-white/20 font-mono">
                                                        <Clock size={10} />
                                                        Último diagnóstico: {new Date(s.last_checked).toLocaleString()}
                                                    </div>
                                                )}

                                                {/* Actions */}
                                                <div className="flex gap-2 pt-2 border-t border-white/5">
                                                    <button
                                                        onClick={() => handleAction(s.class_id, 'retry')}
                                                        disabled={!!actionLoading}
                                                        className={cn(
                                                            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider border transition-all",
                                                            "bg-aethelgard-blue/5 border-aethelgard-blue/20 text-aethelgard-blue/80 hover:bg-aethelgard-blue/15",
                                                            actionLoading && "opacity-50 cursor-wait"
                                                        )}
                                                    >
                                                        {isActing(s.class_id, 'retry')
                                                            ? <Loader2 size={11} className="animate-spin" />
                                                            : <RefreshCw size={11} />
                                                        }
                                                        Reintentar
                                                    </button>

                                                    <button
                                                        onClick={() => handleAction(s.class_id, 'promote', 'Override manual')}
                                                        disabled={!!actionLoading}
                                                        className={cn(
                                                            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider border transition-all",
                                                            "bg-aethelgard-green/5 border-aethelgard-green/20 text-aethelgard-green/70 hover:bg-aethelgard-green/15",
                                                            actionLoading && "opacity-50 cursor-wait"
                                                        )}
                                                    >
                                                        {isActing(s.class_id, 'promote')
                                                            ? <Loader2 size={11} className="animate-spin" />
                                                            : <Zap size={11} />
                                                        }
                                                        Promover
                                                    </button>

                                                    <button
                                                        onClick={() => handleAction(s.class_id, 'discard', 'Archivada por operador')}
                                                        disabled={!!actionLoading}
                                                        className={cn(
                                                            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider border transition-all ml-auto",
                                                            "bg-red-500/5 border-red-500/20 text-red-400/60 hover:bg-red-500/10",
                                                            actionLoading && "opacity-50 cursor-wait"
                                                        )}
                                                    >
                                                        {isActing(s.class_id, 'discard')
                                                            ? <Loader2 size={11} className="animate-spin" />
                                                            : <Trash2 size={11} />
                                                        }
                                                        Descartar
                                                    </button>
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>
            </div>
        </GlassPanel>
    );
};
