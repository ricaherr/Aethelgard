import { useCallback } from 'react';
import { useAuthContext } from '../contexts/AuthContext';

export function useApi() {
    const { token, logout } = useAuthContext();

    const apiFetch = useCallback(async (url: string, options: RequestInit = {}) => {
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers,
        };

        try {
            const response = await fetch(url, { ...options, headers });

            if (response.status === 401) {
                console.warn('⚠️ Unauthorized access detected. Session might be expired.');
                // Optional: Trigger logout or refresh if 401 is persistent
                // logout(); 
            }

            return response;
        } catch (error) {
            console.error(`❌ API Fetch Error (${url}):`, error);
            throw error;
        }
    }, [token, logout]);

    return { apiFetch };
}
