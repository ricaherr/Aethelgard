import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import { cn } from '../../utils/cn'; // We need to create this utility

interface GlassPanelProps extends React.ComponentPropsWithoutRef<typeof motion.div> {
    children: ReactNode;
    className?: string;
    premium?: boolean;
}

export function GlassPanel({ children, className, premium = false, ...props }: GlassPanelProps) {
    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            {...props}
            className={cn(
                "rounded-2xl overflow-hidden backdrop-blur-xl border border-white/5",
                premium ? "glass-premium p-6" : "glass p-4",
                className
            )}
        >
            {children}
        </motion.div>
    );
}
