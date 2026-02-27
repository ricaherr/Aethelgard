import { useAethelgardContext } from '../contexts/AethelgardContext';

/**
 * Enhanced hook that consumes the global Aethelgard context.
 * This ensures that there is only ONE WebSocket connection and ONE polling loop
 * for the entire application, resolving duplicate request issues.
 */
export function useAethelgard() {
    return useAethelgardContext();
}
