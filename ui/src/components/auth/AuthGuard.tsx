import { FC, ReactNode } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { LoginTerminal } from './LoginTerminal';
import { motion } from 'framer-motion';

interface AuthGuardProps {
    children: ReactNode;
}

export const AuthGuard: FC<AuthGuardProps> = ({ children }) => {
    const { isAuthenticated, isLoading } = useAuth();

    if (isLoading) {
        return (
            <div className="min-h-screen bg-[#050505] flex items-center justify-center font-mono">
                <motion.div
                    animate={{ opacity: [0.2, 1, 0.2] }}
                    transition={{ repeat: Infinity, duration: 1.5 }}
                    className="text-aethelgard-cyan text-sm tracking-widest"
                >
                    INITIALIZING CORTEX...
                </motion.div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <LoginTerminal />;
    }

    return <>{children}</>;
};
