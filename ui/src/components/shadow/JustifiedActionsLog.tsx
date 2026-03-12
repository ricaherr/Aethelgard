import React, { useMemo } from 'react';
import { useShadow } from '../../contexts/ShadowContext';
import styles from '../../styles/shadow.module.css';

const JustifiedActionsLog: React.FC = () => {
    const { events } = useShadow();

    const getActionColor = (action: string): string => {
        switch (action) {
            case 'PROMOTION':
                return 'text-green-400';
            case 'DEMOTION':
                return 'text-red-400';
            case 'QUARANTINE':
                return 'text-amber-400';
            case 'MONITOR':
                return 'text-blue-400';
            default:
                return 'text-gray-400';
        }
    };

    const getActionEmoji = (action: string): string => {
        switch (action) {
            case 'PROMOTION':
                return '⬆️';
            case 'DEMOTION':
                return '⬇️';
            case 'QUARANTINE':
                return '🔒';
            case 'MONITOR':
                return '👁️';
            default:
                return '📝';
        }
    };

    return (
        <div
            data-testid="justified-actions-log"
            className="w-full border border-blue-500/20 rounded-lg backdrop-blur-md bg-blue-500/5 p-4 overflow-y-auto"
            style={{
                maxHeight: '400px',
                borderWidth: '0.5px',
            }}
        >
            <h3 className="text-sm font-mono font-bold text-blue-400 mb-3">JUSTIFIED ACTIONS LOG</h3>

            {events.length === 0 ? (
                <div className="text-xs text-gray-500 font-mono">No events yet</div>
            ) : (
                <div className="space-y-2">
                    {events.map((event) => (
                        <ActionEventRow
                            key={event.id}
                            event={event}
                            getActionColor={getActionColor}
                            getActionEmoji={getActionEmoji}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

interface ActionEventRowProps {
    event: any; // ActionEvent type
    getActionColor: (action: string) => string;
    getActionEmoji: (action: string) => string;
}

const ActionEventRow: React.FC<ActionEventRowProps> = ({ event, getActionColor, getActionEmoji }) => {
    const timestamp = new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false });
    const truncatedTraceId = event.trace_id.substring(0, 20) + '...';

    return (
        <div
            className="text-xs text-gray-300 font-mono border-b border-blue-500/10 pb-2 hover:bg-blue-500/5 -mx-2 px-2 py-1 rounded transition-colors"
            data-testid="action-item"
        >
            <div className="flex justify-between gap-2">
                <span className="text-gray-500">{timestamp}</span>
                <span className={`font-bold ${getActionColor(event.action)}`}>
                    {getActionEmoji(event.action)} {event.action}
                </span>
                <span className="text-blue-400">{event.instance_id}</span>
            </div>
            <div className="flex gap-2 mt-1">
                <a
                    href="#"
                    className="text-blue-500 hover:text-blue-300 hover:underline truncate max-w-xs"
                    title={event.trace_id}
                >
                    {truncatedTraceId}
                </a>
            </div>
            {event.message && (
                <div className="text-gray-500 italic mt-1 text-xs">{event.message}</div>
            )}
        </div>
    );
};

export default JustifiedActionsLog;
