import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Cpu,
    ShieldCheck,
    Zap,
    ChevronRight,
    ChevronLeft,
    Server,
    Key,
    Activity,
    CheckCircle2,
    AlertCircle,
    Globe
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';

interface ProviderTemplate {
    id: string;
    name: string;
    icon: string; // Placeholder for icon name or URL
    description: string;
}

const PROVIDERS: ProviderTemplate[] = [
    { id: 'mt5', name: 'MetaTrader 5', icon: 'MT5', description: 'Standard Retail/Institutional Terminal' },
    { id: 'oanda', name: 'OANDA', icon: 'FX', description: 'REST API v20 / Low Latency' },
    { id: 'binance', name: 'Binance', icon: 'CRYPTO', description: 'Spot & Futures WebSocket Engine' },
    { id: 'interactive', name: 'Interactive Brokers', icon: 'IBKR', description: 'TWS / Gateway Institutional' }
];

export function ConnectivityHub() {
    const [step, setStep] = useState(1);
    const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
    const [credentials, setCredentials] = useState<Record<string, string>>({});
    const [isValidating, setIsValidating] = useState(false);
    const [validationResult, setValidationResult] = useState<{ success: boolean, msg: string } | null>(null);

    const nextStep = () => setStep(prev => Math.min(prev + 1, 3));
    const prevStep = () => setStep(prev => Math.max(prev - 1, 1));

    const handleValidate = async () => {
        setIsValidating(true);
        setValidationResult(null);

        // Simulating backend validation
        await new Promise(r => setTimeout(r, 2000));

        setIsValidating(false);
        setValidationResult({
            success: true,
            msg: `Satellite ${selectedProvider?.toUpperCase()} successfully synchronized with Aethelgard.db`
        });
    };

    return (
        <div className="space-y-8">
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-4">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="flex items-center gap-2">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-all duration-500 ${step >= i ? 'bg-aethelgard-blue text-dark shadow-[0_0_15px_rgba(0,210,255,0.4)]' : 'bg-white/5 text-white/20'
                                }`}>
                                {i}
                            </div>
                            {i < 3 && <div className={`w-8 h-0.5 rounded-full ${step > i ? 'bg-aethelgard-blue' : 'bg-white/5'}`} />}
                        </div>
                    ))}
                </div>
                <div className="text-right">
                    <span className="text-[10px] font-black text-white/30 uppercase tracking-[0.3em]">Module Status</span>
                    <p className="text-xs font-mono text-aethelgard-blue font-bold tracking-widest uppercase italic">Provisioning Mode</p>
                </div>
            </div>

            <AnimatePresence mode="wait">
                {step === 1 && (
                    <motion.div
                        key="step1"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        className="space-y-6"
                    >
                        <header>
                            <h3 className="text-lg font-black text-white italic uppercase tracking-tighter">Paso 1: Selección de Proveedor</h3>
                            <p className="text-xs text-white/40 uppercase tracking-widest mt-1">Select your communication satellite type</p>
                        </header>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {PROVIDERS.map(p => (
                                <button
                                    key={p.id}
                                    onClick={() => setSelectedProvider(p.id)}
                                    className={`p-6 rounded-2xl border transition-all duration-500 text-left group flex items-start gap-4 ${selectedProvider === p.id
                                        ? 'bg-aethelgard-blue/10 border-aethelgard-blue/50 shadow-[0_0_20px_rgba(0,210,255,0.15)]'
                                        : 'bg-white/[0.02] border-white/5 hover:border-white/10 hover:bg-white/[0.04]'
                                        }`}
                                >
                                    <div className={`p-3 rounded-xl border transition-all duration-500 ${selectedProvider === p.id ? 'bg-aethelgard-blue/20 border-aethelgard-blue/30 text-aethelgard-blue' : 'bg-white/5 border-white/5 text-white/40'
                                        }`}>
                                        <Server size={24} />
                                    </div>
                                    <div>
                                        <h4 className={`font-bold uppercase tracking-tight ${selectedProvider === p.id ? 'text-white' : 'text-white/60'}`}>{p.name}</h4>
                                        <p className="text-[10px] text-white/30 uppercase tracking-widest mt-1">{p.description}</p>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}

                {step === 2 && (
                    <motion.div
                        key="step2"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        className="space-y-6"
                    >
                        <header>
                            <h3 className="text-lg font-black text-white italic uppercase tracking-tighter">Paso 2: Credenciales de Enlace</h3>
                            <p className="text-xs text-white/40 uppercase tracking-widest mt-1">Configuring {selectedProvider?.toUpperCase()} authentication layer</p>
                        </header>

                        <div className="space-y-4 max-w-xl">
                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-white/30 uppercase tracking-[0.2em]">Satellite ID / Login</label>
                                <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-black/40 border border-white/5 focus-within:border-aethelgard-blue/30 transition-all">
                                    <Cpu size={16} className="text-white/20" />
                                    <input
                                        type="text"
                                        placeholder="Identification code..."
                                        className="bg-transparent border-none outline-none text-sm font-mono text-white/80 w-full"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-white/30 uppercase tracking-[0.2em]">Secret Key / Password</label>
                                <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-black/40 border border-white/5 focus-within:border-aethelgard-blue/30 transition-all">
                                    <Key size={16} className="text-white/20" />
                                    <input
                                        type="password"
                                        placeholder="AES-256 encrypted password..."
                                        className="bg-transparent border-none outline-none text-sm font-mono text-white/80 w-full"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-white/30 uppercase tracking-[0.2em]">Uplink Server</label>
                                <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-black/40 border border-white/5 focus-within:border-aethelgard-blue/30 transition-all">
                                    <Globe size={16} className="text-white/20" />
                                    <input
                                        type="text"
                                        placeholder="Provider endpoint..."
                                        className="bg-transparent border-none outline-none text-sm font-mono text-white/80 w-full"
                                    />
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}

                {step === 3 && (
                    <motion.div
                        key="step3"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        className="space-y-8 flex flex-col items-center py-10"
                    >
                        <div className="relative">
                            <div className={`w-36 h-36 rounded-full border-4 border-dashed animate-[spin_10s_linear_infinite] ${isValidating ? 'border-aethelgard-blue/40' : 'border-white/5'}`} />
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className={`w-24 h-24 rounded-full flex items-center justify-center transition-all duration-700 shadow-2xl ${validationResult?.success ? 'bg-aethelgard-green/20 text-aethelgard-green shadow-aethelgard-green/20' : 'bg-aethelgard-blue/20 text-aethelgard-blue shadow-aethelgard-blue/20'
                                    }`}>
                                    {isValidating ? <Activity className="animate-pulse" size={40} /> : (validationResult?.success ? <CheckCircle2 size={40} /> : <Zap size={40} />)}
                                </div>
                            </div>
                        </div>

                        <div className="text-center space-y-3">
                            <h3 className="text-xl font-black text-white italic uppercase tracking-tighter">
                                {isValidating ? 'Probando Latencia...' : (validationResult?.success ? 'Validation Successful' : 'Paso 3: Validación')}
                            </h3>
                            <p className="text-xs text-white/40 uppercase tracking-[0.3em] max-w-sm mx-auto">
                                {isValidating ? 'Calculating route to provider and verifying credential matrix' : 'Running integrity check against provider endpoint'}
                            </p>

                            {validationResult && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className={`mt-6 p-4 rounded-xl border font-mono text-[11px] uppercase tracking-widest ${validationResult.success ? 'bg-aethelgard-green/10 border-aethelgard-green/20 text-aethelgard-green' : 'bg-red-500/10 border-red-500/20 text-red-500'
                                        }`}
                                >
                                    {validationResult.msg}
                                </motion.div>
                            )}
                        </div>

                        <button
                            onClick={handleValidate}
                            disabled={isValidating || validationResult?.success}
                            className={`px-10 py-4 rounded-2xl font-black uppercase tracking-widest transition-all ${validationResult?.success
                                ? 'bg-white/5 text-white/20 cursor-not-allowed border border-white/5'
                                : 'bg-aethelgard-blue text-dark hover:scale-105 active:scale-95 shadow-[0_0_30px_rgba(0,210,255,0.3)]'
                                }`}
                        >
                            {isValidating ? 'Validating Link...' : 'Execute Pulse Check'}
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="flex justify-between items-center pt-8 border-t border-white/5 mt-auto">
                <button
                    onClick={prevStep}
                    disabled={step === 1}
                    className={`flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] transition-all ${step === 1 ? 'text-white/10' : 'text-white/40 hover:text-white'
                        }`}
                >
                    <ChevronLeft size={16} />
                    Regresar
                </button>

                <button
                    onClick={nextStep}
                    disabled={step === 3 || (step === 1 && !selectedProvider)}
                    className={`flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] transition-all ${(step === 3 || (step === 1 && !selectedProvider)) ? 'text-white/10' : 'text-aethelgard-blue hover:text-white'
                        }`}
                >
                    Siguiente Paso
                    <ChevronRight size={16} />
                </button>
            </div>
        </div>
    );
}
