import React, { useEffect, useState } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { Save, RefreshCw, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';


export function InstrumentsEditor() {
    const [markets, setMarkets] = useState<any>({});
    const [activeMarket, setActiveMarket] = useState<string | null>(null);
    const [activeCategory, setActiveCategory] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [newSymbol, setNewSymbol] = useState<string>("");

    const fetchInstruments = async () => {
        setLoading(true);
        setError(null);
        try {
            // En Settings, pedir todos los instrumentos y categorías (activos e inactivos)
            const res = await fetch('/api/instruments?all=true');
            if (!res.ok) throw new Error('No se pudo obtener la lista de instrumentos.');
            const data = await res.json();
            const mkts = data.markets || {};
            setMarkets(mkts);
            // Selección inicial
            const firstMarket = Object.keys(mkts)[0] || null;
            setActiveMarket(firstMarket);
            const firstCat = firstMarket ? Object.keys(mkts[firstMarket])[0] : null;
            setActiveCategory(firstCat);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchInstruments();
    }, []);

    // Edición de campos de categoría
    const handleCategoryField = (field: string, value: any) => {
        if (!activeMarket || !activeCategory) return;
        setMarkets((prev: any) => ({
            ...prev,
            [activeMarket]: {
                ...prev[activeMarket],
                [activeCategory]: {
                    ...prev[activeMarket][activeCategory],
                    [field]: value
                }
            }
        }));
    };

    // Edición de instrumentos individuales
    const handleInstrumentActive = (symbol: string, checked: boolean) => {
        if (!activeMarket || !activeCategory) return;
        setMarkets((prev: any) => {
            const cat = prev[activeMarket][activeCategory];
            const actives = cat.actives ? { ...cat.actives } : {};
            actives[symbol] = checked;
            return {
                ...prev,
                [activeMarket]: {
                    ...prev[activeMarket],
                    [activeCategory]: {
                        ...cat,
                        actives
                    }
                }
            };
        });
    };

    // Agregar nuevo símbolo
    const handleAddSymbol = () => {
        if (!activeMarket || !activeCategory || !newSymbol.trim()) return;
        setMarkets((prev: any) => {
            const cat = prev[activeMarket][activeCategory];
            const instruments = [...cat.instruments, newSymbol.trim().toUpperCase()];
            return {
                ...prev,
                [activeMarket]: {
                    ...prev[activeMarket],
                    [activeCategory]: {
                        ...cat,
                        instruments
                    }
                }
            };
        });
        setNewSymbol("");
    };

    // Guardar solo la categoría activa (POST optimizado)
    const handleSave = async () => {
        if (!activeMarket || !activeCategory) return;
        setSaving(true);
        setError(null);
        setMessage(null);
        try {
            const catData = markets[activeMarket][activeCategory];
            // Refuerzo: asegurar que instruments contiene TODOS los símbolos agregados históricamente
            // y que no se elimina ninguno al activar/inactivar
            let instruments = Array.isArray(catData.instruments) ? [...catData.instruments] : [];
            // Eliminar duplicados por si acaso
            instruments = Array.from(new Set(instruments.map(s => s.trim().toUpperCase())));
            // Si algún símbolo está en actives pero no en instruments, agregarlo (robustez)
            if (catData.actives) {
                Object.keys(catData.actives).forEach(sym => {
                    if (!instruments.includes(sym)) instruments.push(sym);
                });
            }
            // No eliminar ningún símbolo aunque esté inactivo
            const data = {
                ...catData,
                instruments,
                enabled: catData.enabled !== false
            };
            const payload = {
                market: activeMarket,
                category: activeCategory,
                data
            };
            const res = await fetch('/api/instruments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error('Error al guardar la categoría.');
            setMessage('✅ Categoría actualizada correctamente.');
            setTimeout(() => setMessage(null), 3000);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <GlassPanel premium className="h-full min-h-[500px] flex flex-col p-8 overflow-y-auto">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-2xl font-bold font-outfit text-white/90">Gestión de Instrumentos</h3>
                <div className="flex gap-3">
                    <button
                        onClick={fetchInstruments}
                        className="p-3 rounded-xl bg-white/5 border border-white/5 text-white/40 hover:text-white/80 hover:bg-white/10 transition-all"
                        title="Recargar desde DB"
                    >
                        <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving || loading}
                        className={`flex items-center gap-2 px-6 py-3 rounded-xl font-bold font-outfit transition-all shadow-lg ${saving ? 'bg-white/20 text-white/40 cursor-not-allowed' : 'bg-aethelgard-green text-dark hover:scale-105 active:scale-95 shadow-aethelgard-green/20'}`}
                    >
                        <Save size={18} />
                        {saving ? 'Guardando...' : 'Guardar Cambios'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex gap-3 animate-pulse mb-4">
                    <AlertTriangle size={16} className="shrink-0" />
                    <span>{error}</span>
                </div>
            )}
            {message && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 rounded-xl bg-aethelgard-green/10 border border-aethelgard-green/20 text-aethelgard-green text-xs font-bold mb-4"
                >
                    {message}
                </motion.div>
            )}

            {loading ? (
                <div className="flex flex-col items-center justify-center h-64 text-white/20 gap-4">
                    <RefreshCw size={48} className="animate-spin" />
                    <p className="text-sm font-mono uppercase tracking-widest">Cargando instrumentos...</p>
                </div>
            ) : (
                <>
                    {/* Tabs de mercados */}
                    <div className="flex gap-2 mb-4">
                        {Object.keys(markets).map(market => (
                            <button
                                key={market}
                                className={`px-4 py-2 rounded-lg font-bold text-sm transition-all ${activeMarket === market ? 'bg-aethelgard-blue/30 text-white' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}
                                onClick={() => {
                                    setActiveMarket(market);
                                    const firstCat = Object.keys(markets[market])[0];
                                    setActiveCategory(firstCat);
                                }}
                            >
                                {market}
                            </button>
                        ))}
                    </div>
                    {/* Tabs de categorías */}
                    {activeMarket && (
                        <div className="flex gap-2 mb-6">
                            {Object.keys(markets[activeMarket]).map(cat => (
                                <button
                                    key={cat}
                                    className={`px-3 py-1 rounded font-mono text-xs transition-all ${activeCategory === cat ? 'bg-aethelgard-green/30 text-white' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}
                                    onClick={() => setActiveCategory(cat)}
                                >
                                    {cat}
                                </button>
                            ))}
                        </div>
                    )}
                    {/* Edición de categoría */}
                    {activeMarket && activeCategory && (
                        <div className="mb-4 flex flex-wrap gap-4 items-center">
                            <label className="flex items-center gap-2 text-xs">
                                <input
                                    type="checkbox"
                                    checked={markets[activeMarket][activeCategory].enabled !== false}
                                    onChange={e => handleCategoryField('enabled', e.target.checked)}
                                />
                                <span className="font-bold">Categoría activa</span>
                            </label>
                            <label className="flex items-center gap-2 text-xs">
                                Score mínimo:
                                <input
                                    type="number"
                                    value={markets[activeMarket][activeCategory].min_score ?? ''}
                                    onChange={e => handleCategoryField('min_score', parseFloat(e.target.value))}
                                    className="w-16 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white/80 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none"
                                />
                            </label>
                            <label className="flex items-center gap-2 text-xs">
                                Multiplicador riesgo:
                                <input
                                    type="number"
                                    value={markets[activeMarket][activeCategory].risk_multiplier ?? ''}
                                    onChange={e => handleCategoryField('risk_multiplier', parseFloat(e.target.value))}
                                    className="w-16 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white/80 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none"
                                />
                            </label>
                            <label className="flex items-center gap-2 text-xs">
                                Spread máx:
                                <input
                                    type="number"
                                    value={markets[activeMarket][activeCategory].max_spread ?? ''}
                                    onChange={e => handleCategoryField('max_spread', parseFloat(e.target.value))}
                                    className="w-16 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white/80 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none"
                                />
                            </label>
                        </div>
                    )}
                    {/* Tabla de instrumentos con edición de activo/inactivo */}
                    {activeMarket && activeCategory && (
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-sm text-white/80">
                                <thead>
                                    <tr className="border-b border-white/10">
                                        <th className="p-2 text-left">Símbolo</th>
                                        <th className="p-2 text-left">Activo</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {/* Mostrar TODOS los instrumentos, activos e inactivos */}
                                    {markets[activeMarket][activeCategory].instruments.map((symbol: string) => {
                                        const isActive = !markets[activeMarket][activeCategory].actives ||
                                            markets[activeMarket][activeCategory].actives[symbol] !== false;
                                        return (
                                            <tr key={symbol} className={`border-b border-white/10 hover:bg-white/5 ${!isActive ? 'opacity-50' : ''}`}>
                                                <td className="p-2 font-mono">{symbol}</td>
                                                <td className="p-2">
                                                    <input
                                                        type="checkbox"
                                                        checked={isActive}
                                                        onChange={e => handleInstrumentActive(symbol, e.target.checked)}
                                                        className="w-5 h-5 accent-aethelgard-green"
                                                    />
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                            {/* Agregar nuevo símbolo */}
                            <div className="flex gap-2 mt-4 items-center">
                                <input
                                    type="text"
                                    value={newSymbol}
                                    onChange={e => setNewSymbol(e.target.value)}
                                    placeholder="Nuevo símbolo (ej: EURUSD)"
                                    className="w-32 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white/80 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none"
                                />
                                <button
                                    onClick={handleAddSymbol}
                                    className="px-4 py-2 rounded-lg bg-aethelgard-green text-dark font-bold text-xs hover:scale-105 active:scale-95 transition-all"
                                >
                                    Agregar símbolo
                                </button>
                            </div>
                        </div>
                    )}
                </>
            )}
        </GlassPanel>
    );
}
