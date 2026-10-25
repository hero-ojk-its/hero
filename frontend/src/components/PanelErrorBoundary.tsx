import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { ErrorState } from './ErrorState';

export interface PanelErrorBoundaryProps {
  /** Nama panel yang ditampilkan pada pesan galat, mis. "Struktur Dokumen" */
  nama: string;
  /** Kelas wadah fallback, disamakan dengan kelas panel agar tata letak grid tetap utuh */
  className?: string;
  /** Dipanggil saat tombol "Coba Lagi" ditekan, setelah status galat panel direset */
  onCobaLagi?: () => void;
  children: ReactNode;
}

interface PanelErrorBoundaryState {
  hasError: boolean;
}

/**
 * Menangkap galat render di dalam satu panel sehingga panel lain tetap dapat dipakai.
 * Catatan: galat di event handler atau di luar children (mis. perhitungan di komponen induk)
 * tidak tertangkap oleh error boundary.
 */
export class PanelErrorBoundary extends Component<PanelErrorBoundaryProps, PanelErrorBoundaryState> {
  state: PanelErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): PanelErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Panel "${this.props.nama}" gagal ditampilkan:`, error, info.componentStack);
  }

  handleCobaLagi = () => {
    this.setState({ hasError: false });
    this.props.onCobaLagi?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className={this.props.className}>
          <ErrorState
            title={`Panel ${this.props.nama} gagal ditampilkan`}
            message="Terjadi kesalahan saat menampilkan bagian ini. Panel lain tetap dapat digunakan."
            retryText="Coba Lagi"
            onRetry={this.handleCobaLagi}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
