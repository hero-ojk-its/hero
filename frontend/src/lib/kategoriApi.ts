/**
 * Client API Kelola Kategori Knowledge Base (Langkah 28).
 *
 * Endpoint (izin baca KB_BACA, ubah KB_KELOLA):
 *   GET    /api/v1/categories/tree
 *   POST   /api/v1/categories/              201, bentuk respons tidak terdokumentasi (objek ORM)
 *   PATCH  /api/v1/categories/{id}          200 {kategori, dokumen_dipindah, dokumen_gagal}
 *   DELETE /api/v1/categories/{id}          204, atau 409 {detail: {subkategori, dokumen, message}}
 *
 * Tipe mengikuti kode backend (routers/categories.py, services/category_service.py), bukan
 * step28-report.md, yang berbeda di beberapa hal: classification_rule berupa STRING teks JSON objek,
 * dokumen_gagal[] berisi {document_id, alasan}, dan konflik hapus bersarang di dalam `detail`.
 * Setelah setiap mutasi, pohon dimuat ulang; respons POST tidak dipakai.
 */

import { apiFetch, apiJson, ApiError } from './api';

/** PATCH nama/induk memindahkan berkas fisik seluruh subpohon secara sinkron */
export const KATEGORI_TIMEOUT_MS = 120000;
export const MAKS_NAMA_KATEGORI = 100;
export const MAKS_ATURAN_KLASIFIKASI = 4000;

// ============================================================================
// Tipe
// ============================================================================

export interface CategoryTreeNode {
  id: number;
  name: string;
  parent_id: number | null;
  auto_created: boolean;
  /** Dokumen aktif langsung di kategori ini (= document_count) */
  jumlah_dokumen: number;
  /** Dokumen aktif termasuk seluruh subkategori */
  total_document_count: number;
  classification_rule: string | null;
  children: CategoryTreeNode[];
}

export interface CategoryDetail {
  id: number;
  name: string;
  parent_id: number | null;
  auto_created: boolean;
  path: string[];
  jumlah_dokumen: number;
  classification_rule: string | null;
}

export interface DokumenGagalPenempatan {
  document_id: number;
  /** "metadata_belum_cukup" | "gagal: ..." | teks exception */
  alasan: string;
}

export interface CategoryUpdateResult {
  kategori: CategoryDetail | null;
  dokumen_dipindah: number;
  dokumen_gagal: DokumenGagalPenempatan[];
}

export interface KonflikHapus {
  subkategori: number;
  /** Termasuk dokumen nonaktif (backend tidak menyaring is_active) */
  dokumen: number;
}

/** Body PATCH: hanya field yang berubah. `parent_id: null` = pindah ke akar, beda dengan tidak dikirim. */
export interface UbahKategoriBody {
  name?: string;
  parent_id?: number | null;
  classification_rule?: string | null;
}

export interface BuatKategoriBody {
  name: string;
  parent_id: number | null;
  classification_rule: string | null;
}

// ============================================================================
// Normalisasi (field hilang tidak membuat UI crash)
// ============================================================================

type Objek = Record<string, unknown>;
const objek = (v: unknown): Objek => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Objek) : {});
const angka = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const idAtauNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const teksAtauNull = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function normalisasiNode(v: unknown): CategoryTreeNode | null {
  const o = objek(v);
  if (typeof o.id !== 'number') return null;
  const langsung = typeof o.jumlah_dokumen === 'number' ? o.jumlah_dokumen : o.document_count;
  const anak = Array.isArray(o.children) ? o.children.map(normalisasiNode).filter((n): n is CategoryTreeNode => n !== null) : [];
  return {
    id: o.id,
    name: typeof o.name === 'string' && o.name.trim() !== '' ? o.name : `Kategori #${o.id}`,
    parent_id: idAtauNull(o.parent_id),
    auto_created: o.auto_created === true,
    jumlah_dokumen: angka(langsung),
    total_document_count: typeof o.total_document_count === 'number' ? o.total_document_count : angka(langsung),
    classification_rule: teksAtauNull(o.classification_rule),
    children: anak,
  };
}

export function normalisasiPohon(raw: unknown): CategoryTreeNode[] {
  return Array.isArray(raw) ? raw.map(normalisasiNode).filter((n): n is CategoryTreeNode => n !== null) : [];
}

function normalisasiHasilUbah(raw: unknown): CategoryUpdateResult {
  const o = objek(raw);
  const k = objek(o.kategori);
  const gagal = Array.isArray(o.dokumen_gagal) ? o.dokumen_gagal : [];
  return {
    kategori: typeof k.id === 'number'
      ? {
          id: k.id,
          name: typeof k.name === 'string' ? k.name : '',
          parent_id: idAtauNull(k.parent_id),
          auto_created: k.auto_created === true,
          path: Array.isArray(k.path) ? k.path.filter((s): s is string => typeof s === 'string') : [],
          jumlah_dokumen: angka(typeof k.jumlah_dokumen === 'number' ? k.jumlah_dokumen : k.document_count),
          classification_rule: teksAtauNull(k.classification_rule),
        }
      : null,
    dokumen_dipindah: angka(o.dokumen_dipindah),
    dokumen_gagal: gagal
      .map((g) => objek(g))
      .filter((g) => typeof g.document_id === 'number')
      .map((g) => ({ document_id: g.document_id as number, alasan: typeof g.alasan === 'string' ? g.alasan : String(g.error ?? '') })),
  };
}

// ============================================================================
// Pemanggilan API
// ============================================================================

export async function getPohonKategori({ signal }: { signal?: AbortSignal } = {}): Promise<CategoryTreeNode[]> {
  // no-store: pohon harus segar setelah mutasi
  const raw = await apiFetch<unknown>('/api/v1/categories/tree', { signal, cache: 'no-store' });
  return normalisasiPohon(raw);
}

export async function buatKategori(body: BuatKategoriBody, { signal }: { signal?: AbortSignal } = {}): Promise<void> {
  await apiJson<unknown>('POST', '/api/v1/categories/', body, { signal });
}

export async function ubahKategori(
  id: number,
  body: UbahKategoriBody,
  { signal }: { signal?: AbortSignal } = {}
): Promise<CategoryUpdateResult> {
  const raw = await apiJson<unknown>('PATCH', `/api/v1/categories/${id}`, body, { signal, timeout: KATEGORI_TIMEOUT_MS });
  return normalisasiHasilUbah(raw);
}

export async function hapusKategori(id: number, { signal }: { signal?: AbortSignal } = {}): Promise<void> {
  await apiJson<unknown>('DELETE', `/api/v1/categories/${id}`, undefined, { signal });
}

// ============================================================================
// Pesan galat ramah
// ============================================================================

export type AksiKategori = 'muat' | 'buat' | 'ubah' | 'hapus';

export interface PesanGalatKategori {
  judul: string;
  pesan: string;
  /** "Coba lagi" hanya untuk galat jaringan, timeout, dan 5xx */
  bisaCobaLagi: boolean;
  /** Terisi bila DELETE ditolak 409 karena kategori masih berisi */
  konflikHapus?: KonflikHapus;
}

const IZIN_DITOLAK: Record<AksiKategori, string> = {
  muat: 'Peran Anda tidak memiliki izin melihat kategori Knowledge Base.',
  buat: 'Peran Anda tidak memiliki izin membuat kategori.',
  ubah: 'Peran Anda tidak memiliki izin mengubah kategori.',
  hapus: 'Peran Anda tidak memiliki izin menghapus kategori.',
};

function teksDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  const o = objek(detail);
  return typeof o.message === 'string' ? o.message : typeof o.detail === 'string' ? o.detail : '';
}

function pesan422(detail: unknown): string {
  const t = teksDetail(detail).toLowerCase();
  if (/dirinya sendiri|turunan/.test(t)) return 'Kategori tidak bisa dipindah ke dalam dirinya sendiri atau subkategorinya.';
  if (t.includes('classification_rule') || t.includes('aturan')) {
    if (t.includes('4.000') || t.includes('4000') || t.includes('melebihi')) return 'Aturan klasifikasi melebihi 4.000 karakter.';
    if (t.includes('objek') || t.includes('dict')) return 'Aturan klasifikasi harus berupa objek JSON, misalnya {"kata_kunci": ["..."]}, bukan array atau nilai tunggal.';
    return 'Aturan klasifikasi harus berupa JSON yang valid.';
  }
  if (t.includes('nama') && t.includes('kosong')) return 'Nama kategori tidak boleh kosong.';
  if (t.includes('nama')) return 'Nama kategori tidak valid.';
  return 'Data yang dikirim tidak valid. Periksa kembali isian form.';
}

export function pesanGalatKategori(err: unknown, aksi: AksiKategori): PesanGalatKategori {
  if (!(err instanceof ApiError)) {
    return { judul: 'Terjadi kesalahan', pesan: 'Terjadi kesalahan tak terduga.', bisaCobaLagi: false };
  }
  const { status, detail } = err;
  if (status === 401) return { judul: 'Sesi berakhir', pesan: 'Sesi berakhir, silakan masuk lagi.', bisaCobaLagi: false };
  if (status === 403) return { judul: 'Akses ditolak', pesan: IZIN_DITOLAK[aksi], bisaCobaLagi: false };
  if (status === 404) {
    const induk = teksDetail(detail).toLowerCase().includes('induk');
    return {
      judul: 'Tidak ditemukan',
      pesan: induk
        ? 'Kategori induk yang dipilih tidak ditemukan; mungkin sudah dihapus. Muat ulang pohon lalu pilih induk lain.'
        : 'Kategori ini tidak ditemukan; mungkin sudah dihapus. Muat ulang pohon kategori.',
      bisaCobaLagi: false,
    };
  }
  if (status === 409) {
    const o = objek(detail);
    if (aksi === 'hapus' && (typeof o.subkategori === 'number' || typeof o.dokumen === 'number')) {
      const konflik = { subkategori: angka(o.subkategori), dokumen: angka(o.dokumen) };
      return {
        judul: 'Kategori tidak bisa dihapus',
        pesan: `Masih ada ${konflik.subkategori} subkategori dan ${konflik.dokumen} dokumen (termasuk dokumen nonaktif). Pindahkan atau kosongkan isinya dulu.`,
        bisaCobaLagi: false,
        konflikHapus: konflik,
      };
    }
    return { judul: 'Nama sudah dipakai', pesan: 'Sudah ada kategori dengan nama ini di bawah induk yang sama. Gunakan nama lain.', bisaCobaLagi: false };
  }
  if (status === 422) return { judul: 'Isian tidak valid', pesan: pesan422(detail), bisaCobaLagi: false };
  if (status === 0) {
    return /batas waktu/i.test(err.message)
      ? {
          judul: 'Waktu habis',
          pesan: aksi === 'ubah'
            ? 'Proses memakan waktu lebih dari 120 detik. Perubahan mungkin tetap diselesaikan server; muat ulang pohon untuk memeriksanya.'
            : 'Server terlalu lama merespons.',
          bisaCobaLagi: true,
        }
      : { judul: 'Tidak dapat terhubung', pesan: 'Tidak dapat terhubung ke peladen.', bisaCobaLagi: true };
  }
  if (status >= 500) return { judul: 'Gangguan peladen', pesan: `Terjadi gangguan di peladen (HTTP ${status}).`, bisaCobaLagi: true };
  return { judul: 'Permintaan gagal', pesan: `Permintaan tidak dapat diproses (HTTP ${status}).`, bisaCobaLagi: false };
}

// ============================================================================
// Validasi isian (cermin backend)
// ============================================================================

const KARAKTER_TERLARANG = /[/\\:*?"<>|]/g;

/** Cermin sanitize_segment_name: buang / \ : * ? " < > |, rapikan spasi, potong 100 karakter */
export function sanitasiNamaKategori(nama: string): string {
  return nama.replace(KARAKTER_TERLARANG, '').replace(/\s+/g, ' ').trim().slice(0, MAKS_NAMA_KATEGORI);
}

export type HasilValidasiNama = { ok: true; nama: string; disanitasi: boolean } | { ok: false; pesan: string };

export function validasiNamaKategori(nama: string): HasilValidasiNama {
  if (nama.trim() === '') return { ok: false, pesan: 'Nama kategori wajib diisi.' };
  const bersih = sanitasiNamaKategori(nama);
  // Backend mengganti nama yang kosong setelah disanitasi dengan "Lainnya"; dicegah di sini
  if (bersih === '') return { ok: false, pesan: 'Nama hanya berisi karakter yang tidak diizinkan (/ \\ : * ? " < > |).' };
  return { ok: true, nama: bersih, disanitasi: bersih !== nama.trim() };
}

export type HasilValidasiAturan = { ok: true; nilai: string | null } | { ok: false; pesan: string };

/** Kosong -> null (hapus aturan). Selain itu harus teks JSON objek, maks 4.000 karakter. */
export function validasiAturanKlasifikasi(teks: string): HasilValidasiAturan {
  const t = teks.trim();
  if (t === '') return { ok: true, nilai: null };
  if (t.length > MAKS_ATURAN_KLASIFIKASI) return { ok: false, pesan: `Aturan klasifikasi melebihi ${MAKS_ATURAN_KLASIFIKASI.toLocaleString('id-ID')} karakter.` };
  let hasil: unknown;
  try {
    hasil = JSON.parse(t);
  } catch {
    return { ok: false, pesan: 'Aturan klasifikasi bukan JSON yang valid.' };
  }
  if (!hasil || typeof hasil !== 'object' || Array.isArray(hasil)) {
    return { ok: false, pesan: 'Aturan klasifikasi harus berupa objek JSON ({ ... }), bukan array atau nilai tunggal.' };
  }
  return { ok: true, nilai: t };
}

// ============================================================================
// Utilitas jalur
// ============================================================================

export interface KategoriTerindeks {
  node: CategoryTreeNode;
  /** Nama dari akar sampai node ini */
  path: string[];
  depth: number;
}

/** Daftar datar urut pohon (pre-order) dengan jalur penuh */
export function ratakanPohon(nodes: CategoryTreeNode[], path: string[] = [], depth = 0): KategoriTerindeks[] {
  const hasil: KategoriTerindeks[] = [];
  for (const node of nodes) {
    const p = [...path, node.name];
    hasil.push({ node, path: p, depth });
    hasil.push(...ratakanPohon(node.children, p, depth + 1));
  }
  return hasil;
}

export const jalurTeks = (path: string[]): string => path.join(' / ');

/** ID node beserta seluruh turunannya (tidak boleh menjadi induk baru node itu) */
export function idDanTurunan(node: CategoryTreeNode): Set<number> {
  const ids = new Set<number>();
  const jalan = (n: CategoryTreeNode) => {
    ids.add(n.id);
    n.children.forEach(jalan);
  };
  jalan(node);
  return ids;
}
