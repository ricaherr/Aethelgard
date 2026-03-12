import React from 'react';
import { useShadow } from '../../contexts/ShadowContext';
import { ShadowInstance, HealthStatus } from '../../types/aethelgard';
import styles from '../../styles/shadow.module.css';

// Helper functions - moved outside component to avoid re-declaration issues
const getStatusColor = (health: HealthStatus): string => {
    switch (health) {
        case 'HEALTHY':
            return 'bg-emerald-500 text-white';
        case 'MONITOR':
            return 'bg-amber-500 text-white';
        case 'DEAD':
        case 'QUARANTINED':
            return 'bg-red-500 text-white';
        default:
            return 'bg-gray-500 text-white';
    }
};

const getStatusEmoji = (health: HealthStatus): string => {
    switch (health) {
        case 'HEALTHY':
            return '✅';
        case 'MONITOR':
            return '🟡';
        case 'DEAD':
            return '❌';
        case 'QUARANTINED':
            return '⚠️';
        default:
            return '❓';
    }
};

// Main component
const CompetitionDashboard: React.FC = () => {
    const { instances } = useShadow();
    const displayInstances = instances.slice(0, 6); // Show max 6 (3x2)

    return (
        <div data-testid="competition-dashboard" className="w-full">
            <h2 className="text-xl font-mono font-bold text-blue-400 mb-4">SHADOW POOL COMPETITION</h2>

            {displayInstances.length === 0 ? (
                <div className="text-center py-12 text-gray-400 font-mono text-sm">
                    No active SHADOW instances
                </div>
            ) : (
                <div className="grid gap-3 md:gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                    {displayInstances.map((instance: ShadowInstance) => (
                        <InstanceCard key={instance.instance_id} instance={instance} />
                    ))}
                </div>
            )}
        </div>
    );
};

interface InstanceCardProps {
    instance: ShadowInstance;
}

const InstanceCard: React.FC<InstanceCardProps> = ({ instance }) => {

    const getStatusColor = (health: HealthStatus): string => {
        switch (health) {
            case 'HEALTHY':
                return 'bg-emerald-500 text-white';
            case 'MONITOR':
                return 'bg-amber-500 text-white';
            case 'DEAD':
            case 'QUARANTINED':
                return 'bg-red-500 text-white';
            default:
                return 'bg-gray-500 text-white';
        }
    };

    const getStatusEmoji = (health: HealthStatus): string => {
        switch (health) {
            case 'HEALTHY':
                return '✅';
            case 'MONITOR':
                return '🟡';
            case 'DEAD':
                return '❌';
            case 'QUARANTINED':
                return '⚠️';
            default:
                return '❓';
        }
    };

    return (
        <div
            className="border border-blue-500/20 rounded-lg backdrop-blur-md bg-blue-500/5 p-4 hover:border-blue-500/40 transition-all"
            style={{
                borderWidth: '0.5px',
                fontFamily: 'JetBrains Mono, monospace',
            }}
        >
            <div className="flex justify-between items-start mb-3 pb-3 border-b border-blue-500/20">
                <div className="text-xs font-bold text-blue-300 truncate">
                    {instance.instance_id}
                </div>
                <span className={`px-2 py-1 rounded text-xs font-bold whitespace-nowrap ${getStatusColor(instance.health_status)}`}>
                    {getStatusEmoji(instance.health_status)} {instance.health_status}
                </span>
            </div>
            <div className="grid grid-cols-3 gap-2 mb-3">
                {[
                    { label: 'P1', status: instance.pilar1_status },
                    { label: 'P2', status: instance.pilar2_status },
                    { label: 'P3', status: instance.pilar3_status },
                ].map((pilar) => (
                    <div key={pilar.label} className="text-center">
                        <div className="text-xs text-gray-400 mb-1">{pilar.label}</div>
                        <div
                            className={`text-xs font-bold px-2 py-1 rounded ${
                                pilar.status === 'PASS'
                                    ? 'bg-green-500/20 text-green-400'
                                    : pilar.status === 'FAIL'
                                    ? 'bg-red-500/20 text-red-400'
                                    : 'bg-gray-500/20 text-gray-400'
                            }`}
                        >
                            {pilar.status === 'PASS' ? '✓' : pilar.status === 'FAIL' ? '✗' : '?'}
                        </div>
                    </div>
                ))}
            </div>

            {/* Key Metrics */}
            <div className="space-y-2 text-xs text-gray-300">
                <div className="flex justify-between">
                    <span className="text-gray-500">PF:</span>
                    <span className="font-bold text-amber-400">
                        {instance.metrics.profit_factor.toFixed(2)}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-500">WR:</span>
                    <span className="font-bold text-blue-400">
                        {(instance.metrics.win_rate * 100).toFixed(1)}%
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-500">DD:</span>
                    <span className="font-bold text-red-400">
                        {(instance.metrics.max_drawdown_pct * 100).toFixed(1)}%
                    </span>
                </div>
            </div>

            {/* Footer: Trade Count */}
            <div className="mt-3 pt-3 border-t border-blue-500/20 text-xs text-gray-500">
                Trades: {instance.metrics.total_trades_executed}
            </div>
        </div>
    );
};

export default CompetitionDashboard;
