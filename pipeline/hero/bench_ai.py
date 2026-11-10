"""Benchmark mode AI-Assisted: banding model Gemini pada SATU dokumen yang sama.

Pertanyaan yang dijawab: model mana yang memberi narasi paling setia dengan
biaya dan latensi yang masuk akal, dan — bila semuanya buruk — apakah sebabnya
modelnya atau masukannya.

Yang diukur per model (tiap model diulang ``runs`` kali, berurutan, bukan
paralel, supaya latensi bersih):

* **Latensi**   — detik dinding per panggilan (median, maks), token/detik.
* **Biaya**     — token masuk, keluar, dan *thinking* × harga per 1 juta token.
  Token thinking ditagih sebagai keluaran; ``usage.output_tokens`` produksi
  (``candidates_token_count``) TIDAK memuatnya, jadi biaya di sana terkecil-kecilkan.
* **Kelulusan verifikator** — aturan keras produksi (``verify``): angka, nomor
  pasal, rujukan fakta. Gagal = pengguna melihat hasil Deterministik.
* **Kualitas otomatis** (tanpa model penilai; semua dihitung dari fakta):
  ``cakupan_poin`` (fakta F yang diparafrase), ``cakupan_kategori`` (kategori
  norma yang tersentuh ringkasan), ``recall_butir`` (butir wajib dokumen uji
  yang muncul), ``modalitas_bergeser`` ("dikenai" → "dapat dikenai"),
  ``kebaruan`` (kata di ringkasan yang tidak ada di fakta rujukannya — proxy
  elaborasi/halusinasi), ``mirip_deterministik`` (≈1 berarti AI hanya menyalin),
  ``konsistensi`` (kemiripan fakta yang dirujuk antar-ulangan).
* **Telaah manual** — keluaran lengkap tiap model dan lembar nilai kosong.

Angka otomatis TIDAK menggantikan telaah manusia: ia menyaring model yang jelas
buruk dan menunjukkan *jenis* kesalahannya.

Dokumen uji harus berklasifikasi publik: teksnya dikirim ke layanan Google.
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from hero.analysis.ai import (_finish_reason_gemini, build_facts, gemini_minta, thinking_config,
                              usage_gemini, verify)

# ---------------------------------------------------------------------------
# Harga — USD per 1 juta token, kelas Standard berbayar.
# Sumber: https://aistudio.google.com/docs/pricing (dibaca 10 Nov 2026; halaman
# tanpa tanggal terbit dan terpotong di ujungnya). HARGA BERUBAH: periksa ulang
# sebelum angka dipakai di laporan. ``setelah`` = (berlaku mulai, masuk, keluar).
# ---------------------------------------------------------------------------
HARGA_SUMBER = "https://aistudio.google.com/docs/pricing (dibaca 2026-11-10)"
HARGA: dict[str, dict[str, Any]] = {
    "gemini-2.5-flash-lite": {"masuk": 0.10, "keluar": 0.40, "catatan": ""},
    "gemini-2.5-flash": {"masuk": 0.30, "keluar": 2.50,
                         "catatan": "ditandai deprecated; dialihkan ke gemini-3.5-flash-lite 1 Des 2026"},
    "gemini-2.5-pro": {"masuk": 1.25, "keluar": 10.00,
                       "catatan": "ditandai deprecated; dialihkan ke gemini-3.8-flash 1 Des 2026; harga ≤200k token"},
    "gemini-3.1-flash-lite": {"masuk": 0.25, "keluar": 1.50, "catatan": ""},
    "gemini-3.5-flash-lite": {"masuk": 0.30, "keluar": 2.50, "catatan": ""},
    "gemini-3-flash-preview": {"masuk": 0.50, "keluar": 3.00, "catatan": "preview"},
    "gemini-3.1-pro-preview": {"masuk": 2.00, "keluar": 12.00, "catatan": "preview; harga ≤200k token"},
    "gemini-3.6-flash": {"masuk": 0.75, "keluar": 3.75, "setelah": ("2027-01-01", 1.50, 7.50), "catatan": ""},
    "gemini-3.8-flash": {"masuk": 0.75, "keluar": 3.75, "setelah": ("2027-01-01", 1.50, 7.50), "catatan": ""},
    "gemini-4-argon": {"masuk": 2.00, "keluar": 10.00, "setelah": ("2026-12-01", 4.00, 20.00), "catatan": ""},
}

# Butir yang HARUS muncul dari dokumen uji tertentu (daftar regresi dari QA
# 8 Nov 2026), dicocokkan sebagai potongan teks huruf kecil. Kunci = id dokumen
# backend. Dokumen lain: beri lewat --butir.
BUTIR_WAJIB: dict[str, list[str]] = {
    "106": ["teguran tertulis", "larangan untuk menerbitkan produk", "pembekuan kegiatan usaha",
            "ekspansi", "kegiatan usaha baru", "penilaian faktor tata kelola", "denda"],
}

_MODAL_BARU = ("dapat", "boleh", "sebaiknya", "mungkin", "umumnya", "biasanya", "diharapkan", "seharusnya")
_MODAL_ASAL = (("wajib", ("wajib", "harus", "diwajibkan", "kewajiban")),
               ("dilarang", ("dilarang", "tidak boleh", "larangan", "tidak diperkenankan")),
               ("dikenai", ("dikenai", "dikenakan", "sanksi")))
_STOP = frozenset("yang dalam dengan untuk pada atau dari oleh adalah akan telah dapat serta bagi tersebut "
                  "sebagaimana dimaksud ayat pasal peraturan antara lain ini itu para juga sesuai".split())
_KATA = re.compile(r"[a-zA-Z]{5,}")


# ---------------------------------------------------------------------------
# Metrik (murni; diuji tanpa jaringan)
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _kata(s: str) -> set[str]:
    return {w for w in _KATA.findall((s or "").lower()) if w not in _STOP}


def _ada(kata: str, teks: str) -> bool:
    return re.search(rf"\b{re.escape(kata)}\b", teks) is not None


def kategori_fakta(f: dict[str, Any]) -> str | None:
    m = re.match(r"\[([^\]]+)\]", f.get("teks") or "")
    return m.group(1) if m else None


def skor_keluaran(output: dict[str, Any], facts: list[dict[str, Any]], *,
                  butir: list[str] | None = None, ringkasan_deterministik: str = "") -> dict[str, Any]:
    """Kualitas satu keluaran model terhadap fakta yang diberikan kepadanya."""
    by_id = {f["id"]: f for f in facts}
    kal = output.get("ringkasan") or []
    poin = output.get("poin_kunci") or []
    f_ids = [f["id"] for f in facts if re.fullmatch(r"F\d+", f["id"])]

    dirujuk = {i for s in kal for i in (s.get("fakta") or [])}
    teks_ringkasan = " ".join(s.get("kalimat", "") for s in kal)
    teks_semua = teks_ringkasan + " " + " ".join(p.get("parafrase", "") for p in poin)

    kategori = {kategori_fakta(by_id[i]) for i in f_ids if kategori_fakta(by_id[i])}
    tersentuh = {kategori_fakta(by_id[i]) for i in dirujuk if i in by_id and kategori_fakta(by_id[i])}

    # Pergeseran modalitas: kata modal yang tidak ada di fakta asalnya, atau
    # kewajiban/larangan/sanksi yang hilang dari parafrasenya.
    bergeser: list[str] = []
    pasangan = [(p.get("parafrase", ""), by_id[p["fakta"]]["teks"], p["fakta"])
                for p in poin if p.get("fakta") in by_id]
    for s in kal:
        sumber = " ".join(by_id[i]["teks"] for i in (s.get("fakta") or []) if i in by_id)
        pasangan.append((s.get("kalimat", ""), sumber, "+".join(s.get("fakta") or [])))
    for hasil, sumber, ref in pasangan:
        h, s_ = _norm(hasil), _norm(sumber)
        for m in _MODAL_BARU:
            if _ada(m, h) and not _ada(m, s_):
                bergeser.append(f"{ref}: '{m}' ditambahkan")
        for asal, pengganti in _MODAL_ASAL:
            if _ada(asal, s_) and not any(_ada(x, h) for x in pengganti):
                bergeser.append(f"{ref}: '{asal}' hilang")

    sumber_kal = set()
    for s in kal:
        sumber_kal |= set().union(*[_kata(by_id[i]["teks"]) for i in (s.get("fakta") or []) if i in by_id] or [set()])
    kata_ringkasan = _kata(teks_ringkasan)
    kebaruan = (len(kata_ringkasan - sumber_kal) / len(kata_ringkasan)) if kata_ringkasan else 0.0

    det = _kata(ringkasan_deterministik)
    mirip = (len(kata_ringkasan & det) / len(kata_ringkasan | det)) if (kata_ringkasan | det) else 0.0

    hasil: dict[str, Any] = {
        "kalimat": len(kal),
        "kata_per_kalimat": round(statistics.mean(len(s.get("kalimat", "").split()) for s in kal), 1) if kal else 0,
        "parafrase_lebih_30_kata": sum(1 for p in poin if len(p.get("parafrase", "").split()) > 30),
        "cakupan_poin": round(len({p.get("fakta") for p in poin} & set(f_ids)) / len(f_ids), 3) if f_ids else None,
        "cakupan_kategori": round(len(tersentuh & kategori) / len(kategori), 3) if kategori else None,
        "kategori_terlewat": sorted(kategori - tersentuh),
        "modalitas_bergeser": len(bergeser),
        "modalitas_rincian": bergeser[:8],
        "kebaruan": round(kebaruan, 3),
        "mirip_deterministik": round(mirip, 3),
        "fakta_dirujuk": sorted(dirujuk),
    }
    if butir:
        low = _norm(teks_semua)
        low_r = _norm(teks_ringkasan)
        hasil["recall_butir"] = round(sum(1 for b in butir if _norm(b) in low) / len(butir), 3)
        hasil["recall_butir_ringkasan"] = round(sum(1 for b in butir if _norm(b) in low_r) / len(butir), 3)
        hasil["butir_terlewat"] = [b for b in butir if _norm(b) not in low]
    return hasil


def biaya_usd(model: str, masuk: int, keluar: int, berpikir: int, *, hari: date | None = None) -> float | None:
    h = HARGA.get(model)
    if not h:
        return None
    pm, pk = h["masuk"], h["keluar"]
    if h.get("setelah") and (hari or date.today()).isoformat() >= h["setelah"][0]:
        pm, pk = h["setelah"][1], h["setelah"][2]
    return (masuk * pm + (keluar + berpikir) * pk) / 1_000_000


def konsistensi(runs: list[dict[str, Any]]) -> float | None:
    """Jaccard rata-rata himpunan fakta yang dirujuk antar-ulangan (1 = selalu sama)."""
    himp = [set(r["skor"]["fakta_dirujuk"]) for r in runs if r.get("skor")]
    if len(himp) < 2:
        return None
    pas = [len(a & b) / len(a | b) if (a | b) else 1.0 for i, a in enumerate(himp) for b in himp[i + 1:]]
    return round(statistics.mean(pas), 3)


# ---------------------------------------------------------------------------
# Panggilan Gemini — konfigurasi SAMA dengan produksi (AiNarrator._minta_gemini)
# kecuali yang sengaja divariasikan lewat opsi.
# ---------------------------------------------------------------------------
@dataclass
class Varian:
    model: str
    suhu: float | None = 0.0
    berpikir: dict[str, Any] | None = None         # diteruskan apa adanya sebagai thinking_config
    batas_keluaran: int | None = None
    batas_detik: float | None = None

    @property
    def label(self) -> str:
        sfx = []
        if self.suhu != 0.0:
            sfx.append(f"suhu={'bawaan' if self.suhu is None else self.suhu}")
        if self.berpikir:
            sfx.append("berpikir=" + json.dumps(self.berpikir, separators=(",", ":")))
        if self.batas_keluaran:
            sfx.append(f"maks={self.batas_keluaran}")
        if self.batas_detik:
            sfx.append(f"batas={self.batas_detik:g}s")
        return self.model + (f" [{', '.join(sfx)}]" if sfx else "")


def panggil_gemini(client: Any, v: Varian, user: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = gemini_minta(client, v.model, user, suhu=v.suhu, berpikir=v.berpikir,
                         batas_keluaran=v.batas_keluaran, batas_detik=v.batas_detik)
    except Exception as exc:                                # noqa: BLE001 — setiap galat adalah data benchmark
        return {"galat": f"{type(exc).__name__}: {str(exc)[:300]}", "detik": time.perf_counter() - t0}
    u = usage_gemini(r)
    return {"detik": time.perf_counter() - t0, "masuk": u["input_tokens"] or 0, "keluar": u["output_tokens"] or 0,
            "berpikir": u["thinking_tokens"] or 0, "henti": _finish_reason_gemini(r),
            "teks": getattr(r, "text", None), "versi_model": getattr(r, "model_version", None)}


def jalankan_satu(client: Any, v: Varian, facts: list[dict[str, Any]], *, butir: list[str] | None,
                  ringkasan_det: str) -> dict[str, Any]:
    user = ("FAKTA (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
            + "\n\nTulis ringkasan dan poin_kunci sesuai aturan.")
    r = panggil_gemini(client, v, user)
    out: dict[str, Any] = {"detik": round(r["detik"], 3)}
    if "galat" in r:
        return out | {"galat": r["galat"]}
    out |= {"masuk": r["masuk"], "keluar": r["keluar"], "berpikir": r["berpikir"], "versi_model": r["versi_model"],
            "usd": biaya_usd(v.model, r["masuk"], r["keluar"], r["berpikir"])}
    total_keluar = r["keluar"] + r["berpikir"]
    out["token_per_detik"] = round(total_keluar / r["detik"], 1) if r["detik"] > 0 else None
    if r["henti"]:
        return out | {"galat": r["henti"]}
    try:
        data = json.loads(r["teks"] or "")
    except ValueError:
        return out | {"galat": "keluaran bukan JSON valid", "mentah": (r["teks"] or "")[:400]}
    masalah = verify(data, facts)
    out |= {"lulus_verifikasi": not masalah, "pelanggaran": masalah[:6], "keluaran": data,
            "skor": skor_keluaran(data, facts, butir=butir, ringkasan_deterministik=ringkasan_det)}
    return out


# ---------------------------------------------------------------------------
# Orkestrasi + laporan
# ---------------------------------------------------------------------------
def model_tersedia(client: Any) -> list[str]:
    """Model generateContent yang benar-benar terlihat oleh kunci ini."""
    ada = []
    for m in client.models.list():
        aksi = getattr(m, "supported_actions", None) or []
        if aksi and "generateContent" not in aksi:
            continue
        ada.append(str(m.name).removeprefix("models/"))
    return sorted(ada)


def _agg(runs: list[dict[str, Any]], kunci: str, fn: Callable = statistics.median) -> Any:
    v = [r[kunci] for r in runs if r.get(kunci) is not None]
    return round(fn(v), 4) if v else None


def _skor_agg(runs: list[dict[str, Any]], kunci: str) -> Any:
    v = [r["skor"][kunci] for r in runs if r.get("skor") and r["skor"].get(kunci) is not None]
    return round(statistics.mean(v), 3) if v else None


def ringkas(varian: Varian, runs: list[dict[str, Any]], *, korpus: int) -> dict[str, Any]:
    ok = [r for r in runs if "galat" not in r]
    usd = _agg(ok, "usd", statistics.mean)
    return {
        "model": varian.label, "ulangan": len(runs), "galat": len(runs) - len(ok),
        "contoh_galat": next((r["galat"] for r in runs if "galat" in r), None),
        "detik_median": _agg(ok, "detik"), "detik_maks": _agg(ok, "detik", max),
        "token_masuk": _agg(ok, "masuk"), "token_keluar": _agg(ok, "keluar"), "token_berpikir": _agg(ok, "berpikir"),
        "token_per_detik": _agg(ok, "token_per_detik"),
        "usd_per_dokumen": usd,
        "usd_per_1000_dokumen": round(usd * 1000, 3) if usd is not None else None,
        "usd_seluruh_korpus": round(usd * korpus, 2) if usd is not None else None,
        "lulus_verifikasi": round(sum(1 for r in ok if r.get("lulus_verifikasi")) / len(runs), 3) if runs else None,
        "terpotong": sum(1 for r in runs if "terpotong" in str(r.get("galat") or "").lower()),
        "cakupan_poin": _skor_agg(ok, "cakupan_poin"), "cakupan_kategori": _skor_agg(ok, "cakupan_kategori"),
        "recall_butir": _skor_agg(ok, "recall_butir"), "recall_butir_ringkasan": _skor_agg(ok, "recall_butir_ringkasan"),
        "modalitas_bergeser": _skor_agg(ok, "modalitas_bergeser"), "kebaruan": _skor_agg(ok, "kebaruan"),
        "mirip_deterministik": _skor_agg(ok, "mirip_deterministik"), "konsistensi": konsistensi(ok),
        "tanpa_harga": varian.model not in HARGA,
    }


def _fmt(x: Any, nd: int = 2) -> str:
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def markdown(meta: dict[str, Any], ringkasan: list[dict[str, Any]], hasil: dict[str, list[dict[str, Any]]],
             facts: list[dict[str, Any]]) -> str:
    L = [f"# Benchmark mode AI — {meta['dokumen']}", "",
         f"*Dijalankan {meta['waktu']} · {meta['ulangan']} ulangan/model · prompt `{meta['prompt']}` · "
         f"{len(facts)} fakta dikirim.*", "",
         f"Harga: {HARGA_SUMBER}. **Periksa ulang sebelum dikutip** — harga dan nama model berubah.", ""]
    L += ["## Perbandingan", "",
          "| Model | Median s | Maks s | Token masuk | Keluar | Berpikir | USD/dok | USD/1000 dok | USD korpus | Lulus verifikasi | Galat |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in ringkasan:
        L.append(f"| {r['model']}{' ⚠ harga tak dikenal' if r['tanpa_harga'] else ''} | {_fmt(r['detik_median'])} | "
                 f"{_fmt(r['detik_maks'])} | {_fmt(r['token_masuk'], 0)} | {_fmt(r['token_keluar'], 0)} | "
                 f"{_fmt(r['token_berpikir'], 0)} | {_fmt(r['usd_per_dokumen'], 5)} | {_fmt(r['usd_per_1000_dokumen'], 2)} | "
                 f"{_fmt(r['usd_seluruh_korpus'], 2)} | {_fmt(r['lulus_verifikasi'], 2)} | {r['galat']}/{r['ulangan']} |")
    L += ["", "## Kualitas otomatis", "",
          "| Model | Cakupan poin | Cakupan kategori | Recall butir | Recall butir (ringkasan) | Modalitas bergeser | Kebaruan | Mirip Deterministik | Konsistensi |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in ringkasan:
        L.append(f"| {r['model']} | {_fmt(r['cakupan_poin'])} | {_fmt(r['cakupan_kategori'])} | {_fmt(r['recall_butir'])} | "
                 f"{_fmt(r['recall_butir_ringkasan'])} | {_fmt(r['modalitas_bergeser'], 1)} | {_fmt(r['kebaruan'])} | "
                 f"{_fmt(r['mirip_deterministik'])} | {_fmt(r['konsistensi'])} |")
    L += ["", "Cara baca: *cakupan* dan *recall* makin tinggi makin baik; *modalitas bergeser* dan *kebaruan* makin rendah "
          "makin baik; *mirip Deterministik* mendekati 1 berarti AI hanya menyalin; *konsistensi* 1 = ulangan selalu "
          "merujuk fakta yang sama.", ""]
    galat = [r for r in ringkasan if r["contoh_galat"]]
    if galat:
        L += ["## Galat", ""] + [f"- **{r['model']}** ({r['galat']}/{r['ulangan']}): {r['contoh_galat']}" for r in galat] + [""]
    L += ["## Fakta yang dikirim ke model", "", "Pembanding untuk telaah: semua yang boleh dipakai model hanya ini.", ""]
    L += [f"- `{f['id']}` {f.get('pasal') or ''} — {f['teks'][:240]}" for f in facts] + [""]
    L += ["## Keluaran untuk telaah manual", ""]
    for label, runs in hasil.items():
        L += [f"### {label}", ""]
        for i, r in enumerate(runs, 1):
            if "galat" in r:
                L += [f"**Ulangan {i}:** galat — {r['galat']}", ""]
                continue
            L += [f"**Ulangan {i}** · {r['detik']} s · verifikasi {'lulus' if r['lulus_verifikasi'] else 'GAGAL'}"
                  + (f" ({'; '.join(r['pelanggaran'][:2])})" if r["pelanggaran"] else ""), ""]
            for s in r["keluaran"]["ringkasan"]:
                L.append(f"- {s['kalimat']}  *[{', '.join(s['fakta'])}]*")
            L += ["", "Poin kunci:"]
            L += [f"- `{p['fakta']}` {p['parafrase']}" for p in r["keluaran"]["poin_kunci"]]
            sk = r["skor"]
            if sk["modalitas_rincian"]:
                L += ["", "Pergeseran modalitas: " + "; ".join(sk["modalitas_rincian"])]
            if sk.get("butir_terlewat"):
                L += ["", "Butir wajib terlewat: " + ", ".join(sk["butir_terlewat"])]
            L.append("")
    return "\n".join(L)


def lembar_nilai(hasil: dict[str, list[dict[str, Any]]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["model", "ulangan", "kelengkapan_1_5", "ketepatan_1_5", "kewajaran_bahasa_1_5",
                "butir_penting_terlewat", "kalimat_menyesatkan", "catatan"])
    for label, runs in hasil.items():
        for i, r in enumerate(runs, 1):
            if "galat" not in r:
                w.writerow([label, i, "", "", "", "", "", ""])
    return buf.getvalue()


@dataclass
class Laporan:
    meta: dict[str, Any]
    ringkasan: list[dict[str, Any]]
    hasil: dict[str, list[dict[str, Any]]]
    facts: list[dict[str, Any]] = field(default_factory=list)

    def tulis(self, folder: Path, nama: str) -> dict[str, Path]:
        folder.mkdir(parents=True, exist_ok=True)
        p = {"md": folder / f"{nama}.md", "json": folder / f"{nama}.json", "csv": folder / f"{nama}_nilai.csv"}
        p["md"].write_text(markdown(self.meta, self.ringkasan, self.hasil, self.facts), encoding="utf-8")
        p["json"].write_text(json.dumps({"meta": self.meta, "ringkasan": self.ringkasan, "hasil": self.hasil,
                                         "fakta": self.facts}, ensure_ascii=False, indent=1), encoding="utf-8")
        p["csv"].write_text(lembar_nilai(self.hasil), encoding="utf-8")
        return p


def jalankan(client: Any, analisis: Any, varian: list[Varian], *, ulangan: int, dokumen: str,
             butir: list[str] | None, korpus: int = 1529, jeda: float = 1.0, max_fakta: int = 24,
             progress: Callable[[str], None] = lambda m: None) -> Laporan:
    from hero.analysis.ai import PROMPT_VERSION

    facts = build_facts(analisis, max_fakta)
    det = analisis.ringkasan_teks()
    hasil: dict[str, list[dict[str, Any]]] = {}
    for v in varian:
        runs = []
        for i in range(ulangan):
            progress(f"{v.label} — ulangan {i + 1}/{ulangan}")
            runs.append(jalankan_satu(client, v, facts, butir=butir, ringkasan_det=det))
            time.sleep(jeda)
        hasil[v.label] = runs
    ring = [ringkas(v, hasil[v.label], korpus=korpus) for v in varian]
    meta = {"dokumen": dokumen, "waktu": time.strftime("%Y-%m-%d %H:%M"), "ulangan": ulangan,
            "prompt": PROMPT_VERSION, "jumlah_fakta": len(facts), "korpus": korpus}
    return Laporan(meta, ring, hasil, facts)
