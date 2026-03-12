import React from 'react';
import { useShadow } from '../../contexts/ShadowContext';import styles from '../../styles/shadow.module.css';
const EdgeConciensiaBadge: React.FC = () => {
    const { shadowModeActive, bestPerformer } = useShadow();

    if (!shadowModeActive || !bestPerformer) {
        return null;
    }

    return (
        <div
            data-testid="edge-conciencia-badge"
            className="fixed top-4 right-4 px-3 py-2 rounded-lg border border-blue-500/40 backdrop-blur-md bg-blue-500/10 text-xs font-mono text-blue-300 whitespace-nowrap hover:border-blue-500/60 transition-all z-50"
            style={{
                borderWidth: '0.5px',
            }}
        >
            <div className="font-bold text-blue-400">SHADOW MODE</div>
            <div className="text-gray-400 mt-1">
                Best: {bestPerformer.instance_id} {bestPerformer.health_status === 'HEALTHY' ? '✅' : '🟡'}
            </div>
        </div>
    );
};

export default EdgeConciensiaBadge;
