import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Send, CheckCircle, Loader, AlertCircle, ExternalLink, Copy } from 'lucide-react';
import { useApi } from '../../hooks/useApi';

export function TelegramSetup() {
    const { apiFetch } = useApi();
    const [botToken, setBotToken] = useState('');
    const [chatId, setChatId] = useState('');
    const [step, setStep] = useState<1 | 2 | 3 | 4>(1); // Wizard steps
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [botInfo, setBotInfo] = useState<any>(null);
    const [instructions, setInstructions] = useState<any>(null);

    const loadExistingConfig = useCallback(async () => {
        try {
            const response = await apiFetch('/api/config/notifications');
            if (response.ok) {
                const data = await response.json();
                if (data.data?.bot_token) {
                    setBotToken(data.data.bot_token);
                    setStep(2); // Si ya hay token, ir a paso 2
                }
                if (data.data?.basic_chat_id) {
                    setChatId(data.data.basic_chat_id);
                    setStep(4); // Si ya está todo configurado
                }
            }
        } catch (err) {
            console.error('Error loading config:', err);
        }
    }, [apiFetch]);

    const loadInstructions = useCallback(async () => {
        try {
            const response = await apiFetch('/api/telegram/instructions');
            if (response.ok) {
                const data = await response.json();
                setInstructions(data);
            }
        } catch (err) {
            console.error('Error loading instructions:', err);
        }
    }, [apiFetch]);

    // Load existing config
    useEffect(() => {
        loadExistingConfig();
        loadInstructions();
    }, [loadExistingConfig, loadInstructions]);

    const validateToken = async () => {
        if (!botToken || botToken.length < 40) {
            setError('Token inválido. Debe tener al menos 40 caracteres.');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await apiFetch('/api/telegram/validate', {
                method: 'POST',
                body: JSON.stringify({ bot_token: botToken })
            });

            const data = await response.json();

            if (data.status === 'success') {
                setBotInfo(data.bot_info);
                setSuccess(`✅ Bot validado: @${data.bot_info.username}`);
                setStep(2);
            } else {
                setError(data.error || 'Error validando token');
            }
        } catch (err: any) {
            setError('Error de red. Verifica tu conexión.');
        } finally {
            setLoading(false);
        }
    };

    const getChatId = async () => {
        setLoading(true);
        setError(null);

        try {
            const response = await apiFetch('/api/telegram/get-chat-id', {
                method: 'POST',
                body: JSON.stringify({ bot_token: botToken })
            });

            const data = await response.json();

            if (data.status === 'success') {
                setChatId(data.chat_info.chat_id);
                setSuccess(`✅ Chat ID detectado: ${data.chat_info.chat_id}`);
                setStep(3);
            } else if (data.status === 'waiting') {
                setError(data.message);
            } else {
                setError(data.error || 'No se pudo obtener Chat ID');
            }
        } catch (err: any) {
            setError('Error de red');
        } finally {
            setLoading(false);
        }
    };

    const sendTestMessage = async () => {
        setLoading(true);
        setError(null);

        try {
            const response = await apiFetch('/api/telegram/test', {
                method: 'POST',
                body: JSON.stringify({ bot_token: botToken, chat_id: chatId })
            });

            const data = await response.json();

            if (data.status === 'success') {
                setSuccess('✅ Mensaje de prueba enviado. ¡Revisa tu Telegram!');
                setStep(4);
            } else {
                setError(data.error || 'Error enviando mensaje');
            }
        } catch (err: any) {
            setError('Error de red');
        } finally {
            setLoading(false);
        }
    };

    const saveConfig = async () => {
        setLoading(true);
        setError(null);

        try {
            const response = await apiFetch('/api/telegram/save', {
                method: 'POST',
                body: JSON.stringify({
                    bot_token: botToken,
                    chat_id: chatId,
                    enabled: true
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                setSuccess('🎉 Configuración guardada. Telegram está listo.');
            } else {
                setError(data.error || 'Error guardando configuración');
            }
        } catch (err: any) {
            setError('Error de red');
        } finally {
            setLoading(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        setSuccess('📋 Copiado al portapapeles');
        setTimeout(() => setSuccess(null), 2000);
    };

    return (
        <div className="space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-2xl font-outfit font-bold text-white/90">Configuración de Telegram</h3>
                    <p className="text-sm text-white/40 mt-1">Recibe alertas de trading en tiempo real</p>
                </div>
                {step === 4 && (
                    <div className="flex items-center gap-2 px-4 py-2 bg-aethelgard-green/10 border border-aethelgard-green/20 rounded-lg">
                        <CheckCircle size={16} className="text-aethelgard-green" />
                        <span className="text-sm font-bold text-aethelgard-green">Configurado</span>
                    </div>
                )}
            </div>

            {/* Progress Steps */}
            <div className="flex items-center gap-3">
                {[1, 2, 3, 4].map((s) => (
                    <div key={s} className="flex items-center gap-3 flex-1">
                        <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-all ${step >= s
                                ? 'bg-aethelgard-green/20 border-aethelgard-green text-aethelgard-green'
                                : 'bg-white/5 border-white/10 text-white/30'
                            }`}>
                            {step > s ? <CheckCircle size={16} /> : <span className="text-xs font-bold">{s}</span>}
                        </div>
                        {s < 4 && <div className={`flex-1 h-0.5 ${step > s ? 'bg-aethelgard-green/30' : 'bg-white/10'}`} />}
                    </div>
                ))}
            </div>

            {/* Alerts */}
            {error && (
                <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex gap-3"
                >
                    <AlertCircle size={18} className="shrink-0" />
                    <span>{error}</span>
                </motion.div>
            )}

            {success && (
                <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 rounded-xl bg-aethelgard-green/10 border border-aethelgard-green/20 text-aethelgard-green text-sm flex gap-3"
                >
                    <CheckCircle size={18} className="shrink-0" />
                    <span>{success}</span>
                </motion.div>
            )}

            {/* Step 1: Get Bot Token */}
            {step === 1 && (
                <div className="space-y-6 p-6 rounded-xl bg-white/5 border border-white/5">
                    <div className="space-y-4">
                        <h4 className="font-bold text-aethelgard-blue text-sm">PASO 1: Crear tu Bot</h4>
                        <div className="space-y-3 text-sm text-white/60">
                            <p>1️⃣ Abre Telegram y busca <span className="font-mono text-white/80">@BotFather</span> (bot oficial con verificación azul)</p>
                            <p>2️⃣ Envía el comando <span className="font-mono text-white/80">/newbot</span> y sigue las instrucciones</p>
                            <p>3️⃣ BotFather te dará un <span className="font-bold text-aethelgard-green">token</span> (como: <span className="font-mono text-xs">123456789:ABCdefGH...</span>)</p>
                            <p>4️⃣ Copia todo el token y pégalo abajo</p>
                        </div>
                    </div>

                    <div className="space-y-3">
                        <label className="text-xs font-bold text-white/40 uppercase tracking-widest">Bot Token</label>
                        <input
                            type="password"
                            value={botToken}
                            onChange={(e) => setBotToken(e.target.value)}
                            placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-white/80 focus:bg-white/10 focus:border-aethelgard-blue/30 outline-none transition-all"
                        />
                    </div>

                    <button
                        onClick={validateToken}
                        disabled={loading || !botToken}
                        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-aethelgard-blue text-white font-bold hover:scale-105 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        {loading ? <Loader size={18} className="animate-spin" /> : <CheckCircle size={18} />}
                        {loading ? 'Validando...' : 'Validar Token'}
                    </button>
                </div>
            )}

            {/* Step 2: Get Chat ID */}
            {step === 2 && (
                <div className="space-y-6 p-6 rounded-xl bg-white/5 border border-white/5">
                    <div className="space-y-4">
                        <h4 className="font-bold text-aethelgard-blue text-sm">PASO 2: Obtener tu Chat ID</h4>
                        <div className="space-y-3 text-sm text-white/60">
                            <p>1️⃣ Abre Telegram y busca tu bot: <span className="font-mono text-white/80">@{botInfo?.username || 'tu_bot'}</span></p>
                            <p>2️⃣ Envía el mensaje <span className="font-mono text-white/80">/start</span> a tu bot</p>
                            <p>3️⃣ Haz clic en el botón de abajo para detectar automáticamente tu Chat ID</p>
                        </div>
                    </div>

                    <button
                        onClick={getChatId}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-aethelgard-green text-dark font-bold hover:scale-105 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        {loading ? <Loader size={18} className="animate-spin" /> : <Send size={18} />}
                        {loading ? 'Detectando...' : 'Obtener mi Chat ID'}
                    </button>
                </div>
            )}

            {/* Step 3: Send Test Message */}
            {step === 3 && (
                <div className="space-y-6 p-6 rounded-xl bg-white/5 border border-white/5">
                    <div className="space-y-4">
                        <h4 className="font-bold text-aethelgard-blue text-sm">PASO 3: Prueba de Conexión</h4>
                        <div className="flex items-center gap-3 p-4 bg-white/5 rounded-lg">
                            <span className="text-xs text-white/40 uppercase tracking-widest">Chat ID:</span>
                            <span className="font-mono text-sm text-white/80">{chatId}</span>
                            <button
                                onClick={() => copyToClipboard(chatId)}
                                className="ml-auto p-2 hover:bg-white/10 rounded-lg transition-all"
                            >
                                <Copy size={14} className="text-white/40" />
                            </button>
                        </div>
                    </div>

                    <button
                        onClick={sendTestMessage}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-aethelgard-blue text-white font-bold hover:scale-105 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        {loading ? <Loader size={18} className="animate-spin" /> : <Send size={18} />}
                        {loading ? 'Enviando...' : 'Enviar Mensaje de Prueba'}
                    </button>
                </div>
            )}

            {/* Step 4: Final Save */}
            {step === 4 && (
                <div className="space-y-6 p-6 rounded-xl bg-aethelgard-green/10 border border-aethelgard-green/20">
                    <div className="space-y-4">
                        <div className="flex items-center gap-3">
                            <CheckCircle size={24} className="text-aethelgard-green" />
                            <h4 className="font-bold text-aethelgard-green text-lg">¡Configuración Completa!</h4>
                        </div>
                        <p className="text-sm text-white/60">
                            Tu bot de Telegram está listo. Recibirás notificaciones cuando:
                        </p>
                        <ul className="space-y-2 text-sm text-white/60 list-disc list-inside">
                            <li>Cambie el régimen de mercado</li>
                            <li>Se detecte una señal de trading</li>
                            <li>Ocurra un evento importante del sistema</li>
                        </ul>
                    </div>

                    <div className="flex gap-3">
                        <button
                            onClick={sendTestMessage}
                            disabled={loading}
                            className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-white/10 text-white font-bold hover:bg-white/20 transition-all disabled:opacity-40"
                        >
                            <Send size={18} />
                            Enviar Otra Prueba
                        </button>
                        <button
                            onClick={saveConfig}
                            disabled={loading}
                            className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-aethelgard-green text-dark font-bold hover:scale-105 active:scale-95 transition-all disabled:opacity-40"
                        >
                            {loading ? <Loader size={18} className="animate-spin" /> : <CheckCircle size={18} />}
                            {loading ? 'Guardando...' : 'Guardar Configuración'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
