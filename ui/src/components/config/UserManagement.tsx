import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Edit, Check, X, AlertTriangle, Mail, Shield } from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { useApi } from '../../hooks/useApi';

interface User {
  id: string;
  email: string;
  role: 'admin' | 'trader';
  status: 'active' | 'suspended' | 'deleted';
  tier: 'BASIC' | 'PREMIUM' | 'INSTITUTIONAL';
  created_at: string;
  updated_at: string;
}

interface CreateUserForm {
  email: string;
  password: string;
  role: 'admin' | 'trader';
  tier: 'BASIC' | 'PREMIUM' | 'INSTITUTIONAL';
}

interface EditingUser {
  id: string;
  role?: 'admin' | 'trader';
  status?: 'active' | 'suspended';
  tier?: 'BASIC' | 'PREMIUM' | 'INSTITUTIONAL';
}

interface ApiResponse {
  status: string;
  message?: string;
  users?: User[];
  user?: User;
  count?: number;
}

export function UserManagement() {
  const { apiFetch } = useApi();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingUser, setEditingUser] = useState<EditingUser | null>(null);
  const [currentUser, setCurrentUser] = useState<string | null>(null);

  const [createForm, setCreateForm] = useState<CreateUserForm>({
    email: '',
    password: '',
    role: 'trader',
    tier: 'BASIC'
  });

  // Cargar usuario actual (para bloquear self-modification)
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      try {
        const decoded = JSON.parse(atob(token.split('.')[1]));
        setCurrentUser(decoded.sub || null);
      } catch (e) {
        console.warn('[UserManagement] Could not decode token');
      }
    }
  }, []);

  // Cargar lista de usuarios
  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch('/api/admin/users');
      if (!response.ok) {
        if (response.status === 403) {
          throw new Error('Acceso denegado: Se requiere rol ADMIN');
        }
        throw new Error(`Error ${response.status}: No se pudieron cargar usuarios`);
      }

      const data: User[] = await response.json();
      // Filtrar usuarios eliminados
      const activeUsers = data.filter((u: User) => u.status !== 'deleted');
      setUsers(activeUsers);
    } catch (err: any) {
      setError(err.message || 'Error cargando usuarios');
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // Crear usuario
  const handleCreateUser = async () => {
    if (!createForm.email || !createForm.password) {
      setError('Email y contraseña son requeridos');
      return;
    }

    try {
      const response = await apiFetch('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify(createForm)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error ${response.status}`);
      }

      const newUser: User = await response.json();
      setUsers([...users, newUser]);
      setCreateForm({ email: '', password: '', role: 'trader', tier: 'BASIC' });
      setShowCreateForm(false);
      setMessage(`✅ Usuario ${createForm.email} creado correctamente`);
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setError(err.message || 'Error creando usuario');
    }
  };

  // Actualizar usuario
  const handleUpdateUser = async (userId: string) => {
    if (!editingUser || editingUser.id !== userId) return;

    try {
      const updatePayload: any = {};
      if (editingUser.role !== undefined) updatePayload.role = editingUser.role;
      if (editingUser.status !== undefined) updatePayload.status = editingUser.status;
      if (editingUser.tier !== undefined) updatePayload.tier = editingUser.tier;

      const response = await apiFetch(`/api/admin/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify(updatePayload)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error ${response.status}`);
      }

      const updatedUser: User = await response.json();
      setUsers(users.map(u => (u.id === userId ? updatedUser : u)));
      setEditingUser(null);
      setMessage('✅ Usuario actualizado correctamente');
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setError(err.message || 'Error actualizando usuario');
    }
  };

  // Eliminar usuario (soft delete)
  const handleDeleteUser = async (userId: string) => {
    if (userId === currentUser) {
      setError('No puedes eliminar tu propia cuenta');
      return;
    }

    if (!window.confirm('¿Estás seguro de que deseas eliminar este usuario? (No se puede revertir)')) {
      return;
    }

    try {
      const response = await apiFetch(`/api/admin/users/${userId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error ${response.status}`);
      }

      setUsers(users.filter(u => u.id !== userId));
      setMessage('✅ Usuario eliminado correctamente');
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setError(err.message || 'Error eliminando usuario');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('es-ES', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric'
    });
  };

  const getRoleColor = (role: string) => {
    return role === 'admin' ? 'text-yellow-400' : 'text-blue-400';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'suspended':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      default:
        return 'bg-red-500/20 text-red-400 border-red-500/30';
    }
  };

  const getTierColor = (tier: string) => {
    switch (tier) {
      case 'PREMIUM':
        return 'text-purple-400';
      case 'INSTITUTIONAL':
        return 'text-orange-400';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-outfit font-bold text-white/90">Gestión de Usuarios</h3>
          <p className="text-xs text-white/40 font-mono">SSOT: global/aethelgard.db | Soft Delete Policy</p>
        </div>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-aethelgard-green/20 hover:bg-aethelgard-green/30 text-aethelgard-green border border-aethelgard-green/30 transition-all"
        >
          <Plus size={18} />
          Crear Usuario
        </button>
      </div>

      {/* Error/Message */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex gap-3 items-start"
          >
            <AlertTriangle size={18} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </motion.div>
        )}
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-4 rounded-lg bg-aethelgard-green/10 border border-aethelgard-green/20 text-aethelgard-green text-sm"
          >
            {message}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create Form */}
      <AnimatePresence>
        {showCreateForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <GlassPanel className="p-6 space-y-4">
              <h4 className="text-lg font-bold text-white/90">Crear Nuevo Usuario</h4>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-white/50 font-mono uppercase mb-2 block">Email</label>
                  <input
                    type="email"
                    value={createForm.email}
                    onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm focus:border-aethelgard-green/50 focus:outline-none"
                    placeholder="usuario@example.com"
                  />
                </div>

                <div>
                  <label className="text-xs text-white/50 font-mono uppercase mb-2 block">Contraseña</label>
                  <input
                    type="password"
                    value={createForm.password}
                    onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-white/20 text-sm focus:border-aethelgard-green/50 focus:outline-none"
                    placeholder="••••••••"
                  />
                </div>

                <div>
                  <label className="text-xs text-white/50 font-mono uppercase mb-2 block">Rol</label>
                  <select
                    value={createForm.role}
                    onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as 'admin' | 'trader' })}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:border-aethelgard-green/50 focus:outline-none"
                  >
                    <option value="trader">Trader</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs text-white/50 font-mono uppercase mb-2 block">Plan</label>
                  <select
                    value={createForm.tier}
                    onChange={(e) => setCreateForm({ ...createForm, tier: e.target.value as 'BASIC' | 'PREMIUM' | 'INSTITUTIONAL' })}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:border-aethelgard-green/50 focus:outline-none"
                  >
                    <option value="BASIC">BASIC</option>
                    <option value="PREMIUM">PREMIUM</option>
                    <option value="INSTITUTIONAL">INSTITUTIONAL</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setShowCreateForm(false)}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10 transition-all text-sm"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleCreateUser}
                  className="px-4 py-2 rounded-lg bg-aethelgard-green/20 hover:bg-aethelgard-green/30 text-aethelgard-green border border-aethelgard-green/30 transition-all text-sm font-bold flex items-center gap-2"
                >
                  <Check size={16} />
                  Crear
                </button>
              </div>
            </GlassPanel>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Users Table */}
      {loading ? (
        <div className="flex items-center justify-center h-64 text-white/20">
          <div className="animate-spin">⏳ Cargando usuarios...</div>
        </div>
      ) : users.length === 0 ? (
        <GlassPanel className="p-8 text-center text-white/40">
          <Shield size={32} className="mx-auto mb-2 opacity-50" />
          <p className="text-sm">No hay usuarios registrados</p>
        </GlassPanel>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-3 px-4 text-white/50 font-mono font-bold">Email</th>
                <th className="text-left py-3 px-4 text-white/50 font-mono font-bold">Rol</th>
                <th className="text-left py-3 px-4 text-white/50 font-mono font-bold">Plan</th>
                <th className="text-left py-3 px-4 text-white/50 font-mono font-bold">Estado</th>
                <th className="text-left py-3 px-4 text-white/50 font-mono font-bold">Creado</th>
                <th className="text-right py-3 px-4 text-white/50 font-mono font-bold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <Mail size={14} className="text-white/30" />
                      <span className="text-white/80">{user.email}</span>
                    </div>
                  </td>

                  <td className="py-3 px-4">
                    {editingUser?.id === user.id ? (
                      <select
                        value={editingUser.role || user.role}
                        onChange={(e) =>
                          setEditingUser({
                            ...editingUser,
                            role: e.target.value as 'admin' | 'trader'
                          })
                        }
                        className="bg-white/5 border border-white/10 rounded text-white text-xs px-2 py-1"
                      >
                        <option value="admin">Admin</option>
                        <option value="trader">Trader</option>
                      </select>
                    ) : (
                      <span className={`${getRoleColor(user.role)} font-bold`}>
                        {user.role.toUpperCase()}
                      </span>
                    )}
                  </td>

                  <td className="py-3 px-4">
                    {editingUser?.id === user.id ? (
                      <select
                        value={editingUser.tier || user.tier}
                        onChange={(e) =>
                          setEditingUser({
                            ...editingUser,
                            tier: e.target.value as 'BASIC' | 'PREMIUM' | 'INSTITUTIONAL'
                          })
                        }
                        className="bg-white/5 border border-white/10 rounded text-white text-xs px-2 py-1"
                      >
                        <option value="BASIC">BASIC</option>
                        <option value="PREMIUM">PREMIUM</option>
                        <option value="INSTITUTIONAL">INSTITUTIONAL</option>
                      </select>
                    ) : (
                      <span className={getTierColor(user.tier)}>{user.tier}</span>
                    )}
                  </td>

                  <td className="py-3 px-4">
                    {editingUser?.id === user.id ? (
                      <select
                        value={editingUser.status || user.status}
                        onChange={(e) =>
                          setEditingUser({
                            ...editingUser,
                            status: e.target.value as 'active' | 'suspended'
                          })
                        }
                        className="bg-white/5 border border-white/10 rounded text-white text-xs px-2 py-1"
                      >
                        <option value="active">Active</option>
                        <option value="suspended">Suspended</option>
                      </select>
                    ) : (
                      <span className={`px-2 py-1 rounded text-xs border ${getStatusColor(user.status)}`}>
                        {user.status}
                      </span>
                    )}
                  </td>

                  <td className="py-3 px-4 text-white/50">{formatDate(user.created_at)}</td>

                  <td className="py-3 px-4">
                    <div className="flex gap-2 justify-end">
                      {editingUser?.id === user.id ? (
                        <>
                          <button
                            onClick={() => handleUpdateUser(user.id)}
                            className="p-1 rounded bg-aethelgard-green/20 hover:bg-aethelgard-green/30 text-aethelgard-green transition-all"
                            title="Guardar cambios"
                          >
                            <Check size={14} />
                          </button>
                          <button
                            onClick={() => setEditingUser(null)}
                            className="p-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 transition-all"
                            title="Cancelar edición"
                          >
                            <X size={14} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => setEditingUser({ id: user.id })}
                            disabled={user.id === currentUser}
                            className="p-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            title={user.id === currentUser ? 'No puedes editar tu propia cuenta' : 'Editar'}
                          >
                            <Edit size={14} />
                          </button>
                          <button
                            onClick={() => handleDeleteUser(user.id)}
                            disabled={user.id === currentUser}
                            className="p-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            title={user.id === currentUser ? 'No puedes eliminar tu propia cuenta' : 'Eliminar'}
                          >
                            <Trash2 size={14} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer Info */}
      <div className="text-xs text-white/30 font-mono space-y-1">
        <p>📊 Total: {users.length} usuarios activos</p>
        <p>🔐 Soft Delete Policy: Usuarios nunca se eliminan (compliance/audit)</p>
        <p>📝 Todos los cambios se registran en sys_audit_logs</p>
      </div>
    </div>
  );
}
