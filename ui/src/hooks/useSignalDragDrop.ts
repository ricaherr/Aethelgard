/**
 * HOOK: useSignalDragDrop (FIXED)
 * 
 * TRACE_ID: HOOK-DRAG-DROP-001-FIXED
 * Responsabilidad: Gestionar drag & drop de señales entre widgets
 */

import { useState, useCallback, useEffect } from 'react';
import { Signal } from '../types/aethelgard';

export interface DragDropState {
  draggedSignal: Signal | null;
  dropZoneTarget: string | null;
  dropZones: Map<string, Signal[]>;
  trace_id: string;
  timestamp: number;
}

export interface DragDropEvent {
  signal: Signal;
  sourceZone: string;
  targetZone: string;
  trace_id: string;
  timestamp: number;
  success: boolean;
  reason?: string;
}

export interface UseSignalDragDropReturn {
  state: DragDropState;
  onDragStart: (signal: Signal, sourceZone: string) => void;
  onDragOver: (targetZone: string) => void;
  onDrop: (targetZone: string) => void;
  onDragEnd: () => void;
  removeSignal: (zoneId: string, signalId: string) => void;
  clearZone: (zoneId: string) => void;
  getZoneSignals: (zoneId: string) => Signal[];
  lastEvent: DragDropEvent | null;
  isDragging: boolean;
}

const VALID_DROP_ZONES = new Set(['central-hud', 'timeline-widget', 'risk-widget', 'scanner-widget']);
const STORAGE_KEY = 'aethelgard-drag-state';
const MAX_SIGNALS_PER_ZONE = 10;

const generateTraceId = (): string => {
  return `DRAG-${Date.now()}-${Math.random().toString(36).substr(2, 9).toUpperCase()}`;
};

const isValidDropZone = (zone: string): boolean => VALID_DROP_ZONES.has(zone);

const persistState = (dropZones: Map<string, Signal[]>): void => {
  try {
    const stateToSave = {
      dropZones: Array.from(dropZones.entries()),
      lastUpdate: Date.now(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stateToSave));
  } catch (error) {
    console.error('[DragDrop] localStorage persist error:', error);
  }
};

const restoreState = (): Map<string, Signal[]> => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return new Map();

    const parsed = JSON.parse(stored);
    const entries: [string, Signal[]][] = parsed.dropZones || [];
    return new Map(entries);
  } catch (error) {
    console.error('[DragDrop] localStorage restore error:', error);
    return new Map();
  }
};

const initializeDropZones = (restored?: Map<string, Signal[]>): Map<string, Signal[]> => {
  if (restored && restored.size > 0) {
    return restored;
  }

  return new Map([
    ['central-hud', []],
    ['timeline-widget', []],
    ['risk-widget', []],
    ['scanner-widget', []],
  ]);
};

export const useSignalDragDrop = (): UseSignalDragDropReturn => {
  const restoredZones = restoreState();

  const [state, setState] = useState<DragDropState>({
    draggedSignal: null,
    dropZoneTarget: null,
    dropZones: initializeDropZones(restoredZones),
    trace_id: '',
    timestamp: 0,
  });

  const [lastEvent, setLastEvent] = useState<DragDropEvent | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const onDragStart = useCallback((signal: Signal, sourceZone: string): void => {
    const trace_id = generateTraceId();
    const timestamp = Date.now();

    setState((prev) => ({
      ...prev,
      draggedSignal: signal,
      trace_id,
      timestamp,
    }));

    setIsDragging(true);
  }, []);

  const onDragOver = useCallback((targetZone: string): void => {
    if (!isValidDropZone(targetZone)) {
      return;
    }

    setState((prev) => ({
      ...prev,
      dropZoneTarget: targetZone,
    }));
  }, []);

  const onDrop = useCallback((targetZone: string): void => {
    setState((prev) => {
      if (!prev.draggedSignal || !isValidDropZone(targetZone)) {
        return prev;
      }

      const currentSignals = prev.dropZones.get(targetZone) || [];

      if (currentSignals.length >= MAX_SIGNALS_PER_ZONE) {
        setLastEvent({
          signal: prev.draggedSignal,
          sourceZone: 'alpha-signals',
          targetZone,
          trace_id: prev.trace_id,
          timestamp: Date.now(),
          success: false,
          reason: `MAX_SIGNALS_REACHED_${MAX_SIGNALS_PER_ZONE}`,
        });

        return prev;
      }

      const updated = new Map(prev.dropZones);
      updated.set(targetZone, [...currentSignals, prev.draggedSignal]);

      setLastEvent({
        signal: prev.draggedSignal,
        sourceZone: 'alpha-signals',
        targetZone,
        trace_id: prev.trace_id,
        timestamp: Date.now(),
        success: true,
      });

      const newState = {
        ...prev,
        dropZones: updated,
      };

      persistState(newState.dropZones);

      return newState;
    });
  }, []);

  const onDragEnd = useCallback((): void => {
    setState((prev) => ({
      ...prev,
      draggedSignal: null,
      dropZoneTarget: null,
      trace_id: '',
    }));

    setIsDragging(false);
  }, []);

  const removeSignal = useCallback((zoneId: string, signalId: string): void => {
    setState((prev) => {
      const currentSignals = prev.dropZones.get(zoneId) || [];
      const filtered = currentSignals.filter((s) => s.id !== signalId);

      const updated = new Map(prev.dropZones);
      updated.set(zoneId, filtered);

      persistState(updated);

      return {
        ...prev,
        dropZones: updated,
      };
    });
  }, []);

  const clearZone = useCallback((zoneId: string): void => {
    setState((prev) => {
      const updated = new Map(prev.dropZones);
      updated.set(zoneId, []);

      persistState(updated);

      return {
        ...prev,
        dropZones: updated,
      };
    });
  }, []);

  const getZoneSignals = useCallback((zoneId: string): Signal[] => {
    return state.dropZones.get(zoneId) || [];
  }, [state.dropZones]);

  useEffect(() => {
    if (state.dropZones.size > 0) {
      persistState(state.dropZones);
    }
  }, [state.dropZones]);

  return {
    state,
    onDragStart,
    onDragOver,
    onDrop,
    onDragEnd,
    removeSignal,
    clearZone,
    getZoneSignals,
    lastEvent,
    isDragging,
  };
};
