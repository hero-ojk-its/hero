import AppBreadcrumb from '../common/AppBreadcrumb';
import type { BreadcrumbItem } from '../common/AppBreadcrumb';

export interface AnalisaBreadcrumbProps {
  /**
   * Tahap atau konteks halaman saat ini:
   * - 'initial': Halaman awal Analisa Regulasi (Upload / Pilih Draft)
   * - 'summary': Ringkasan Eksekutif & Key Takeaways (Summary View)
   * - 'analisa': Workspace Analisa Regulasi 2-Panel
   */
  stage: 'initial' | 'summary' | 'analisa';

  /**
   * Callback untuk mereset sesi aktif dan kembali ke formulir upload / riwayat draft
   */
  onBackToState1?: () => void;

  /**
   * Callback untuk kembali ke Summary View dari Workspace Analisa (jika tersedia)
   */
  onBackToSummary?: () => void;

  /**
   * ClassName opsional untuk penyesuaian margin/padding jika dibutuhkan
   */
  className?: string;
}

/**
 * Komponen Breadcrumb Terstandarisasi untuk Seluruh Halaman Fitur Analisa Regulasi HERO
 * Menggunakan AppBreadcrumb sebagai basis styling dan arsitektur komponen global.
 */
export default function AnalisaBreadcrumb({
  stage,
  onBackToState1,
  onBackToSummary,
  className = '',
}: AnalisaBreadcrumbProps) {
  const items: BreadcrumbItem[] = [
    { label: 'Dashboard', to: '/' },
  ];

  if (stage === 'initial') {
    items.push({
      label: 'Analisa Regulasi',
      isCurrent: true,
      variant: 'red',
    });
  } else if (stage === 'summary') {
    items.push({
      label: 'Analisa Regulasi',
      onClick: onBackToState1,
      title: 'Kembali ke formulir upload dan daftar draft regulasi',
    });
    items.push({
      label: 'Summary',
      isCurrent: true,
      variant: 'red',
    });
  } else if (stage === 'analisa') {
    items.push({
      label: 'Analisa Regulasi',
      onClick: onBackToState1,
      title: 'Kembali ke formulir upload dan daftar draft regulasi',
    });
    if (onBackToSummary) {
      items.push({
        label: 'Summary',
        onClick: onBackToSummary,
        title: 'Kembali ke Ringkasan Eksekutif & Key Takeaways',
      });
    }
    items.push({
      label: 'Analisa Regulasi',
      isCurrent: true,
      variant: 'red',
    });
  }

  return (
    <AppBreadcrumb
      items={items}
      includeDashboard={false}
      className={className}
    />
  );
}
