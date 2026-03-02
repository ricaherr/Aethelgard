import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface AuthContextType {
    userId: string | null;
    email: string | null;
    tenantId: string | null;
    role: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (userId: string, tenantId: string, email: string, role: string) => void;
    logout: () => Promise<void>;
    checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [userId, setUserId] = useState<string | null>(null);
    const [email, setEmail] = useState<string | null>(null);
    const [tenantId, setTenantId] = useState<string | null>(null);
    const [role, setRole] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);

    // On mount, check if user has valid HttpOnly cookie session
    useEffect(() => {
        checkAuth();
    }, []);

    const checkAuth = async () => {
        try {
            const res = await fetch('/api/auth/me', {
                credentials: 'include',  // Critical: send HttpOnly cookies
            });

            if (res.ok) {
                const data = await res.json();
                setUserId(data.user_id);
                setEmail(data.email);
                setTenantId(data.tenant_id);
                setRole(data.role);
                setIsAuthenticated(true);
            } else {
                // No valid session
                setIsAuthenticated(false);
                setUserId(null);
                setEmail(null);
                setTenantId(null);
                setRole(null);
            }
        } catch (error) {
            console.error('❌ Auth check failed:', error);
            setIsAuthenticated(false);
        } finally {
            setIsLoading(false);
        }
    };

    const login = (userId: string, tenantId: string, email: string, role: string) => {
        setUserId(userId);
        setEmail(email);
        setTenantId(tenantId);
        setRole(role);
        setIsAuthenticated(true);
    };

    const logout = async () => {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include',  // Critical: send HttpOnly cookies for revocation
            });
        } catch (error) {
            console.error('❌ Logout failed:', error);
        } finally {
            setIsAuthenticated(false);
            setUserId(null);
            setEmail(null);
            setTenantId(null);
            setRole(null);
        }
    };

    return (
        <AuthContext.Provider value={{ userId, email, tenantId, role, isAuthenticated, isLoading, login, logout, checkAuth }}>
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
