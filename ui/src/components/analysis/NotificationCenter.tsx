import React, { useState, useEffect, useCallback } from 'react';
import { Bell, X, AlertTriangle, Info, CheckCircle, TrendingUp } from 'lucide-react';
import { useApi } from '../../hooks/useApi';

interface Notification {
    id: string;
    category: 'signal' | 'execution' | 'risk' | 'regime' | 'position' | 'system';
    priority: 'critical' | 'high' | 'medium' | 'low';
    title: string;
    message: string;
    timestamp: string;
    read: boolean;
    actions?: Array<{ label: string; action: string }>;
    details?: any;
}

export const NotificationCenter: React.FC = () => {
    const { apiFetch } = useApi();
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const [loading, setLoading] = useState(false);

    const fetchNotifications = useCallback(async () => {
        try {
            setLoading(true);
            const response = await apiFetch('/api/notifications/unread?user_id=default');
            if (response.ok) {
                const data = await response.json();
                setNotifications(data.notifications || []);
            }
        } catch (error) {
            console.error('Error fetching notifications:', error);
        } finally {
            setLoading(false);
        }
    }, [apiFetch]);

    useEffect(() => {
        fetchNotifications();
        const interval = setInterval(fetchNotifications, 30000); // Refresh cada 30s
        return () => clearInterval(interval);
    }, [fetchNotifications]);

    const markAsRead = async (notificationId: string) => {
        try {
            const response = await apiFetch(`/api/notifications/${notificationId}/mark-read`, {
                method: 'POST'
            });
            if (response.ok) {
                setNotifications(prev => prev.filter(n => n.id !== notificationId));
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    };

    const getPriorityColor = (priority: string) => {
        switch (priority) {
            case 'critical': return 'bg-red-600';
            case 'high': return 'bg-orange-600';
            case 'medium': return 'bg-yellow-600';
            case 'low': return 'bg-blue-600';
            default: return 'bg-gray-600';
        }
    };

    const getCategoryIcon = (category: string) => {
        switch (category) {
            case 'signal': return <TrendingUp className="w-5 h-5" />;
            case 'execution': return <CheckCircle className="w-5 h-5" />;
            case 'risk': return <AlertTriangle className="w-5 h-5" />;
            case 'regime': return <Info className="w-5 h-5" />;
            default: return <Bell className="w-5 h-5" />;
        }
    };

    const unreadCount = notifications.length;

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="relative p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
            >
                <Bell className="w-6 h-6 text-gray-300" />
                {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 flex items-center justify-center w-5 h-5 bg-red-600 text-white text-xs font-bold rounded-full">
                        {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-10"
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute top-full right-0 mt-2 w-96 max-h-[600px] bg-gray-800 rounded-lg shadow-xl border border-gray-700 z-20 overflow-hidden flex flex-col">
                        <div className="flex items-center justify-between p-4 border-b border-gray-700">
                            <div className="flex items-center gap-2">
                                <Bell className="w-5 h-5 text-blue-400" />
                                <h3 className="font-semibold text-white">Notificaciones</h3>
                                {unreadCount > 0 && (
                                    <span className="px-2 py-0.5 bg-red-600 text-white text-xs rounded-full">
                                        {unreadCount}
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={() => setIsOpen(false)}
                                className="text-gray-400 hover:text-white transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto">
                            {loading ? (
                                <div className="flex items-center justify-center p-8">
                                    <div className="text-gray-400">Cargando...</div>
                                </div>
                            ) : notifications.length === 0 ? (
                                <div className="flex flex-col items-center justify-center p-8 text-center">
                                    <Bell className="w-12 h-12 text-gray-600 mb-3" />
                                    <p className="text-gray-400">No hay notificaciones</p>
                                </div>
                            ) : (
                                <div className="divide-y divide-gray-700">
                                    {notifications.map((notification) => (
                                        <div
                                            key={notification.id}
                                            className="p-4 hover:bg-gray-750 transition-colors"
                                        >
                                            <div className="flex items-start gap-3">
                                                <div className={`flex-shrink-0 p-2 rounded-lg ${getPriorityColor(notification.priority)}`}>
                                                    {getCategoryIcon(notification.category)}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-start justify-between gap-2">
                                                        <h4 className="font-semibold text-white text-sm">
                                                            {notification.title}
                                                        </h4>
                                                        <button
                                                            onClick={() => markAsRead(notification.id)}
                                                            className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                    <p className="text-sm text-gray-300 mt-1 whitespace-pre-line">
                                                        {notification.message}
                                                    </p>
                                                    <div className="text-xs text-gray-500 mt-2">
                                                        {new Date(notification.timestamp).toLocaleString('es-ES', {
                                                            hour: '2-digit',
                                                            minute: '2-digit',
                                                            day: '2-digit',
                                                            month: 'short'
                                                        })}
                                                    </div>
                                                    {notification.actions && notification.actions.length > 0 && (
                                                        <div className="flex gap-2 mt-3">
                                                            {notification.actions.map((action, idx) => (
                                                                <button
                                                                    key={idx}
                                                                    className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg transition-colors"
                                                                >
                                                                    {action.label}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};
