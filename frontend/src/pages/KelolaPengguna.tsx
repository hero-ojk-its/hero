import { useState, useEffect, useCallback } from 'react';
import { 
  Users, 
  RefreshCw, 
  Filter, 
  Lock, 
  UserCheck, 
  UserX, 
  Shield, 
  Briefcase, 
  Calendar
} from 'lucide-react';
import { getUsers, extractSafeErrorMessage, type UserResponse } from '../lib/adminApi';
import type { components } from '../lib/openapi';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import AppBreadcrumb from '../components/common/AppBreadcrumb';

type PeranOption = components['schemas']['PeranPengguna'] | '';

const ROLE_LABELS: Record<string, { label: string; badgeClass: string }> = {
  analis: { label: 'Analis Regulasi', badgeClass: 'bg-blue-50 text-blue-700 border-blue-200' },
  admin_kb: { label: 'Admin Knowledge Base', badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  admin_sistem: { label: 'Admin Sistem', badgeClass: 'bg-purple-50 text-purple-700 border-purple-200' },
  pilot_user: { label: 'Pilot User', badgeClass: 'bg-amber-50 text-amber-700 border-amber-200' },
};

export default function KelolaPengguna() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown | null>(null);
  const [roleFilter, setRoleFilter] = useState<PeranOption>('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const fetchUsers = useCallback(async (signal?: AbortSignal) => {
    queueMicrotask(() => {
      if (!signal?.aborted) {
        setLoading(true);
        setError(null);
      }
    });
    try {
      const data = await getUsers(
        {
          role: roleFilter ? roleFilter : null,
          is_active: statusFilter === 'active' ? true : statusFilter === 'inactive' ? false : null,
        },
        signal
      );
      setUsers(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [roleFilter, statusFilter]);

  useEffect(() => {
    const controller = new AbortController();
    fetchUsers(controller.signal);
    return () => controller.abort();
  }, [fetchUsers]);

  const safeError = error ? extractSafeErrorMessage(error) : null;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <AppBreadcrumb items={[{ label: 'Kelola Pengguna', isCurrent: true }]} />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-gray-200">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-red-100 text-red-700 rounded-lg">
              <Users size={20} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Kelola Pengguna</h1>
              <p className="text-sm text-gray-500 mt-1">
                Daftar akun, peran otorisasi, dan status aktif pengguna sistem HERO.
              </p>
            </div>
          </div>
        </div>

        {/* Action button */}
        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => fetchUsers()}
            disabled={loading}
            className="inline-flex items-center px-3.5 py-2 text-xs font-semibold rounded-lg bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw size={14} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Segarkan
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-wrap items-center gap-4">
        <div className="flex items-center space-x-2 text-xs font-semibold text-gray-700">
          <Filter size={15} className="text-gray-400" />
          <span>Filter:</span>
        </div>

        <div className="flex items-center space-x-2">
          <label htmlFor="role-filter" className="text-xs text-gray-500">
            Peran:
          </label>
          <select
            id="role-filter"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value as PeranOption)}
            className="py-1.5 px-2.5 border border-gray-300 rounded-lg text-xs text-gray-800 bg-white focus:ring-red-600 focus:border-red-600"
          >
            <option value="">Semua Peran</option>
            <option value="analis">Analis Regulasi</option>
            <option value="admin_kb">Admin Knowledge Base</option>
            <option value="admin_sistem">Admin Sistem</option>
            <option value="pilot_user">Pilot User</option>
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <label htmlFor="status-filter" className="text-xs text-gray-500">
            Status:
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'inactive')}
            className="py-1.5 px-2.5 border border-gray-300 rounded-lg text-xs text-gray-800 bg-white focus:ring-red-600 focus:border-red-600"
          >
            <option value="all">Semua Status</option>
            <option value="active">Hanya Aktif</option>
            <option value="inactive">Nonaktif</option>
          </select>
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <LoadingState message="Memuat daftar pengguna dari peladen backend..." />
      ) : safeError ? (
        <div className="space-y-4">
          {safeError.is403 && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start space-x-3 text-amber-900">
              <Lock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs space-y-1">
                <p className="font-semibold">{safeError.title}</p>
                <p className="text-amber-800">{safeError.message}</p>
              </div>
            </div>
          )}
          <ErrorState
            title={safeError.title}
            message={safeError.message}
            onRetry={() => fetchUsers()}
            retryText="Coba Ambil Ulang"
          />
        </div>
      ) : users.length === 0 ? (
        <EmptyState
          title="Tidak ada akun pengguna"
          message="Belum ada pengguna yang sesuai dengan filter yang dipilih."
          onAction={() => {
            setRoleFilter('');
            setStatusFilter('all');
          }}
          actionLabel="Hapus Filter"
        />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-gray-700 divide-y divide-gray-200">
              <thead className="bg-gray-50 text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                <tr>
                  <th scope="col" className="px-4 py-3">Nama Lengkap & Username</th>
                  <th scope="col" className="px-4 py-3">Unit Kerja</th>
                  <th scope="col" className="px-4 py-3">Peran Akses</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3">Terdaftar Pada</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {users.map((user) => {
                  const roleConfig = ROLE_LABELS[user.role] || {
                    label: user.role,
                    badgeClass: 'bg-gray-100 text-gray-800 border-gray-200',
                  };

                  const createdStr = user.created_at
                    ? new Date(user.created_at).toLocaleDateString('id-ID', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })
                    : '-';

                  return (
                    <tr key={user.id} className="hover:bg-gray-50/80 transition-colors">
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="font-semibold text-gray-900">
                          {user.nama_lengkap || user.username}
                        </div>
                        <div className="text-[11px] text-gray-500 font-mono">@{user.username}</div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-600 flex items-center gap-1.5">
                        <Briefcase size={13} className="text-gray-400 shrink-0" />
                        <span>{user.unit_kerja || '-'}</span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold border ${roleConfig.badgeClass}`}
                        >
                          <Shield size={10} className="mr-1" />
                          {roleConfig.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {user.is_active ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <UserCheck size={11} className="mr-1" />
                            Aktif
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-50 text-red-700 border border-red-200">
                            <UserX size={11} className="mr-1" />
                            Nonaktif
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-500 flex items-center gap-1.5">
                        <Calendar size={13} className="text-gray-400 shrink-0" />
                        <span>{createdStr}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
