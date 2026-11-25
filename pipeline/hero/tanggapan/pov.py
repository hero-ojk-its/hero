"""Draft Tanggapan berbasis PoV unit fungsi (URD 3.5, FR-POV-01..05).

Tiga pertanyaan, dijawab deterministik dan masing-masing menunjuk teks penyebabnya:

* **Pasal mana yang berdampak pada unit, dan kenapa?** (FR-POV-05, US-55) — kata kunci topik tugas,
  fungsi, dan keilmuan unit dari profil PoV (``config/pov.yaml``), dengan kutipan tempat ditemukan.
* **Pasal mana yang wajib ditanggapi, dan mana yang belum?** (FR-POV-03, US-53) — checklist dari
  profil: relevansi unit, jenis norma (kewajiban/larangan/…), temuan harmonisasi, ketentuan peralihan.
* **Apa draft tanggapannya?** (FR-POV-04, US-54) — narasi bertemplat per pasal dalam susunan catatan
  dinas yang disepakati (Weekly #10: Kepada Kepala Departemen, Dari Analis Eksekutif, Hal "Tanggapan
  atas …", Tanggal diisi manual). Setiap kalimat lahir dari fakta yang dicantumkan di ``dasar``.

Keluaran berstatus Draft: unit tetap menyunting (FR-POV-06) sebelum diekspor (FR-POV-08).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

VERSION = "tanggapan-pov-v0.1"
CATATAN = ("Draft / Rekomendasi — disusun otomatis dari teks draft dan profil PoV. Wajib ditelaah dan "
           "disunting analis sebelum dikirim; keputusan final tetap kewenangan unit.")


# ---------------------------------------------------------------------------
# profil PoV (FR-POV-01, FR-POV-07)
# ---------------------------------------------------------------------------

@dataclass
class Topik:
    id: str
    nama: str
    bobot: int
    kata_kunci: list[str]
    dampak: str
    _rx: re.Pattern | None = field(default=None, repr=False, compare=False)

    def pola(self) -> re.Pattern:
        if self._rx is None:
            # Kata utuh, frasa panjang dulu; "siber" tidak boleh cocok di "subsiberan" dsb.
            kata = sorted({k.lower() for k in self.kata_kunci}, key=len, reverse=True)
            self._rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in kata) + r")\b")
        return self._rx


@dataclass
class Profil:
    id: str
    nama: str
    unit: str = ""
    tugas: str = ""
    fungsi: list[str] = field(default_factory=list)
    keilmuan: str = ""
    topik: list[Topik] = field(default_factory=list)
    wajib_tanggap: dict[str, Any] = field(default_factory=dict)

    def ringkas(self) -> dict[str, Any]:
        return {"id": self.id, "nama": self.nama, "unit": self.unit, "tugas": self.tugas,
                "fungsi": self.fungsi, "topik": [t.nama for t in self.topik]}


def load_profiles(path: str | Path | None = "config/pov.yaml") -> dict[str, Profil]:
    p = Path(path) if path else None
    if p is None or not p.is_file():
        p = Path(__file__).resolve().parents[2] / "config" / "pov.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, Profil] = {}
    for d in raw.get("profil") or []:
        topik = [Topik(t["id"], t["nama"], int(t.get("bobot", 1)), list(t.get("kata_kunci") or []),
                       t.get("dampak", "")) for t in d.get("topik") or []]
        out[d["id"]] = Profil(d["id"], d["nama"], d.get("unit", ""), d.get("tugas", ""),
                              list(d.get("fungsi") or []), d.get("keilmuan", ""), topik,
                              dict(d.get("wajib_tanggap") or {}))
    if not out:
        raise ValueError(f"tidak ada profil PoV di {p}")
    return out


def pilih_profil(profiles: dict[str, Profil], profil_id: str | None = None) -> Profil:
    if profil_id is None:
        return next(iter(profiles.values()))
    if profil_id not in profiles:
        raise KeyError(f"profil PoV '{profil_id}' tidak dikenal (tersedia: {', '.join(profiles)})")
    return profiles[profil_id]


# ---------------------------------------------------------------------------
# dampak per pasal (FR-POV-05)
# ---------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_DEFINISI = re.compile(r"^\s*(?:\(1\)\s*)?Dalam\s+(?:Peraturan|Surat\s+Edaran)\b.{0,90}?yang\s+dimaksud\s+"
                       r"dengan", re.IGNORECASE)
_PERALIHAN = re.compile(r"\b(?:pada saat .{0,40}mulai berlaku|wajib menyesuaikan|paling lama .{0,40}"
                        r"sejak .{0,40}(?:diundangkan|berlaku)|ketentuan peralihan)\b", re.IGNORECASE)
_BATAS_WAKTU = re.compile(r"\b(?:paling (?:lambat|lama)|dalam jangka waktu)\s+(\d+)\s*(?:\([^)]{1,30}\)\s*)?"
                          r"(hari(?: kerja| kalender)?|bulan|tahun)\b", re.IGNORECASE)


def _cuplik(teks: str, mulai: int, akhir: int, lebar: int = 70) -> str:
    a, b = max(0, mulai - lebar), min(len(teks), akhir + lebar)
    return ("…" if a else "") + teks[a:b].strip() + ("…" if b < len(teks) else "")


@dataclass
class TopikKena:
    id: str
    nama: str
    bobot: int
    kata: list[str]
    bukti: str          # kutipan apa adanya di sekitar kata kunci pertama


def nilai_pasal(teks: str, profil: Profil) -> tuple[int, list[TopikKena]]:
    """Skor relevansi = jumlah bobot topik yang tersentuh (bukan jumlah kemunculan: satu pasal yang
    menyebut "sistem elektronik" lima kali tidak lebih relevan dari yang menyebutnya sekali)."""
    low = _WS.sub(" ", teks or "").lower()
    asli = _WS.sub(" ", teks or "")
    kena: list[TopikKena] = []
    for t in profil.topik:
        hits = list(t.pola().finditer(low))
        if not hits:
            continue
        kata = sorted({h.group(1) for h in hits}, key=lambda k: low.find(k))
        kena.append(TopikKena(t.id, t.nama, t.bobot, kata, _cuplik(asli, hits[0].start(), hits[0].end())))
    kena.sort(key=lambda k: (-k.bobot, k.nama))
    return sum(k.bobot for k in kena), kena


def _tingkat(skor: int) -> str:
    return "tinggi" if skor >= 5 else "sedang" if skor >= 3 else "rendah" if skor >= 1 else "tidak"


def _norma(teks: str) -> list[str]:
    from hero.analysis.structured import classify_unit, split_ayat

    out: list[str] = []
    for _, unit in split_ayat(teks) or [(None, teks)]:
        got = classify_unit(unit)
        if got and got[0] not in out:
            out.append(got[0])
    return out


@dataclass
class PasalTanggapan:
    pasal: str
    halaman: int | None
    kutipan: str
    skor: int
    tingkat: str                                    # tinggi | sedang | rendah | tidak
    topik: list[TopikKena]
    alasan: str                                     # kenapa berdampak — untuk analis
    norma: list[str]
    batas_waktu: list[str] = field(default_factory=list)
    peralihan: bool = False
    definisi: bool = False                          # pasal Ketentuan Umum ("yang dimaksud dengan")
    harmonisasi: dict[str, Any] | None = None       # temuan harmonisasi pasal ini (jenis, pembanding…)
    wajib: bool = False
    dasar_wajib: list[str] = field(default_factory=list)
    status: str = "tidak_wajib"                     # sudah | belum | tidak_wajib
    narasi: str = ""
    usulan: str = ""
    dasar: list[str] = field(default_factory=list)  # fakta yang melahirkan narasi


def _alasan(profil: Profil, kena: list[TopikKena]) -> str:
    if not kena:
        return f"tidak menyentuh topik tugas, fungsi, atau keilmuan {profil.nama}"
    dampak = {t.id: t.dampak for t in profil.topik}
    bagian = [f"{dampak.get(k.id) or k.nama} (kata kunci: {', '.join(k.kata[:4])})" for k in kena[:3]]
    return "; ".join(bagian)


# ---------------------------------------------------------------------------
# checklist kelengkapan (FR-POV-03)
# ---------------------------------------------------------------------------

def wajib_ditanggapi(p: PasalTanggapan, profil: Profil) -> tuple[bool, list[str]]:
    aturan = profil.wajib_tanggap or {}
    dasar: list[str] = []
    if p.definisi and not aturan.get("definisi", False):
        return False, []          # definisi: ditandai berdampak (cek konsistensi istilah), bukan wajib
    if p.skor >= int(aturan.get("skor_minimal", 3)):
        dasar.append(f"relevansi {profil.nama} {p.tingkat} (skor {p.skor})")
    norma_wajib = set(aturan.get("norma") or [])
    kena_norma = [n for n in p.norma if n in norma_wajib]
    if kena_norma and p.skor >= int(aturan.get("skor_minimal_norma", 1)):
        dasar.append(f"memuat norma {', '.join(kena_norma).lower()} yang menyentuh topik unit")
    jenis = (p.harmonisasi or {}).get("jenis")
    if jenis in set(aturan.get("temuan") or []) and p.skor >= 1:
        dasar.append(f"temuan harmonisasi: {(p.harmonisasi or {}).get('istilah') or jenis}")
    if aturan.get("peralihan", True) and p.peralihan and p.skor >= 1:
        dasar.append("ketentuan peralihan/mulai berlaku — menyangkut kesiapan implementasi")
    return bool(dasar), dasar


def periksa_kelengkapan(pasal: list[PasalTanggapan], sudah: dict[str, str] | None) -> dict[str, Any]:
    """Tandai pasal wajib yang BELUM ditanggapi (FR-POV-03). ``sudah`` = {"Pasal 5": "teks tanggapan"}
    dari draft yang sudah disunting analis; tanggapan kosong/hanya tanda baca dihitung belum."""
    isi = {_kunci(k): v for k, v in (sudah or {}).items() if v and re.search(r"\w{3,}", v)}
    for p in pasal:
        p.status = ("sudah" if _kunci(p.pasal) in isi else "belum") if p.wajib else "tidak_wajib"
    wajib = [p for p in pasal if p.wajib]
    belum = [p.pasal for p in wajib if p.status == "belum"]
    return {"wajib": len(wajib), "sudah": len(wajib) - len(belum), "belum": len(belum),
            "lengkap": not belum, "pasal_belum": belum,
            "keterangan": ("semua pasal wajib sudah ditanggapi" if not belum else
                           f"{len(belum)} dari {len(wajib)} pasal wajib belum ditanggapi: "
                           + ", ".join(belum[:15]) + (" …" if len(belum) > 15 else ""))}


def _kunci(pasal: str) -> str:
    return re.sub(r"^pasal\s+", "", _WS.sub(" ", str(pasal)).strip(), flags=re.IGNORECASE).upper()


# ---------------------------------------------------------------------------
# narasi (FR-POV-04)
# ---------------------------------------------------------------------------

def _ringkas_kutipan(teks: str, n: int = 260) -> str:
    t = _WS.sub(" ", teks).strip()
    t = re.sub(r"^\(\d+\)\s*", "", t)
    if len(t) <= n:
        return t.rstrip(" .;:")
    return t[:n].rsplit(" ", 1)[0].rstrip(" ,;:") + " …"


_KATA_FUNGSI = {"Dalam", "Setiap", "Apabila", "Jika", "Selain", "Untuk", "Pada", "Ketentuan", "Dengan",
                "Sebelum", "Setelah", "Terhadap", "Sebagaimana", "Hal", "Bagi", "Atas", "Dalam hal"}


def _awal_kecil(s: str) -> str:
    """"Dalam hal …" → "dalam hal …" di tengah kalimat; istilah terdefinisi ("Bank") tetap kapital."""
    kata = s.split(" ", 1)[0] if s else ""
    return s[:1].lower() + s[1:] if kata in _KATA_FUNGSI else s


def _nama_pembanding(h: dict[str, Any]) -> str:
    pb = h.get("pembanding") or {}
    judul = (pb.get("judul") or "").strip()
    nomor = pb.get("key", "") or ""
    nama = nomor.replace("|", " Nomor ", 1).replace("|", " Tahun ") if nomor else ""
    pasal = f"Pasal {pb.get('pasal')}" if pb.get("pasal") else "ketentuan"
    return f"{pasal} {nama}".strip() + (f" tentang {_judul_rapi(judul)}" if judul and nama else "")


def susun_narasi(p: PasalTanggapan, profil: Profil) -> None:
    """Narasi bertemplat; setiap kalimat bersumber dari fakta yang dicatat di ``p.dasar``."""
    # Ayat yang disebut temuan harmonisasi ("ayat (2) ↔ ayat (1) — …") lebih dulu: narasi mengutip
    # tempat perbedaannya; tanpa itu, ayat yang paling menyentuh topik unit.
    disebut = [int(m.group(1)) for d in (p.harmonisasi or {}).get("perbedaan") or []
               for m in [re.match(r"ayat \((\d+)\) ↔", d)] if m]
    if p.definisi:
        istilah = ", ".join(dict.fromkeys(k for t in p.topik for k in t.kata)) or "-"
        p.narasi = (f"{p.pasal} memuat definisi istilah yang bersinggungan dengan lingkup {profil.nama}, "
                    f"antara lain terkait {istilah}.")
        p.usulan = ("Kami mengusulkan agar definisi istilah tersebut diselaraskan dengan istilah yang sama "
                    "dalam peraturan lain yang berlaku di bidang teknologi informasi.")
        p.dasar.append("topik PoV: " + "; ".join(f"{t.nama} ← \"{t.bukti}\"" for t in p.topik[:3]))
        return
    ayat, teks_ayat = _ayat_terkait(p.kutipan, profil, utamakan=disebut[0] if disebut else None)
    sebut = f"{p.pasal} ayat ({ayat})" if ayat else p.pasal
    kal: list[str] = [f"{sebut} mengatur bahwa {_awal_kecil(_ringkas_kutipan(teks_ayat))}."]
    p.dasar.append(f"kutipan {sebut} (hal. {p.halaman or '-'})")
    if p.topik:
        istilah = ", ".join(dict.fromkeys(k for t in p.topik for k in t.kata))
        kal.append(f"Dari sudut pandang {profil.nama}, ketentuan ini {_dampak(profil, p)}, antara lain "
                   f"terkait {istilah}.")
        p.dasar.append("topik PoV: " + "; ".join(f"{t.nama} ← \"{t.bukti}\"" for t in p.topik[:3]))
    h = p.harmonisasi or {}
    jenis = h.get("jenis")
    beda = "; ".join(h.get("perbedaan") or [])
    if jenis == "konflik":
        kal.append(f"Ketentuan tersebut berbeda dengan {_nama_pembanding(h)} yang masih berlaku"
                   + (f" ({beda})" if beda else "") + ".")
        p.usulan = (f"Kami mengusulkan agar ketentuan ini diselaraskan dengan {_nama_pembanding(h)}, "
                    "atau hubungan keduanya dinyatakan secara tegas (mengubah atau mencabut) agar tidak "
                    "terdapat dua ketentuan berbeda yang berlaku bersamaan.")
    elif jenis == "duplikasi":
        kal.append(f"Substansinya hampir sama dengan {_nama_pembanding(h)}.")
        p.usulan = (f"Kami mengusulkan agar ketentuan ini cukup merujuk {_nama_pembanding(h)} untuk "
                    "menghindari pengaturan ganda.")
    elif jenis == "menggantikan":
        kal.append(f"Ketentuan ini menggantikan {_nama_pembanding(h)}" + (f" ({beda})" if beda else "") + ".")
        if beda:   # tanpa perbedaan konkret, usulan peralihan hanya akan berulang di setiap pasal
            p.usulan = (f"Mengingat terdapat perubahan ketentuan ({beda}), kami mengusulkan agar tersedia "
                        "ketentuan peralihan yang memadai bagi sistem dan layanan yang telah berjalan "
                        "berdasarkan ketentuan sebelumnya.")
    elif jenis == "memperjelas":
        kal.append(f"Ketentuan ini selaras dengan dan melengkapi {_nama_pembanding(h)}.")
    elif jenis == "pasal_baru":
        kal.append("Ketentuan ini merupakan pengaturan baru yang belum diatur dalam peraturan di "
                   "Knowledge Base.")
    if jenis:
        p.dasar.append(f"harmonisasi: {h.get('istilah') or jenis} — {h.get('alasan', '')[:160]}")
    if not p.usulan:
        if p.batas_waktu and ("Kewajiban" in p.norma or "Pelaporan" in p.norma):
            p.usulan = (f"Mengingat ketentuan ini menetapkan jangka waktu ({', '.join(p.batas_waktu)}), "
                        "kami mengusulkan agar jangka waktu tersebut mempertimbangkan kesiapan sistem "
                        "dan infrastruktur teknologi informasi pelaku usaha jasa keuangan.")
            p.dasar.append(f"batas waktu: {', '.join(p.batas_waktu)}")
        elif p.peralihan:
            p.usulan = ("Kami mengusulkan agar masa penyesuaian memperhitungkan waktu pengembangan dan "
                        "pengujian sistem yang diperlukan.")
        elif "Larangan" in p.norma:
            p.usulan = ("Kami mengusulkan agar cakupan larangan ini dirumuskan secara jelas, termasuk "
                        "pengecualian yang diperlukan bagi kebutuhan operasional sistem.")
        elif "Kewajiban" in p.norma or "Pelaporan" in p.norma:
            p.usulan = ("Kami mengusulkan agar ketentuan teknis pelaksanaannya diatur lebih lanjut secara "
                        "jelas sehingga dapat diterapkan dan diawasi secara konsisten.")
        else:
            p.usulan = ("Pada prinsipnya kami dapat memahami ketentuan ini; penerapannya perlu menjadi "
                        "perhatian dalam pengawasan.")
    p.narasi = " ".join(kal)


def _ayat_terkait(teks: str, profil: Profil, utamakan: int | None = None) -> tuple[int | None, str]:
    """Ayat yang paling menyentuh topik unit — narasi menunjuk ayat itu, bukan seluruh pasal."""
    from hero.analysis.structured import split_ayat

    units = [(n, t) for n, t in (split_ayat(teks) or []) if t and t.strip()]
    if len(units) < 2:
        return None, teks
    for n, t in units:
        if utamakan is not None and n == utamakan:
            return n, t
    skor = [(nilai_pasal(t, profil)[0], -i, n, t) for i, (n, t) in enumerate(units)]
    best = max(skor)
    return (best[2], best[3]) if best[0] > 0 else (units[0][0], units[0][1])


_KECIL = {"oleh", "dan", "atau", "di", "ke", "dari", "yang", "untuk", "pada", "dalam", "bagi", "serta",
          "terhadap", "tentang", "atas", "dengan", "melalui", "sebagai", "termasuk", "berupa"}


def _judul_rapi(judul: str) -> str:
    kata = judul.lower().split()
    return " ".join(w if (i and w in _KECIL) else (
        w.upper() if w.strip("(),.") in {"ti", "ojk", "bpr", "bprs", "pojk", "seojk", "uus", "lpe"}
        else w.capitalize()) for i, w in enumerate(kata))


def _dampak(profil: Profil, p: PasalTanggapan) -> str:
    dampak = {t.id: t.dampak for t in profil.topik}
    bagian = list(dict.fromkeys(dampak.get(t.id) or t.nama for t in p.topik[:2]))
    return " serta ".join(bagian)


# ---------------------------------------------------------------------------
# rakit laporan
# ---------------------------------------------------------------------------

@dataclass
class LaporanTanggapan:
    versi: str
    profil: dict[str, Any]
    draft: dict[str, Any]
    surat: dict[str, Any]
    pasal_berdampak: list[PasalTanggapan]
    kelengkapan: dict[str, Any]
    ringkasan: dict[str, Any]
    catatan: str = CATATAN

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ISTILAH = {"konflik": "Kontradiktif", "duplikasi": "Tumpang Tindih", "memperjelas": "Selaras / Melengkapi",
            "menggantikan": "Menggantikan", "pasal_baru": "Pasal Baru"}


def _temuan_per_pasal(harmonisasi: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t in (harmonisasi or {}).get("temuan") or []:
        k = _kunci(t.get("pasal_draft") or "")
        if k and k not in out:
            out[k] = {"jenis": t.get("jenis"), "istilah": _ISTILAH.get(t.get("jenis"), t.get("jenis")),
                      "alasan": t.get("alasan") or "", "perbedaan": t.get("perbedaan") or [],
                      "pembanding": t.get("pembanding"), "keyakinan": t.get("keyakinan")}
    return out


def rapikan_judul(judul: str) -> str:
    """"… tentang PERUBAHAN ATAS … KRIPTO PERUBAHAN ATAS … KRIPTO" → satu perihal, huruf judul.

    Katalog menyusun judul dari kolom judul + perihal; bila keduanya memuat perihal yang sama,
    perihal tertulis dua kali, dan teks sumber JDIH ditulis kapital semua."""
    t = _WS.sub(" ", judul or "").strip()
    m = re.match(r"(.*?\btentang\s+)(.*)$", t, re.IGNORECASE | re.DOTALL)
    awal, perihal = (m.group(1), m.group(2)) if m else ("", t)
    kata = perihal.split()
    for n in range(len(kata) // 2, 2, -1):       # potongan berulang terpanjang di ekor perihal
        if [w.upper() for w in kata[-2 * n:-n]] == [w.upper() for w in kata[-n:]]:
            kata = kata[:-n]
            break
    perihal = " ".join(kata)
    huruf = [c for c in perihal if c.isalpha()]
    if huruf and sum(c.isupper() for c in huruf) / len(huruf) > 0.8:
        perihal = _judul_rapi(perihal)
    return (awal + perihal).strip()


def _perihal(judul: str) -> str:
    m = re.search(r"\btentang\b\s+(.*)", judul or "", re.IGNORECASE | re.DOTALL)
    return _WS.sub(" ", m.group(1) if m else (judul or "")).strip()


def susun_tanggapan(judul: str, articles: list[dict[str, Any]], profil: Profil,
                    harmonisasi: dict[str, Any] | None = None, sudah: dict[str, str] | None = None,
                    *, sertakan_tidak_berdampak: bool = False) -> LaporanTanggapan:
    """Draft tanggapan atas satu draft peraturan dari sudut pandang ``profil``.

    ``articles``     pasal draft: [{"number", "text", "page"}] (sama dengan masukan harmonisasi)
    ``harmonisasi``  ``Report.to_dict()`` dari harmonisasi draft yang sama (opsional) — temuan
                     kontradiktif/tumpang tindih/menggantikan ikut masuk narasi dan checklist.
    ``sudah``        tanggapan yang sudah ditulis analis per pasal, untuk pemeriksaan kelengkapan.
    """
    judul = rapikan_judul(judul)
    temuan = _temuan_per_pasal(harmonisasi)
    seen: set[str] = set()
    hasil: list[PasalTanggapan] = []
    for a in articles:
        nomor = str(a.get("number") or "").strip()
        teks = _WS.sub(" ", a.get("text") or "").strip()
        if not nomor or len(teks) < 30 or nomor.upper() in seen:
            continue
        seen.add(nomor.upper())
        label = nomor if nomor.lower().startswith(("pasal", "diktum", "bagian", "angka")) else f"Pasal {nomor}"
        skor, kena = nilai_pasal(teks, profil)
        p = PasalTanggapan(label, a.get("page"), teks, skor, _tingkat(skor), kena, _alasan(profil, kena),
                           _norma(teks),
                           batas_waktu=[f"{m.group(1)} {m.group(2)}" for m in _BATAS_WAKTU.finditer(teks)][:3],
                           peralihan=bool(_PERALIHAN.search(teks)),
                           definisi=bool(_DEFINISI.match(teks)),
                           harmonisasi=temuan.get(_kunci(label)))
        p.wajib, p.dasar_wajib = wajib_ditanggapi(p, profil)
        hasil.append(p)
    for p in hasil:
        if p.wajib or p.skor > 0:
            susun_narasi(p, profil)
    kelengkapan = periksa_kelengkapan(hasil, sudah)
    berdampak = [p for p in hasil if p.skor > 0 or p.wajib or sertakan_tidak_berdampak]
    per_tingkat = {t: sum(p.tingkat == t for p in hasil) for t in ("tinggi", "sedang", "rendah", "tidak")}
    perihal = _perihal(judul)
    surat = _surat(judul, perihal, profil, [p for p in hasil if p.wajib], harmonisasi, len(hasil))
    ringkasan = {"pasal_draft": len(hasil), "pasal_berdampak": len(berdampak),
                 "per_tingkat": per_tingkat, "wajib_ditanggapi": kelengkapan["wajib"],
                 "dengan_temuan_harmonisasi": sum(1 for p in hasil if p.harmonisasi),
                 "topik_terbanyak": _topik_terbanyak(hasil)}
    return LaporanTanggapan(VERSION, profil.ringkas(), {"judul": judul, "perihal": perihal,
                                                         "pasal": len(hasil)},
                            surat, berdampak, kelengkapan, ringkasan)


def _topik_terbanyak(hasil: list[PasalTanggapan]) -> list[dict[str, Any]]:
    hitung: dict[str, int] = {}
    for p in hasil:
        for t in p.topik:
            hitung[t.nama] = hitung.get(t.nama, 0) + 1
    return [{"topik": k, "pasal": v} for k, v in sorted(hitung.items(), key=lambda x: -x[1])[:5]]


def _surat(judul: str, perihal: str, profil: Profil, wajib: list[PasalTanggapan],
           harmonisasi: dict[str, Any] | None, n_pasal: int) -> dict[str, Any]:
    """Susunan catatan dinas (Weekly #10). Bentuk baku surat tanggapan DPEA (TD-08) belum diterima;
    struktur ini mengikuti kop yang sudah disepakati dan butir yang dipakai ekspor Catatan Dinas backend."""
    nama = judul.strip()
    pokok = [{"pasal": p.pasal, "halaman": p.halaman, "narasi": p.narasi, "usulan": p.usulan,
              "temuan": (p.harmonisasi or {}).get("istilah"), "dasar": p.dasar} for p in wajib]
    lain: list[str] = []
    for r in (harmonisasi or {}).get("rujukan") or []:
        if r.get("status") == "dicabut" and r.get("relasi") == "dirujuk":
            lain.append(f"Draft merujuk {str(r.get('key', '')).replace('|', ' ')} yang telah dicabut; "
                        "kami mengusulkan rujukan disesuaikan dengan peraturan penggantinya.")
    if not pokok:
        pembuka_pokok = (f"Berdasarkan penelaahan dari sudut pandang {profil.nama}, tidak terdapat pasal "
                         f"yang secara langsung berdampak pada tugas dan fungsi unit.")
    else:
        pembuka_pokok = (f"Berdasarkan penelaahan dari sudut pandang {profil.nama}, terdapat {len(pokok)} "
                         f"pasal yang perlu mendapat tanggapan, yaitu:")
    return {
        "kepada": "Kepala Departemen",
        "dari": "Analis Eksekutif",
        "hal": f"Tanggapan atas {nama}",
        "tanggal": "(diisi manual)",
        "pembuka": (f"Sehubungan dengan permintaan tanggapan atas {nama}, bersama ini kami sampaikan "
                    f"tanggapan dari sudut pandang {profil.nama} sebagai berikut:"),
        "butir": [
            {"nomor": 1, "judul": "Latar Belakang",
             "isi": (f"Draft mengatur tentang {perihal or nama} dan terdiri atas {n_pasal} pasal yang "
                     f"terbaca. Penelaahan difokuskan pada pasal yang berdampak pada tugas {profil.nama}, "
                     f"yaitu {profil.tugas[:1].lower()}{profil.tugas[1:].rstrip('.')}.")},
            {"nomor": 2, "judul": "Pokok Tanggapan", "isi": pembuka_pokok, "pasal": pokok},
            *([{"nomor": 3, "judul": "Hal Lain", "isi": " ".join(lain)}] if lain else []),
        ],
        "penutup": "Demikian kami sampaikan, atas perhatian Bapak/Ibu kami ucapkan terima kasih.",
    }


def render_markdown(lap: LaporanTanggapan, maks_pasal: int | None = None) -> str:
    """Draft tanggapan berformat catatan dinas (untuk ditelaah/disalin analis; ekspor resmi di backend)."""
    s = lap.surat
    out = [f"**Kepada** : {s['kepada']}  ", f"**Dari** : {s['dari']}  ", f"**Hal** : {s['hal']}  ",
           f"**Tanggal** : {s['tanggal']}", "", s["pembuka"], ""]
    for b in s["butir"]:
        out.append(f"{b['nomor']}. **{b['judul']}**  ")
        out.append(f"   {b['isi']}")
        pasal = b.get("pasal") or []
        for i, p in enumerate(pasal[:maks_pasal] if maks_pasal else pasal):
            huruf = chr(ord("a") + i) if i < 26 else f"{i + 1}"
            tag = f" *(temuan harmonisasi: {p['temuan']})*" if p.get("temuan") else ""
            out.append(f"   {huruf}. {p['narasi']}{tag} {p['usulan']}")
        if maks_pasal and len(pasal) > maks_pasal:
            out.append(f"   … {len(pasal) - maks_pasal} pasal lain (lihat keluaran JSON).")
        out.append("")
    out += [s["penutup"], "", f"> {lap.catatan}", "",
            f"Kelengkapan: {lap.kelengkapan['keterangan']}. Pasal berdampak: "
            f"{lap.ringkasan['pasal_berdampak']} dari {lap.ringkasan['pasal_draft']} "
            f"(tinggi {lap.ringkasan['per_tingkat']['tinggi']}, sedang {lap.ringkasan['per_tingkat']['sedang']}, "
            f"rendah {lap.ringkasan['per_tingkat']['rendah']})."]
    return "\n".join(out)
