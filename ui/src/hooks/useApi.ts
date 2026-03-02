import { useCallback } from 'react';
import { useAuthContext } from '../contexts/AuthContext';

export function useApi() {
    const { isAuthenticated, logout, checkAuth } = useAuthContext();

    const apiFetch = useCallback(async (url: string, options: RequestInit = {}) => {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        try {
            const response = await fetch(url, {
                ...options,
                headers,
                credentials: 'include',  // Critical: HttpOnly cookies are sent automatically
            });

            if (response.status === 401) {
                console.warn('⚠️ Unauthorized access detected. Session might be expired.');
                // Try to refresh token
                try {
                    const refreshRes = await fetch('/api/auth/refresh', {
                        method: 'POST',
                        credentials: 'include',
                    });
                    
                    if (refreshRes.ok) {
                        // Re-validate auth state and retry request
                        await checkAuth();
                        // Retry original request
                        return fetch(url, {
                            ...options,
                            headers,
                            credentials: 'include',
                        });
                    } else {
                        // Refresh failed, logout
                        await logout();
                    }
                } catch (refreshError) {
                    console.error('Token refresh failed:', refreshError);
                    await logout();
                }
            }

            return response;
        } catch (error) {
            console.error(`❌ API Fetch Error (${url}):`, error);
            throw error;
        }
    }, [isAuthenticated, logout, checkAuth]);

    return { apiFetch };
}
