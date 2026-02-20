import React, { useEffect, useState } from 'react';
import { Save, RefreshCw, Shield, AlertTriangle, CheckCircle } from 'lucide-react';

type BackupSettingsData = {
    enabled: boolean;
    backup_dir: string;
    interval_days: number;
    retention_days: number;
};

const DEFAULT_SETTINGS: BackupSettingsData = {
    enabled: true,
    backup_dir: 'backups',
    interval_days: 1,
    retention_days: 15
};

export function BackupSettings() {
    const [settings, setSettings] = useState<BackupSettingsData>(DEFAULT_SETTINGS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchSettings = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/backup/settings');
            if (!res.ok) throw new Error(`Error ${res.status}`);
            const data = await res.json();
            setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) });
        } catch (e: any) {
            setError(e.message || 'Failed to load backup settings');
        } finally {
            setLoading(false);
        }
    };

    const saveSettings = async () => {
        setSaving(true);
        setError(null);
        setMessage(null);
        try {
            const payload = {
                ...settings,
                interval_days: Math.max(1, Number(settings.interval_days) || 1),
                retention_days: Math.max(1, Number(settings.retention_days) || 1)
            };
            const res = await fetch('/api/backup/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error(`Error ${res.status}`);
            const data = await res.json();
            setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) });
            setMessage('Backup settings saved.');
            setTimeout(() => setMessage(null), 2500);
        } catch (e: any) {
            setError(e.message || 'Failed to save backup settings');
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => {
        fetchSettings();
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-48 text-white/40">
                <RefreshCw size={20} className="animate-spin mr-2" />
                Loading backup settings...
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-aethelgard-blue/20 text-aethelgard-blue">
                        <Shield size={20} />
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-white/90">Database Backup Policy</h3>
                        <p className="text-xs text-white/40 uppercase tracking-[0.2em]">
                            Defaults: backups / daily / 15 days
                        </p>
                    </div>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={fetchSettings}
                        className="p-2 rounded-lg bg-white/5 border border-white/10 text-white/50 hover:text-white/80"
                        title="Reload"
                    >
                        <RefreshCw size={16} />
                    </button>
                    <button
                        onClick={saveSettings}
                        disabled={saving}
                        className="px-4 py-2 rounded-lg bg-aethelgard-green text-dark font-bold flex items-center gap-2 disabled:opacity-60"
                    >
                        <Save size={16} />
                        {saving ? 'Saving...' : 'Save'}
                    </button>
                </div>
            </div>

            {message && (
                <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/10 text-green-300 text-sm flex items-center gap-2">
                    <CheckCircle size={16} />
                    {message}
                </div>
            )}

            {error && (
                <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-sm flex items-center gap-2">
                    <AlertTriangle size={16} />
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <Field label="Enabled">
                    <button
                        onClick={() => setSettings(prev => ({ ...prev, enabled: !prev.enabled }))}
                        className={`relative w-14 h-7 rounded-full transition-all ${settings.enabled ? 'bg-aethelgard-green' : 'bg-white/15'}`}
                    >
                        <div className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-all ${settings.enabled ? 'left-8' : 'left-1'}`} />
                    </button>
                </Field>

                <Field label="Backup Folder">
                    <input
                        value={settings.backup_dir}
                        onChange={(e) => setSettings(prev => ({ ...prev, backup_dir: e.target.value }))}
                        className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/80 w-full"
                    />
                </Field>

                <Field label="Interval (Days)">
                    <input
                        type="number"
                        min={1}
                        value={settings.interval_days}
                        onChange={(e) => setSettings(prev => ({ ...prev, interval_days: Number(e.target.value) }))}
                        className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/80 w-full"
                    />
                </Field>

                <Field label="Retention (Days)">
                    <input
                        type="number"
                        min={1}
                        value={settings.retention_days}
                        onChange={(e) => setSettings(prev => ({ ...prev, retention_days: Number(e.target.value) }))}
                        className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/80 w-full"
                    />
                </Field>
            </div>
        </div>
    );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col gap-2">
            <label className="text-[10px] font-bold text-white/40 uppercase tracking-[0.2em]">{label}</label>
            {children}
        </div>
    );
}
