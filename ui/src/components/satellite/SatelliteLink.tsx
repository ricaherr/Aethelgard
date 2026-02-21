import { useState, useEffect } from 'react';
import { Satellite, ShieldCheck, Activity, Power, PowerOff, Wifi, Terminal, Zap, Globe, Gauge } from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';
import { useAethelgard } from '../../hooks/useAethelgard';

export function SatelliteLink() {
    const { status: systemStatus } = useAethelgard();
    const providers = systemStatus.satellites || {};

    const toggleProvider = async (id: string, currentlyEnabled: boolean) => {
        try {
            await fetch('/api/satellite/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_id: id, enabled: !currentlyEnabled })
            });
            // Status will be updated via WebSocket heartbeat
        } catch (err) {
            console.error('Error toggling provider:', err);
        }
    };

    return (
        <div className="flex flex-col gap-6 h-full p-4 lg:p-8 bg-black/20 rounded-3xl backdrop-blur-sm border border-white/5 overflow-y-auto scrollbar-hide">
            {/* NASA HEADER */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/5 pb-8">
                <div className="space-y-4">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-aethelgard-blue/20 text-aethelgard-blue border border-aethelgard-blue/30 shadow-[0_0_15px_rgba(0,210,255,0.2)]">
                            <Terminal size={18} />
                        </div>
                        <h2 className="text-4xl font-outfit font-black text-white tracking-tighter uppercase italic">
                            Comms <span className="text-aethelgard-blue">Command</span>
                        </h2>
                    </div>
                    <div className="flex items-center gap-6">
                        <div className="flex flex-col">
                            <span className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-black">Mission Status</span>
                            <span className="text-xs font-mono text-aethelgard-green font-bold">OPERATIONAL</span>
                        </div>
                        <div className="w-px h-8 bg-white/10" />
                        <div className="flex flex-col">
                            <span className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-black">Active Nodes</span>
                            <span className="text-xs font-mono text-white/80">{Object.keys(providers).length}</span>
                        </div>
                        <div className="w-px h-8 bg-white/10" />
                        <div className="flex flex-col">
                            <span className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-black">Global Heartbeat</span>
                            <div className="flex items-center gap-2">
                                <Activity size={12} className="text-aethelgard-green animate-pulse" />
                                <span className="text-xs font-mono text-aethelgard-green">STABLE</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <GlassPanel className="px-6 py-4 border-aethelgard-blue/20 bg-aethelgard-blue/5">
                        <div className="flex items-center gap-4">
                            <Globe size={20} className="text-aethelgard-blue animate-[spin_10s_linear_infinite]" />
                            <div className="flex flex-col">
                                <span className="text-[9px] font-black text-white/40 uppercase tracking-[0.2em]">Omnichain Layer</span>
                                <span className="text-[11px] font-mono text-aethelgard-blue/80 font-bold">L1-PERSISTENCE: ON</span>
                            </div>
                        </div>
                    </GlassPanel>
                </div>
            </div>

            {/* TELEMETRY GRID */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4">
                {Object.keys(providers).length === 0 ? (
                    <div className="col-span-full py-20 flex flex-col items-center justify-center border-2 border-dashed border-white/5 rounded-3xl bg-white/[0.01]">
                        <Satellite size={48} className="text-white/10 mb-4" />
                        <p className="text-white/20 font-mono text-xs uppercase tracking-[0.4em]">Awaiting Satellite Uplink...</p>
                    </div>
                ) : (
                    Object.entries(providers).map(([id, status]) => (
                        <SatelliteNode
                            key={id}
                            id={id}
                            status={status}
                            onToggle={() => toggleProvider(id, status.status !== 'MANUAL_DISABLED')}
                        />
                    ))
                )}
            </div>

            {/* CHIEF DIRECTIVE BAR */}
            <div className="mt-auto pt-8">
                <div className="bg-gradient-to-r from-aethelgard-green/5 via-transparent to-transparent p-6 border-l-2 border-aethelgard-green/50 rounded-r-2xl">
                    <div className="flex items-start gap-4">
                        <ShieldCheck size={24} className="text-aethelgard-green shrink-0 mt-1" />
                        <div className="space-y-2">
                            <h4 className="text-sm font-black text-white uppercase tracking-widest italic">Agnosticism Protocol & Manual Veto</h4>
                            <p className="text-[11px] text-white/40 leading-relaxed max-w-3xl font-medium uppercase tracking-tighter">
                                DECOUPLING LAW: The Core Brain (Aethelgard.db) maintains absolute independence from provider libraries.
                                Manual SILENCE command overrides all trade executions instantly, purging connector state from persistent memory.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function SatelliteNode({ id, status, onToggle }: { id: string, status: any, onToggle: () => void }) {
    const isManualDisabled = status.status === 'MANUAL_DISABLED';
    const isOffline = status.status === 'OFFLINE';
    const isHighLatency = status.latency > 200;

    let glowColor = 'shadow-aethelgard-blue/20';
    let iconColor = 'text-aethelgard-blue';
    let bgColor = 'bg-aethelgard-blue/10';

    if (isManualDisabled) {
        glowColor = 'shadow-white/5';
        iconColor = 'text-white/20';
        bgColor = 'bg-white/5';
    } else if (isOffline) {
        glowColor = 'shadow-red-500/20';
        iconColor = 'text-red-500';
        bgColor = 'bg-red-500/10';
    } else if (isHighLatency) {
        glowColor = 'shadow-orange-500/20';
        iconColor = 'text-orange-400';
        bgColor = 'bg-orange-400/10';
    }

    return (
        <GlassPanel
            className={`relative overflow-hidden group transition-all duration-700 ${isManualDisabled ? 'opacity-40' : 'hover:bg-white/[0.03] hover:border-white/20 shadow-2xl'} ${glowColor}`}
        >
            <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-transparent via-current to-transparent opacity-20" style={{ color: isManualDisabled ? '#333' : (isOffline ? '#ef4444' : (isHighLatency ? '#fb923c' : '#00d2ff')) }} />

            <div className="p-6 space-y-6">
                {/* NODE HEADER */}
                <div className="flex justify-between items-start">
                    <div className="flex items-center gap-4">
                        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center border border-white/5 transition-all duration-700 ${bgColor} ${iconColor} group-hover:scale-110`}>
                            <Zap size={28} className={!isManualDisabled && !isOffline ? 'animate-pulse' : ''} />
                        </div>
                        <div>
                            <h3 className="font-black text-white text-xl tracking-tighter uppercase italic">{id}</h3>
                            <div className="flex items-center gap-2">
                                <div className={`w-1.5 h-1.5 rounded-full ${isManualDisabled ? 'bg-white/10' : (isOffline ? 'bg-red-500' : 'bg-aethelgard-blue')} animate-pulse`} />
                                <span className={`text-[10px] font-mono font-black uppercase tracking-widest ${iconColor}`}>
                                    {status.status.replace('_', ' ')}
                                </span>
                            </div>
                        </div>
                    </div>

                    <button
                        onClick={onToggle}
                        className={`p-3 rounded-xl transition-all duration-500 border ${!isManualDisabled
                            ? 'bg-aethelgard-blue/20 border-aethelgard-blue/30 text-aethelgard-blue hover:bg-aethelgard-blue/40 hover:scale-110 shadow-[0_0_15px_rgba(0,210,255,0.2)]'
                            : 'bg-white/5 border-white/10 text-white/20 hover:bg-white/10 hover:text-white/80'
                            }`}
                        title={!isManualDisabled ? "SILENCE SATELLITE" : "RESTORE CONNECTION"}
                    >
                        {!isManualDisabled ? <Power size={20} /> : <PowerOff size={20} />}
                    </button>
                </div>

                {/* LATENCY TELEMETRY */}
                <div className="space-y-2">
                    <div className="flex justify-between items-end">
                        <span className="text-[9px] font-black text-white/30 uppercase tracking-[0.3em]">Latency Response</span>
                        <div className="flex items-baseline gap-1">
                            <span className={`text-lg font-mono font-black tracking-tighter ${iconColor}`}>
                                {status.latency.toFixed(0)}
                            </span>
                            <span className="text-[9px] font-mono text-white/20">ms</span>
                        </div>
                    </div>
                    <div className="h-1.5 bg-white/5 rounded-full overflow-hidden flex gap-0.5">
                        {[...Array(20)].map((_, i) => {
                            const intensity = (i + 1) * 20; // 0 to 400ms scale
                            const isActive = status.latency >= intensity - 20;
                            return (
                                <div
                                    key={i}
                                    className={`h-full flex-1 transition-all duration-700 ${isActive
                                            ? (intensity > 200 ? 'bg-red-500' : (intensity > 100 ? 'bg-orange-400' : 'bg-aethelgard-blue'))
                                            : 'bg-white/5'
                                        }`}
                                />
                            );
                        })}
                    </div>
                </div>

                {/* STATS ROW */}
                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/5">
                    <div className="space-y-0.5">
                        <span className="text-[8px] font-black text-white/20 uppercase tracking-[0.3em]">Burst Errors</span>
                        <div className="flex items-center gap-2">
                            <Gauge size={12} className="text-white/20" />
                            <span className={`text-sm font-mono font-bold ${status.failures > 0 ? 'text-red-400' : 'text-white/60'}`}>
                                {status.failures.toString().padStart(3, '0')}
                            </span>
                        </div>
                    </div>
                    <div className="space-y-0.5">
                        <span className="text-[8px] font-black text-white/20 uppercase tracking-[0.3em]">Signal Quality</span>
                        <div className="flex items-center gap-2">
                            <Zap size={12} className="text-white/20" />
                            <span className="text-sm font-mono font-bold text-white/60">
                                {isManualDisabled ? '00.0%' : (isOffline ? '00.0%' : (isHighLatency ? '82.4%' : '99.9%'))}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </GlassPanel>
    );
}
