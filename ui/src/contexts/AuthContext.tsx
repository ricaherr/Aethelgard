import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { jwtDecode } from 'jwt-decode';

interface DecodedToken {
    sub: string;
    tid: string; // Backend uses 'tid' for tenant_id
    role?: string;
    exp: number;
}

interface AuthContextType {
    token: string | null;
    tenantId: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (newToken: string) => void;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [token, setToken] = useState<string | null>(localStorage.getItem('aethelgard_token'));
    const [tenantId, setTenantId] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);

    useEffect(() => {
        validateToken(token);
    }, [token]);

    const validateToken = (currentToken: string | null) => {
        if (!currentToken) {
            setIsAuthenticated(false);
            setTenantId(null);
            setIsLoading(false);
            return;
        }

        try {
            const decoded = jwtDecode<DecodedToken>(currentToken);
            const isExpired = decoded.exp * 1000 < Date.now();

            if (isExpired) {
                console.warn('⚠️ Session expired.');
                logout();
            } else {
                setTenantId(decoded.tid);
                setIsAuthenticated(true);
            }
        } catch (error) {
            console.error('❌ Session corrupted:', error);
            logout();
        }
        setIsLoading(false);
    };

    const login = (newToken: string) => {
        localStorage.setItem('aethelgard_token', newToken);
        setToken(newToken);
    };

    const logout = () => {
        localStorage.removeItem('aethelgard_token');
        setToken(null);
        setTenantId(null);
        setIsAuthenticated(false);
    };

    return (
        <AuthContext.Provider value={{ token, tenantId, isAuthenticated, isLoading, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuthContext() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuthContext must be used within an AuthProvider');
    }
    return context;
}
