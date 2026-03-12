import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { ShadowInstance, ActionEvent, WebSocketShadowEvent, HealthStatus } from '../types/aethelgard';

interface ShadowContextType {
    instances: ShadowInstance[];
    setInstances: (instances: ShadowInstance[]) => void;
    updateInstance: (instance: ShadowInstance) => void;
    events: ActionEvent[];
    addEvent: (event: ActionEvent) => void;
    shadowModeActive: boolean;
    setBesPerformer: (instance: ShadowInstance | null) => void;
    bestPerformer: ShadowInstance | null;
}

const ShadowContext = createContext<ShadowContextType | undefined>(undefined);

export const ShadowProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [instances, setInstances] = useState<ShadowInstance[]>([]);
    const [events, setEvents] = useState<ActionEvent[]>([]);
    const [bestPerformer, setBestPerformer] = useState<ShadowInstance | null>(null);

    const updateInstance = useCallback((updatedInstance: ShadowInstance) => {
        setInstances((prev) =>
            prev.map((inst) =>
                inst.instance_id === updatedInstance.instance_id ? updatedInstance : inst
            )
        );
    }, []);

    const addEvent = useCallback((event: ActionEvent) => {
        setEvents((prev) => [event, ...prev.slice(0, 49)]); // Keep max 50 events
    }, []);

    const shadowModeActive = instances.some((i) => i.shadow_status !== 'DEAD');

    const value: ShadowContextType = {
        instances,
        setInstances,
        updateInstance,
        events,
        addEvent,
        shadowModeActive,
        setBesPerformer: setBestPerformer,
        bestPerformer,
    };

    return (
        <ShadowContext.Provider value={value}>
            {children}
        </ShadowContext.Provider>
    );
};

export const useShadow = (): ShadowContextType => {
    const context = useContext(ShadowContext);
    if (!context) {
        throw new Error('useShadow must be used within ShadowProvider');
    }
    return context;
};
