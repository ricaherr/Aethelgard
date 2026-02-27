import React, { useState, useEffect, useCallback } from 'react';
import { User, ChevronDown } from 'lucide-react';
import { useApi } from '../../hooks/useApi';

// ... interfaces ...

interface Profile {
    profile_type: string;
    auto_trading_enabled: boolean;
    notify_signals: boolean;
    notify_executions: boolean;
    notify_threshold_score: number;
    default_view: string;
    require_confirmation: boolean;
    max_daily_trades?: number;
    auto_trading_max_risk?: number;
}

interface ProfileSelectorProps {
    currentProfile: string;
    onProfileChange: (profileType: string) => void;
}

const PROFILE_LABELS: Record<string, string> = {
    explorer: '🌱 Explorador',
    active_trader: '📈 Trader Activo',
    analyst: '🔬 Analista',
    scalper: '🎯 Scalper',
    custom: '⚙️ Personalizado'
};

const PROFILE_DESCRIPTIONS: Record<string, string> = {
    explorer: 'Vista simplificada para aprender',
    active_trader: 'Balance entre análisis y acción',
    analyst: 'Análisis profundo y detallado',
    scalper: 'Ejecución rápida, alta frecuencia',
    custom: 'Configuración personalizada'
};

export const ProfileSelector: React.FC<ProfileSelectorProps> = ({
    currentProfile,
    onProfileChange
}) => {
    const { apiFetch } = useApi();
    const [isOpen, setIsOpen] = useState(false);
    const [profiles, setProfiles] = useState<Record<string, Profile>>({});
    const [loading, setLoading] = useState(true);

    const fetchProfiles = useCallback(async () => {
        try {
            const response = await apiFetch('/api/user/profiles');
            const data = await response.json();
            setProfiles(data.profiles);
        } catch (error) {
            console.error('Error fetching profiles:', error);
        } finally {
            setLoading(false);
        }
    }, [apiFetch]);

    useEffect(() => {
        fetchProfiles();
    }, [fetchProfiles]);

    const handleProfileSelect = async (profileType: string) => {
        setIsOpen(false);
        onProfileChange(profileType);

        // Actualizar preferencias del usuario
        try {
            const profileConfig = profiles[profileType];

            // Enviar user_id + todos los campos del perfil
            const payload = {
                user_id: 'default',
                ...profileConfig
            };

            const response = await apiFetch('/api/user/preferences', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Error updating profile:', errorText);
            }
        } catch (error) {
            console.error('Error updating profile:', error);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg">
                <User className="w-5 h-5 text-gray-400" />
                <span className="text-sm text-gray-400">Cargando...</span>
            </div>
        );
    }

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
                <User className="w-5 h-5 text-blue-400" />
                <div className="flex flex-col items-start">
                    <span className="text-sm font-medium text-white">
                        {PROFILE_LABELS[currentProfile] || 'Perfil'}
                    </span>
                    <span className="text-xs text-gray-400">
                        {PROFILE_DESCRIPTIONS[currentProfile]}
                    </span>
                </div>
                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-10"
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute top-full left-0 mt-2 w-80 bg-gray-800 rounded-lg shadow-xl border border-gray-700 z-20">
                        <div className="p-2">
                            <div className="text-xs font-semibold text-gray-400 px-3 py-2">
                                SELECCIONAR PERFIL
                            </div>
                            {Object.keys(PROFILE_LABELS).map((profileType) => (
                                <button
                                    key={profileType}
                                    onClick={() => handleProfileSelect(profileType)}
                                    className={`w-full flex items-start gap-3 px-3 py-3 rounded-lg transition-colors ${currentProfile === profileType
                                        ? 'bg-blue-600 text-white'
                                        : 'hover:bg-gray-700 text-gray-200'
                                        }`}
                                >
                                    <div className="flex-1 text-left">
                                        <div className="font-medium text-sm">
                                            {PROFILE_LABELS[profileType]}
                                        </div>
                                        <div className={`text-xs mt-1 ${currentProfile === profileType ? 'text-blue-100' : 'text-gray-400'
                                            }`}>
                                            {PROFILE_DESCRIPTIONS[profileType]}
                                        </div>
                                    </div>
                                    {currentProfile === profileType && (
                                        <div className="flex-shrink-0 w-2 h-2 bg-white rounded-full mt-1.5" />
                                    )}
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};
