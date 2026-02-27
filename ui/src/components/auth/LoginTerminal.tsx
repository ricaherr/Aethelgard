import { useState } from 'react';
import { motion } from 'framer-motion';
import { Lock, User, Terminal, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export function LoginTerminal() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const { login } = useAuth();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsSubmitting(true);

        try {
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);

            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData.toString()
            });

            if (res.ok) {
                const data = await res.json();
                login(data.access_token);
                // The AuthGuard will automatically re-render and show the dashboard
            } else {
                const errorData = await res.json();
                setError(errorData.detail || 'Access Denied: Invalid Credentials');
            }
        } catch (err) {
            setError('Connection Error: Cerebro not reachable');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen w-full bg-[#050505] flex items-center justify-center overflow-hidden relative">
            {/* Background Effects */}
            <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-aethelgard-cyan/5 blur-[120px] rounded-full pointer-events-none" />
            <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-aethelgard-red/5 blur-[100px] rounded-full pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="w-full max-w-md p-8 glass-premium rounded-2xl relative z-10"
            >
                <div className="flex flex-col items-center mb-8">
                    <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-aethelgard-cyan/20 to-aethelgard-blue/5 border border-aethelgard-cyan/30 flex items-center justify-center mb-4 shadow-[0_0_30px_rgba(0,242,255,0.1)]">
                        <Terminal size={32} className="text-aethelgard-cyan" />
                    </div>
                    <h1 className="font-outfit text-2xl font-bold tracking-tight text-white/90">AETHELGARD CORE</h1>
                    <p className="text-[10px] text-white/30 uppercase tracking-[0.3em] font-mono mt-1">Intelligence Terminal v2.0</p>
                </div>

                <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                    <div className="relative group">
                        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-white/20 group-focus-within:text-aethelgard-cyan transition-colors">
                            <User size={18} />
                        </div>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder="USER ID"
                            className="w-full bg-black/40 border border-white/10 rounded-xl px-12 py-4 text-sm font-mono text-white/80 placeholder:text-white/20 focus:outline-none focus:border-aethelgard-cyan/50 focus:bg-aethelgard-cyan/5 transition-all"
                            required
                        />
                    </div>

                    <div className="relative group">
                        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-white/20 group-focus-within:text-aethelgard-cyan transition-colors">
                            <Lock size={18} />
                        </div>
                        <input
                            type={showPassword ? 'text' : 'password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="PASSWORD"
                            className="w-full bg-black/40 border border-white/10 rounded-xl px-12 py-4 text-sm font-mono text-white/80 placeholder:text-white/20 focus:outline-none focus:border-aethelgard-cyan/50 focus:bg-aethelgard-cyan/5 transition-all"
                            required
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="absolute right-4 top-1/2 -translate-y-1/2 text-white/20 hover:text-aethelgard-cyan transition-colors"
                        >
                            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>

                    {error && (
                        <motion.div
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="text-aethelgard-red text-xs font-mono bg-aethelgard-red/10 border border-aethelgard-red/20 p-3 rounded-lg flex items-center justify-center text-center"
                        >
                            {error}
                        </motion.div>
                    )}

                    <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        disabled={isSubmitting}
                        className="w-full mt-4 bg-aethelgard-cyan/10 hover:bg-aethelgard-cyan/20 border border-aethelgard-cyan/30 text-aethelgard-cyan font-mono font-bold text-sm py-4 rounded-xl transition-all shadow-[0_0_20px_rgba(0,242,255,0.1)] hover:shadow-[0_0_30px_rgba(0,242,255,0.2)] disabled:opacity-50"
                    >
                        {isSubmitting ? 'VERIFYING...' : 'SIGN IN'}
                    </motion.button>
                </form>

                <div className="mt-8 pt-6 border-t border-white/5 text-center">
                    <p className="text-[10px] text-white/20 font-mono tracking-widest">SECURE 256-BIT ENCRYPTION • RESTRICTED ACCESS</p>
                </div>
            </motion.div>
        </div>
    );
}
