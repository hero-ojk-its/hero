import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Lock,
  User,
  AlertCircle,
  AlertTriangle,
  Loader2,
  ArrowRight,
  Shield,
  Eye,
  EyeOff,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import {
  login,
  getMe,
  extractAuthError,
  type AuthErrorInfo,
} from '../lib/authApi';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<AuthErrorInfo | null>(null);
  const [retryCountdown, setRetryCountdown] = useState<number | null>(null);
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null);

  // Periksa apakah autentikasi diaktifkan di backend
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    getMe(controller.signal)
      .then((profile) => {
        if (isMounted) {
          setAuthEnabled(profile.auth_enabled !== false);
        }
      })
      .catch(() => {
        // Jika endpoint /me mengembalikan error (misal 401 saat auth aktif), auth dianggap aktif
        if (isMounted) {
          setAuthEnabled(true);
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  // Timer countdown untuk Retry-After jika informasi waktu tersedia dari backend
  useEffect(() => {
    if (retryCountdown === null || retryCountdown <= 0) return;

    const interval = setInterval(() => {
      setRetryCountdown((prev) => {
        if (prev === null || prev <= 1) {
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [retryCountdown]);

  const isLockedOut = retryCountdown !== null && retryCountdown > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isLoading || isLockedOut) return;

    if (!username.trim() || !password) {
      setError({
        title: 'Formulir Belum Lengkap',
        message: 'Silakan masukkan username dan kata sandi Anda.',
        status: 400,
        retryAfter: null,
        is429: false,
        is401: false,
        is403: false,
        is5xx: false,
        isNetworkError: false,
      });
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await login({ username, password });

      // Berhasil masuk: arahkan ke halaman tujuan atau dashboard
      const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const authErr = extractAuthError(err);
      setError(authErr);

      // Keamanan: Password dikosongkan setelah login gagal
      setPassword('');

      // Jika response menyediakan Retry-After valid, aktifkan timer tanpa mengarang angka
      if (authErr.is429 && typeof authErr.retryAfter === 'number' && authErr.retryAfter > 0) {
        setRetryCountdown(authErr.retryAfter);
      } else {
        setRetryCountdown(null);
      }
    } finally {
      // Pastikan loading state selalu berhenti setelah request selesai
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-100 to-gray-200 flex flex-col justify-center items-center p-4 sm:p-6 lg:p-8 font-sans">
      <div className="w-full max-w-md">
        {/* Header Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center space-x-2 mb-2">
            <span className="text-3xl font-extrabold text-gray-900 tracking-tight">
              HERO<span className="text-red-700">.</span>
            </span>
            <span className="text-gray-300 font-light text-2xl">|</span>
            <span className="text-xs font-semibold text-gray-600 tracking-wider uppercase text-left leading-tight">
              Regulasi Otomatis<br />Otoritas Jasa Keuangan
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Harmonisasi Elektronik Regulasi Otomatis
          </p>
        </div>

        {/* Notifikasi jika mode AUTH_ENABLED=false */}
        {authEnabled === false && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-sm flex items-start space-x-3 shadow-sm">
            <Shield className="shrink-0 text-amber-600 mt-0.5" size={18} aria-hidden="true" />
            <div className="flex-1">
              <p className="font-semibold text-amber-900">Mode Pengembangan Aktif</p>
              <p className="text-xs text-amber-700 mt-0.5">
                Autentikasi saat ini dinonaktifkan di backend (<code>AUTH_ENABLED=false</code>). Anda dapat langsung menuju dashboard.
              </p>
              <button
                type="button"
                onClick={() => navigate('/')}
                className="mt-2 text-xs font-semibold text-amber-900 underline hover:text-amber-950 flex items-center space-x-1"
              >
                <span>Buka Dashboard Langsung</span>
                <ArrowRight size={12} />
              </button>
            </div>
          </div>
        )}

        {/* Card Formulir Login */}
        <div className="bg-white rounded-2xl shadow-xl border border-gray-200/80 p-6 sm:p-8 backdrop-blur-sm">
          <div className="mb-6">
            <h2 className="text-xl font-bold text-gray-900">Masuk ke Sistem</h2>
            <p className="text-xs text-gray-500 mt-1">
              Gunakan kredensial akun terdaftar Anda untuk melanjutkan ke portal HERO.
            </p>
          </div>

          {/* Kotak Pesan Galat */}
          {error && (
            <div
              role="alert"
              className={`mb-6 p-4 rounded-xl border text-sm flex items-start space-x-3 animate-in fade-in duration-200 ${
                error.is429
                  ? 'bg-red-50 border-red-300 text-red-900'
                  : error.isNetworkError
                  ? 'bg-orange-50 border-orange-200 text-orange-900'
                  : error.is5xx
                  ? 'bg-rose-50 border-rose-200 text-rose-900'
                  : 'bg-red-50 border-red-200 text-red-800'
              }`}
            >
              <div className="shrink-0 mt-0.5">
                {error.is429 ? (
                  <AlertTriangle className="text-red-700" size={20} aria-hidden="true" />
                ) : (
                  <AlertCircle
                    className={error.isNetworkError ? 'text-orange-600' : 'text-red-600'}
                    size={20}
                    aria-hidden="true"
                  />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm leading-tight">{error.title}</p>
                {/* Tampilkan pesan backend tanpa diganti pesan generik */}
                <p className="text-xs mt-1 text-gray-700 whitespace-pre-line leading-relaxed">
                  {error.message}
                </p>

                {/* Indikator waktu tunggu jika Retry-After tersedia */}
                {isLockedOut && (
                  <div className="mt-2.5 pt-2 border-t border-red-200/60 flex items-center space-x-1.5 text-xs font-medium text-red-800">
                    <Clock size={14} className="text-red-700 shrink-0" aria-hidden="true" />
                    <span>
                      Dapat mencoba kembali dalam:{' '}
                      <strong className="font-bold tabular-nums">
                        {retryCountdown >= 60
                          ? `${Math.floor(retryCountdown / 60)}m ${retryCountdown % 60}s`
                          : `${retryCountdown} detik`}
                      </strong>
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Input Username */}
            <div>
              <label htmlFor="username" className="block text-xs font-semibold text-gray-700 mb-1">
                Username / Identitas Pengguna
              </label>
              <div className="relative rounded-lg shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                  <User size={16} aria-hidden="true" />
                </div>
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  disabled={isLoading}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="mis. raditya / analis_ojk"
                  className="block w-full pl-9 pr-3 py-2.5 text-sm rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-red-600 bg-white text-gray-900 disabled:bg-gray-100 disabled:text-gray-500 transition-colors"
                />
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                Username tidak peka huruf besar-kecil.
              </p>
            </div>

            {/* Input Password */}
            <div>
              <label htmlFor="password" className="block text-xs font-semibold text-gray-700 mb-1">
                Kata Sandi
              </label>
              <div className="relative rounded-lg shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                  <Lock size={16} aria-hidden="true" />
                </div>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  disabled={isLoading}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="block w-full pl-9 pr-10 py-2.5 text-sm rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-red-600 bg-white text-gray-900 disabled:bg-gray-100 disabled:text-gray-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Sembunyikan kata sandi' : 'Tampilkan kata sandi'}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                Kata sandi Anda dilindungi enkripsi bcrypt.
              </p>
            </div>

            {/* Tombol Masuk */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading || isLockedOut}
                aria-busy={isLoading}
                className="w-full py-2.5 px-4 rounded-lg bg-red-700 hover:bg-red-800 focus:outline-none focus:ring-2 focus:ring-red-600 focus:ring-offset-2 text-white font-medium text-sm transition-all flex items-center justify-center space-x-2 disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed shadow-sm active:scale-[0.99]"
              >
                {isLoading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                    <span>Memverifikasi...</span>
                  </>
                ) : isLockedOut ? (
                  <>
                    <Clock size={16} aria-hidden="true" />
                    <span>Tunggu ({retryCountdown}s)</span>
                  </>
                ) : (
                  <>
                    <span>Masuk ke HERO</span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Catatan Kebijakan Keamanan */}
          <div className="mt-6 pt-5 border-t border-gray-100">
            <div className="flex items-start space-x-2 text-[11px] text-gray-500">
              <CheckCircle2 size={14} className="text-emerald-600 shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                Sistem menerapkan pembatasan laju percobaan (rate limit) untuk mencegah serangan brute force. Akun akan terkunci sementara jika melebihi batas percobaan.
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-400 mt-6">
          &copy; {new Date().getFullYear()} Otoritas Jasa Keuangan (OJK). Seluruh Hak Cipta Dilindungi.
        </p>
      </div>
    </div>
  );
}

