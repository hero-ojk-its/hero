"""Uji latensi, throughput, dan kapasitas server API HERO.

Menjawab tiga pertanyaan dengan angka terukur, bukan perkiraan:

1. **Latensi** — berapa lama tiap endpoint menjawab saat dipakai satu orang?
   (p50/p95/p99, dibandingkan dengan NFR-02: pencarian < 3 detik).
2. **Kapasitas** — berapa permintaan per detik yang sanggup dilayani, dan pada
   berapa pengguna serentak latensi/kegagalan mulai melewati batas?
3. **Sumber daya** — berapa memori dan CPU server saat itu?

Cara kerja: beban *closed-loop* — N pengguna virtual, masing-masing mengirim
permintaan berikutnya begitu jawaban datang (tanpa jeda berpikir). Ini beban
terberat yang bisa diberikan N klien, jadi hasilnya batas bawah yang aman.
Untuk menerjemahkannya ke "berapa orang yang bisa memakai", throughput
dikalikan jeda berpikir pengguna sungguhan (``think_time``; manusia tidak
menekan tombol tiap milidetik). Itu perkiraan turunan dan dilabeli demikian.

Hanya pustaka standar + ``uvicorn`` yang sudah ada di ekstra ``api``. Server
diuji lewat HTTP sungguhan (soket, serialisasi JSON, middleware), bukan
``TestClient``, karena itulah yang dialami frontend.

Hanya permintaan **GET** yang dikirim — uji ini tidak mengubah data.
"""
from __future__ import annotations

import http.client
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

# Batas mutu. NFR-02 (SRS): respons pencarian < 3 detik untuk KB skala MVP.
SLO_MS_DEFAULT = 3000.0
GALAT_MAKS_DEFAULT = 0.01          # 1% permintaan gagal = tidak sehat
LEVEL_DEFAULT = (1, 2, 5, 10, 25, 50, 100)
THINK_TIME_DEFAULT = 5.0           # detik antar-aksi pengguna sungguhan
TIMEOUT_S = 30.0

QUERIES = ["keamanan siber", "tata kelola teknologi informasi", "manajemen risiko",
           "perlindungan konsumen", "bursa karbon", "kewajiban pelaporan",
           "sanksi administratif", "penyelenggara sistem elektronik"]


# --------------------------------------------------------------------------
# Skenario: apa yang ditembak, dan seberapa sering
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Endpoint:
    nama: str
    path: Callable[[random.Random, dict[str, Any]], str]
    bobot: int                      # kemunculan relatif dalam satu sesi pengguna
    berat: bool = False             # model semantik besar: diukur terpisah
    butuh: str | None = None        # kunci konteks yang harus ada (mis. doc_id)


def _q(rng: random.Random) -> str:
    """Satu atau dua frasa digabung: kueri yang beragam, agar cache (bila ada)
    tidak membuat hasil terlihat lebih baik daripada yang dialami pengguna."""
    return quote(" ".join(rng.sample(QUERIES, rng.choice((1, 1, 2)))))


def _doc(rng: random.Random, ctx: dict[str, Any]) -> str:
    return rng.choice(ctx["doc_ids"])


PROFIL_API: list[Endpoint] = [
    Endpoint("health", lambda r, c: "/api/health", 1),
    Endpoint("dashboard", lambda r, c: "/api/dashboard/summary", 3),
    Endpoint("kb-daftar", lambda r, c: f"/api/kb/documents?page={r.randint(1, 3)}&page_size=8", 6),
    Endpoint("kb-daftar-filter", lambda r, c: "/api/kb/documents?status=berlaku&sort=terbaru&page_size=20", 3),
    Endpoint("kb-cari-leksikal", lambda r, c: f"/api/kb/documents?q={_q(r)}&page_size=8", 5),
    Endpoint("kb-facets", lambda r, c: "/api/kb/facets", 2),
    Endpoint("kb-detail", lambda r, c: f"/api/kb/documents/{_doc(r, c)}", 4, butuh="doc_ids"),
    Endpoint("kb-relasi", lambda r, c: f"/api/kb/documents/{_doc(r, c)}/relations", 1, butuh="doc_ids"),
    Endpoint("analisa", lambda r, c: f"/api/analisa/{_doc(r, c)}", 3, butuh="doc_ids"),
    Endpoint("analisa-klausul", lambda r, c: f"/api/analisa/{_doc(r, c)}/klausul?kebutuhan={_q(r)}", 1,
             butuh="doc_ids"),
    Endpoint("cari-lexical", lambda r, c: f"/api/search?q={_q(r)}&method=lexical&k=10", 3),
    Endpoint("cari-lsa", lambda r, c: f"/api/search?q={_q(r)}&method=lsa&k=10", 2),
    Endpoint("cari-hybrid", lambda r, c: f"/api/search?q={_q(r)}&method=hybrid&k=10", 2),
    Endpoint("cari-semantik", lambda r, c: f"/api/search?q={_q(r)}&method=semantic&k=10", 1, berat=True),
    Endpoint("graf-statistik", lambda r, c: "/api/graph/stats", 1),
]

PROFIL_ML: list[Endpoint] = [
    Endpoint("health", lambda r, c: "/health", 1),
    Endpoint("dokumen", lambda r, c: "/dokumen?limit=50", 3),
    Endpoint("analisa", lambda r, c: f"/analisa/{_doc(r, c)}", 4, butuh="doc_ids"),
    Endpoint("analisa-klausul", lambda r, c: f"/analisa/{_doc(r, c)}/klausul?kebutuhan={_q(r)}", 2,
             butuh="doc_ids"),
    Endpoint("cari", lambda r, c: f"/cari?q={_q(r)}&metode=hybrid", 4),
    Endpoint("cari-lsa", lambda r, c: f"/cari?q={_q(r)}&metode=lsa", 2),
    Endpoint("cari-lexical", lambda r, c: f"/cari?q={_q(r)}&metode=lexical", 2),
]

PROFIL = {"api": PROFIL_API, "ml": PROFIL_ML}
APP_FACTORY = {"api": "hero.server.app:create_app", "ml": "hero.bridge.ml_api:app_from_env"}
HEALTH_PATH = {"api": "/api/health", "ml": "/health"}


# --------------------------------------------------------------------------
# Statistik
# --------------------------------------------------------------------------
def percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank: nilai nyata yang teramati, bukan interpolasi."""
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(-(-p / 100 * len(sorted_vals) // 1)) - 1))
    return sorted_vals[k]


def ringkas(ms: list[float]) -> dict[str, float]:
    s = sorted(ms)
    if not s:
        return {"n": 0, "min": 0, "p50": 0, "p95": 0, "p99": 0, "maks": 0, "rata": 0}
    return {"n": len(s), "min": round(s[0], 2), "p50": round(percentile(s, 50), 2),
            "p95": round(percentile(s, 95), 2), "p99": round(percentile(s, 99), 2),
            "maks": round(s[-1], 2), "rata": round(statistics.fmean(s), 2)}


@dataclass
class Hasil:
    """Pengukuran satu endpoint atau satu level beban."""
    ms: list[float] = field(default_factory=list)
    galat: int = 0
    contoh_galat: list[str] = field(default_factory=list)

    def tambah(self, durasi_ms: float, galat: str | None) -> None:
        if galat:
            self.galat += 1
            if len(self.contoh_galat) < 3 and galat not in self.contoh_galat:
                self.contoh_galat.append(galat)
        else:
            self.ms.append(durasi_ms)

    def gabung(self, lain: "Hasil") -> None:
        self.ms += lain.ms
        self.galat += lain.galat
        for g in lain.contoh_galat:
            if len(self.contoh_galat) < 3 and g not in self.contoh_galat:
                self.contoh_galat.append(g)

    @property
    def total(self) -> int:
        return len(self.ms) + self.galat

    @property
    def rasio_galat(self) -> float:
        return self.galat / self.total if self.total else 0.0


# --------------------------------------------------------------------------
# Klien HTTP (satu koneksi keep-alive per utas)
# --------------------------------------------------------------------------
class Klien:
    def __init__(self, base_url: str):
        u = urlsplit(base_url)
        self.host, self.port = u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)
        self.https = u.scheme == "https"
        self.prefix = u.path.rstrip("/")
        self.conn: http.client.HTTPConnection | None = None

    def _buka(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=TIMEOUT_S)

    def get(self, path: str) -> tuple[float, str | None, bytes]:
        """(ms, galat|None, badan). Galat = status ≥ 400, timeout, atau koneksi putus."""
        t0 = time.perf_counter()
        try:
            if self.conn is None:
                self.conn = self._buka()
            self.conn.request("GET", self.prefix + path, headers={"Accept": "application/json"})
            r = self.conn.getresponse()
            body = r.read()
            ms = (time.perf_counter() - t0) * 1000
            if r.status >= 400:
                return ms, f"HTTP {r.status}", body
            return ms, None, body
        except (OSError, http.client.HTTPException) as exc:
            self.tutup()
            return (time.perf_counter() - t0) * 1000, type(exc).__name__, b""

    def tutup(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None


def _pilih(rng: random.Random, eps: list[Endpoint]) -> Endpoint:
    return rng.choices(eps, weights=[e.bobot for e in eps], k=1)[0]


# --------------------------------------------------------------------------
# Server uji: dijalankan sendiri agar worker & sumber dayanya terkendali
# --------------------------------------------------------------------------
def port_bebas() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerUji:
    """Menjalankan ``uvicorn`` sebagai proses anak dan menyampling memori/CPU-nya."""

    def __init__(self, profil: str, config: Path, workers: int, cwd: Path):
        self.profil, self.config, self.workers, self.cwd = profil, config, workers, cwd
        self.port = port_bebas()
        self.proc: subprocess.Popen | None = None
        self.base_url = f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "ServerUji":
        env = dict(os.environ, HERO_CONFIG=str(self.config.resolve()))
        cmd = [sys.executable, "-m", "uvicorn", APP_FACTORY[self.profil], "--factory",
               "--host", "127.0.0.1", "--port", str(self.port), "--workers", str(self.workers),
               "--log-level", "warning"]
        self.proc = subprocess.Popen(cmd, cwd=self.cwd, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return self

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def tunggu_siap(self, timeout: float = 120.0) -> float:
        """Detik sampai /health menjawab 2xx — itu juga waktu *cold start* server."""
        t0 = time.perf_counter()
        k = Klien(self.base_url)
        while time.perf_counter() - t0 < timeout:
            if self.proc and self.proc.poll() is not None:
                err = (self.proc.stderr.read() or b"").decode("utf-8", "replace")[-800:] if self.proc.stderr else ""
                raise RuntimeError(f"server uji berhenti (kode {self.proc.returncode}): {err}")
            _, galat, _ = k.get(HEALTH_PATH[self.profil])
            if galat is None:
                k.tutup()
                return time.perf_counter() - t0
            time.sleep(0.25)
        raise RuntimeError(f"server uji tidak siap dalam {timeout:.0f} detik")

    def pids(self) -> list[int]:
        if not self.proc:
            return []
        try:
            out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return [self.proc.pid]
        kids: dict[int, list[int]] = {}
        for line in out.splitlines():
            try:
                p, pp = (int(x) for x in line.split())
            except ValueError:
                continue
            kids.setdefault(pp, []).append(p)
        todo, seen = [self.proc.pid], []
        while todo:
            p = todo.pop()
            seen.append(p)
            todo += kids.get(p, [])
        return seen

    def sumber_daya(self) -> dict[str, float]:
        """RSS total (MB) dan CPU% (jumlah semua proses; 100 = satu inti penuh)."""
        pids = self.pids()
        if not pids:
            return {"rss_mb": 0.0, "cpu_pct": 0.0}
        try:
            out = subprocess.run(["ps", "-o", "rss=,pcpu=", "-p", ",".join(map(str, pids))],
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return {"rss_mb": 0.0, "cpu_pct": 0.0}
        rss = cpu = 0.0
        for line in out.splitlines():
            try:
                a, b = line.split()
                rss += float(a)
                cpu += float(b)
            except ValueError:
                continue
        return {"rss_mb": round(rss / 1024, 1), "cpu_pct": round(cpu, 1)}


class Sampler(threading.Thread):
    """Memantau sumber daya server selama satu level beban; mengambil puncaknya."""

    def __init__(self, server: ServerUji | None, interval: float = 1.0):
        super().__init__(daemon=True)
        self.server, self.interval = server, interval
        self.stop = threading.Event()
        self.rss = self.cpu = 0.0

    def run(self) -> None:
        if self.server is None:
            return
        while not self.stop.wait(self.interval):
            s = self.server.sumber_daya()
            self.rss, self.cpu = max(self.rss, s["rss_mb"]), max(self.cpu, s["cpu_pct"])


# --------------------------------------------------------------------------
# Persiapan: temukan id dokumen nyata & saring endpoint yang memang hidup
# --------------------------------------------------------------------------
def kenali_dokumen(base_url: str, profil: str, n: int = 40) -> list[str]:
    k = Klien(base_url)
    try:
        if profil == "api":
            _, galat, body = k.get(f"/api/kb/documents?page_size={min(n, 100)}")
            if galat:
                return []
            data = json.loads(body)
            return [str(i["id"]) for i in data.get("items", []) if i.get("id")][:n]
        _, galat, body = k.get(f"/dokumen?limit={min(n, 500)}")
        if galat:
            return []
        return [str(i["document_id"]) for i in json.loads(body).get("items", [])][:n]
    except (ValueError, KeyError):
        return []
    finally:
        k.tutup()


def periksa_endpoint(base_url: str, eps: list[Endpoint], ctx: dict[str, Any],
                     termasuk_berat: bool) -> tuple[list[Endpoint], dict[str, str]]:
    """Satu panggilan per endpoint. Yang gagal tidak ikut diuji — dan dilaporkan,
    supaya 'p95 bagus' tidak lahir dari menembak endpoint yang sebenarnya mati."""
    hidup, dilewati = [], {}
    rng = random.Random(0)
    k = Klien(base_url)
    for e in eps:
        if e.butuh and not ctx.get(e.butuh):
            dilewati[e.nama] = f"tidak ada data ({e.butuh})"
            continue
        if e.berat and not termasuk_berat:
            dilewati[e.nama] = "model semantik berat — aktifkan dengan --berat"
            continue
        _, galat, _ = k.get(e.path(rng, ctx))
        if galat:
            dilewati[e.nama] = f"gagal saat pemeriksaan awal ({galat})"
        else:
            hidup.append(e)
    k.tutup()
    return hidup, dilewati


# --------------------------------------------------------------------------
# Fase 1 — latensi satu pengguna
# --------------------------------------------------------------------------
def ukur_latensi(base_url: str, eps: list[Endpoint], ctx: dict[str, Any],
                 ulang: int, pemanasan: int = 3) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    rng = random.Random(1)
    k = Klien(base_url)
    for e in eps:
        for _ in range(pemanasan):
            k.get(e.path(rng, ctx))
        h = Hasil()
        for _ in range(ulang):
            ms, galat, _ = k.get(e.path(rng, ctx))
            h.tambah(ms, galat)
        out[e.nama] = {**ringkas(h.ms), "galat": h.galat, "contoh_galat": h.contoh_galat}
    k.tutup()
    return out


# --------------------------------------------------------------------------
# Fase 2 — beban serentak
# --------------------------------------------------------------------------
def jalankan_level(base_url: str, eps: list[Endpoint], ctx: dict[str, Any], pengguna: int,
                   durasi: float, pemanasan: float, server: ServerUji | None,
                   seed: int = 7) -> dict[str, Any]:
    """``pengguna`` utas, masing-masing mengirim permintaan berurutan selama ``durasi`` detik."""
    mulai_ukur = time.perf_counter() + pemanasan
    selesai = mulai_ukur + durasi
    # Hasil tiap utas dibuat di muka dan diisi bertahap: permintaan yang macet
    # (server tidak menjawab) tidak pernah selesai, dan tanpa ini ia lenyap dari
    # hitungan sehingga server yang beku tampak "tanpa galat".
    per_utas: list[tuple[Hasil, dict[str, Hasil]]] = [(Hasil(), {}) for _ in range(pengguna)]

    def kerja(idx: int) -> None:
        rng = random.Random(seed * 1000 + idx)
        k = Klien(base_url)
        total, per_ep = per_utas[idx]
        while True:
            now = time.perf_counter()
            if now >= selesai:
                break
            e = _pilih(rng, eps)
            ms, galat, _ = k.get(e.path(rng, ctx))
            if now >= mulai_ukur:           # pemanasan tidak dihitung
                total.tambah(ms, galat)
                per_ep.setdefault(e.nama, Hasil()).tambah(ms, galat)
        k.tutup()

    sampler = Sampler(server)
    sampler.start()
    cpu0, wall0 = time.process_time(), time.perf_counter()
    utas = [threading.Thread(target=kerja, args=(i,), daemon=True) for i in range(pengguna)]
    for t in utas:
        t.start()
    batas_tunggu = time.perf_counter() + pemanasan + durasi + TIMEOUT_S + 5
    for t in utas:
        t.join(timeout=max(0.0, batas_tunggu - time.perf_counter()))
    macet = sum(1 for t in utas if t.is_alive())
    cpu_klien = (time.process_time() - cpu0) / max(time.perf_counter() - wall0, 1e-9)
    sampler.stop.set()

    total, per_ep = Hasil(), {}
    for t, pe in per_utas:
        total.gabung(t)
        for nama, h in pe.items():
            per_ep.setdefault(nama, Hasil()).gabung(h)
    if macet:
        total.galat += macet
        total.contoh_galat.append(f"{macet} koneksi macet (tak ada jawaban)")
    ringkas_total = ringkas(total.ms)
    return {
        "pengguna": pengguna,
        "macet": macet,
        "permintaan": total.total,
        "rps": round(total.total / durasi, 1),
        "rps_sukses": round(len(total.ms) / durasi, 1),
        "galat": total.galat,
        "rasio_galat": round(total.rasio_galat, 4),
        "contoh_galat": total.contoh_galat,
        "latensi_ms": ringkas_total,
        "per_endpoint": {n: {**ringkas(h.ms), "galat": h.galat} for n, h in sorted(per_ep.items())},
        "server": {"rss_mb": sampler.rss, "cpu_pct": sampler.cpu} if server else None,
        # >0,8 berarti pembangkit beban (GIL Python) hampir jenuh: angka = batas bawah.
        "cpu_klien": round(cpu_klien, 2),
    }


def sehat(level: dict[str, Any], slo_ms: float, galat_maks: float) -> bool:
    return (level["rasio_galat"] <= galat_maks and level["latensi_ms"]["p95"] <= slo_ms
            and level["permintaan"] > 0)


def kapasitas(levels: list[dict[str, Any]], slo_ms: float, galat_maks: float,
              think_time: float) -> dict[str, Any]:
    """Level terbesar yang masih sehat *dan* semua level di bawahnya sehat.

    Berhenti di pelanggaran pertama: level yang kebetulan lolos setelah gagal
    (derau) tidak boleh menaikkan klaim kapasitas."""
    terbaik = None
    for lv in levels:
        if sehat(lv, slo_ms, galat_maks):
            terbaik = lv
        else:
            break
    puncak = max(levels, key=lambda lv: lv["rps_sukses"], default=None)
    hasil: dict[str, Any] = {
        "slo_p95_ms": slo_ms, "galat_maks": galat_maks, "think_time_s": think_time,
        "pengguna_serentak_sehat": terbaik["pengguna"] if terbaik else 0,
        "rps_pada_batas_sehat": terbaik["rps_sukses"] if terbaik else 0.0,
        "rps_puncak": puncak["rps_sukses"] if puncak else 0.0,
        "pengguna_pada_rps_puncak": puncak["pengguna"] if puncak else 0,
    }
    # Little's law untuk sistem terbuka: pengguna ≈ throughput × (jeda berpikir + waktu layan).
    if terbaik:
        layan = terbaik["latensi_ms"]["rata"] / 1000
        hasil["perkiraan_pengguna_nyata"] = round(terbaik["rps_sukses"] * (think_time + layan))
    else:
        hasil["perkiraan_pengguna_nyata"] = 0
    pelanggar = next((lv for lv in levels if not sehat(lv, slo_ms, galat_maks)), None)
    if pelanggar:
        alasan = []
        if pelanggar["rasio_galat"] > galat_maks:
            alasan.append(f"galat {_id(pelanggar['rasio_galat'] * 100)}% > {galat_maks:.0%}")
        if pelanggar["latensi_ms"]["p95"] > slo_ms:
            alasan.append(f"p95 {pelanggar['latensi_ms']['p95']:.0f} ms > {slo_ms:.0f} ms")
        hasil["pelanggaran_pertama"] = {"pengguna": pelanggar["pengguna"], "alasan": "; ".join(alasan)}
    else:
        hasil["pelanggaran_pertama"] = None      # level tertinggi pun masih sehat → batas belum ditemukan
    return hasil


# --------------------------------------------------------------------------
# Orkestrasi
# --------------------------------------------------------------------------
def siapkan_batas_fd(pengguna_maks: int) -> int:
    """Naikkan batas file descriptor agar ``Too many open files`` tidak menyamar sebagai galat server.

    macOS membuka dengan 256; 500 koneksi akan gagal di sisi *klien* dan, bila tidak
    dicegah, dilaporkan sebagai server runtuh. Mengembalikan jumlah pengguna yang
    benar-benar aman diuji (≤ ``pengguna_maks``)."""
    try:
        import resource
        lunak, keras = resource.getrlimit(resource.RLIMIT_NOFILE)
        butuh = pengguna_maks * 2 + 200          # klien + server (proses anak mewarisi)
        target = butuh if keras == resource.RLIM_INFINITY else min(butuh, keras)
        if lunak == resource.RLIM_INFINITY or lunak >= target:
            return pengguna_maks
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, keras))
        return min(pengguna_maks, max(1, (target - 200) // 2))
    except (ImportError, ValueError, OSError):
        return min(pengguna_maks, 100)


def host_info() -> dict[str, Any]:
    return {"cpu_inti": os.cpu_count(), "platform": sys.platform,
            "python": sys.version.split()[0]}


def jalankan(*, profil: str = "api", url: str | None = None, config: Path | None = None,
             cwd: Path | None = None, workers: int = 1, levels: tuple[int, ...] = LEVEL_DEFAULT,
             durasi: float = 10.0, pemanasan: float = 2.0, ulang_latensi: int = 30,
             slo_ms: float = SLO_MS_DEFAULT, galat_maks: float = GALAT_MAKS_DEFAULT,
             think_time: float = THINK_TIME_DEFAULT, termasuk_berat: bool = False,
             cari_batas: bool = True, maks_pengguna: int = 512,
             hanya: list[str] | None = None,
             progress: Callable[[str], None] = lambda m: None) -> dict[str, Any]:
    """Jalankan seluruh uji. ``url`` kosong → server diluncurkan sendiri dari ``config``."""
    eps_all = PROFIL[profil]
    maks_aman = siapkan_batas_fd(max(maks_pengguna, max(levels)))
    if maks_aman < max(levels):
        progress(f"Batas file descriptor membatasi uji ke {maks_aman} pengguna.")
        levels = tuple(n for n in levels if n <= maks_aman)
    maks_pengguna = min(maks_pengguna, maks_aman)
    if hanya:
        kenal = {e.nama for e in eps_all}
        salah = [n for n in hanya if n not in kenal]
        if salah:
            raise ValueError(f"endpoint tidak dikenal: {', '.join(salah)}. Pilihan: {', '.join(sorted(kenal))}")
        eps_all = [e for e in eps_all if e.nama in hanya]
        termasuk_berat = True       # diminta eksplisit berarti disengaja
    server: ServerUji | None = None
    cold = None
    if url is None:
        if config is None:
            raise ValueError("config wajib bila url tidak diberikan")
        server = ServerUji(profil, config, workers, cwd or Path.cwd())
        server.__enter__()
        progress(f"Meluncurkan server uji ({workers} worker) di {server.base_url} …")
    try:
        base = server.base_url if server else url
        assert base
        if server:
            cold = server.tunggu_siap()
            progress(f"Server siap setelah {cold:.1f} s (cold start).")
        ctx: dict[str, Any] = {"doc_ids": kenali_dokumen(base, profil)}
        eps, dilewati = periksa_endpoint(base, eps_all, ctx, termasuk_berat)
        if not eps:
            raise RuntimeError(f"tidak ada endpoint yang hidup: {dilewati}")
        progress(f"{len(eps)} endpoint diuji, {len(dilewati)} dilewati, {len(ctx['doc_ids'])} dokumen contoh.")

        progress("Fase 1/2 — latensi satu pengguna …")
        lat = ukur_latensi(base, eps, ctx, ulang_latensi)

        progress("Fase 2/2 — beban serentak …")
        levels_out: list[dict[str, Any]] = []
        antrean = list(levels)
        while antrean:
            n = antrean.pop(0)
            lv = jalankan_level(base, eps, ctx, n, durasi, pemanasan, server)
            levels_out.append(lv)
            progress(f"  {n:>4} pengguna · {lv['rps']:>7.1f} req/s · p95 {lv['latensi_ms']['p95']:>8.1f} ms · "
                     f"galat {lv['rasio_galat']:.1%}")
            if lv["rasio_galat"] > 0.2:
                progress("  server runtuh (galat > 20%) — level lebih tinggi tidak dijalankan.")
                break
            # Level yang diminta habis tetapi batas belum ketemu: gandakan sampai ketemu.
            # Berhenti bila pembangkit beban sendiri jenuh — angka berikutnya hanya mengukur klien.
            if (not antrean and cari_batas and sehat(lv, slo_ms, galat_maks)
                    and n * 2 <= maks_pengguna):
                if lv["cpu_klien"] > 0.8:
                    progress("  pembangkit beban jenuh — pencarian batas dihentikan (angka = batas bawah).")
                else:
                    antrean.append(n * 2)
        kap = kapasitas(levels_out, slo_ms, galat_maks, think_time)
        return {
            "dibuat": time.strftime("%Y-%m-%d %H:%M:%S"),
            "profil": profil, "target": base, "server_diluncurkan": server is not None,
            "workers": workers if server else None, "cold_start_s": round(cold, 2) if cold else None,
            "host": host_info(), "mix_endpoint": {e.nama: e.bobot for e in eps},
            "dilewati": dilewati, "dokumen_contoh": len(ctx["doc_ids"]),
            "subset_endpoint": hanya or None,
            "parameter": {"durasi_per_level_s": durasi, "pemanasan_s": pemanasan,
                          "ulang_latensi": ulang_latensi, "levels": list(levels)},
            "latensi_satu_pengguna": lat, "beban": levels_out, "kapasitas": kap,
        }
    finally:
        if server:
            server.__exit__(None, None, None)


# --------------------------------------------------------------------------
# Laporan
# --------------------------------------------------------------------------
def _id(x: float, d: int = 1) -> str:
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render(rep: dict[str, Any]) -> str:
    kap, p = rep["kapasitas"], rep["parameter"]
    L: list[str] = []
    L.append("# Performa Server — Latensi & Kapasitas\n")
    L.append(f"*Dihasilkan oleh `hero loadtest` pada {rep['dibuat']}. Semua angka diukur ulang setiap "
             f"perintah dijalankan.*\n")
    L.append(f"- **Target:** profil `{rep['profil']}` · "
             + (f"server diluncurkan sendiri dengan **{rep['workers']} worker**" if rep["server_diluncurkan"]
                else f"server yang sudah berjalan di `{rep['target']}`"))
    L.append(f"- **Mesin uji:** {rep['host']['cpu_inti']} inti CPU · {rep['host']['platform']} · "
             f"Python {rep['host']['python']} — pembangkit beban dan server berbagi mesin yang sama.")
    if rep.get("cold_start_s"):
        L.append(f"- **Cold start:** {_id(rep['cold_start_s'])} detik dari proses dimulai sampai `/health` menjawab.")
    if rep.get("subset_endpoint"):
        L.append(f"- ⚠ **Subset endpoint:** hanya {', '.join('`' + n + '`' for n in rep['subset_endpoint'])} "
                 f"— bukan campuran sesi pengguna; jangan dibaca sebagai kapasitas aplikasi utuh.")
    L.append(f"- **Isi katalog:** {rep['dokumen_contoh']} dokumen dipakai sebagai contoh akses detail.")
    L.append(f"- **Batas mutu:** p95 ≤ {_id(kap['slo_p95_ms'], 0)} ms (NFR-02) dan galat ≤ "
             f"{kap['galat_maks']:.0%}.\n")

    L.append("## Jawaban singkat\n")
    if kap["pengguna_serentak_sehat"]:
        L.append(f"- **Pengguna serentak maksimum yang sehat:** **{kap['pengguna_serentak_sehat']}** koneksi "
                 f"yang menembak tanpa jeda ({_id(kap['rps_pada_batas_sehat'])} permintaan/detik).")
        L.append(f"- **Perkiraan pengguna nyata:** ± **{kap['perkiraan_pengguna_nyata']}** orang bekerja "
                 f"bersamaan, bila tiap orang beraksi sekali per {_id(kap['think_time_s'], 0)} detik "
                 f"*(turunan: throughput × (jeda + waktu layan); bukan hasil ukur langsung)*.")
    else:
        L.append("- **Tidak ada level yang lolos batas mutu**, bahkan satu pengguna — lihat tabel latensi.")
    L.append(f"- **Throughput puncak:** {_id(kap['rps_puncak'])} permintaan/detik pada "
             f"{kap['pengguna_pada_rps_puncak']} pengguna.")
    pl = kap["pelanggaran_pertama"]
    if pl:
        L.append(f"- **Batas pertama terlampaui di {pl['pengguna']} pengguna:** {pl['alasan']}.")
    else:
        L.append("- **Batas belum ditemukan** — level tertinggi yang diuji pun masih sehat. "
                 "Naikkan `--level` untuk mencarinya.")
    if not pl:
        L.append("- Karena batas belum ditemukan, kedua angka pengguna di atas adalah **batas bawah** "
                 "(≥), bukan kapasitas sebenarnya.")
    padat = [b for b in rep["beban"] if b["cpu_klien"] > 0.8]
    if padat:
        L.append(f"- ⚠ **Pembangkit beban hampir jenuh** pada {', '.join(str(b['pengguna']) for b in padat)} "
                 f"pengguna (CPU klien > 80% dari satu inti): angka di level itu adalah batas **bawah**; "
                 f"server mungkin sanggup lebih.")
    L.append("")

    L.append("## 1. Latensi satu pengguna (tanpa persaingan)\n")
    L.append("| Endpoint | n | p50 ms | p95 ms | p99 ms | maks ms | galat |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for nama, r in sorted(rep["latensi_satu_pengguna"].items(), key=lambda kv: -kv[1]["p95"]):
        flag = " ⚠" if r["p95"] > kap["slo_p95_ms"] else ""
        L.append(f"| {nama}{flag} | {r['n']} | {_id(r['p50'])} | {_id(r['p95'])} | {_id(r['p99'])} | "
                 f"{_id(r['maks'])} | {r['galat']} |")
    L.append("")

    L.append("## 2. Beban serentak\n")
    L.append(f"Tiap level berjalan {_id(p['durasi_per_level_s'], 0)} detik setelah pemanasan "
             f"{_id(p['pemanasan_s'], 0)} detik; pengguna virtual mengirim permintaan berurutan tanpa jeda "
             f"dengan campuran endpoint di bagian 4.\n")
    L.append("| Pengguna | req/s | p50 ms | p95 ms | p99 ms | maks ms | galat | RAM server MB | CPU server % | CPU klien | Sehat |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for b in rep["beban"]:
        lt = b["latensi_ms"]
        srv = b["server"] or {}
        ok = "✅" if sehat(b, kap["slo_p95_ms"], kap["galat_maks"]) else "❌"
        L.append(f"| {b['pengguna']} | {_id(b['rps'])} | {_id(lt['p50'])} | {_id(lt['p95'])} | {_id(lt['p99'])} | "
                 f"{_id(lt['maks'])} | {_id(b['rasio_galat'] * 100)}% | {_id(srv['rss_mb']) if srv else '—'} | "
                 f"{_id(srv['cpu_pct'], 0) if srv else '—'} | {b['cpu_klien']:.0%} | {ok} |")
    L.append("")
    galat = [(b["pengguna"], b["contoh_galat"]) for b in rep["beban"] if b["contoh_galat"]]
    if galat:
        L.append("Contoh galat yang teramati: " + "; ".join(f"{n} pengguna → {', '.join(g)}" for n, g in galat) + "\n")

    L.append("## 3. Endpoint paling lambat di bawah beban\n")
    ref = next((b for b in reversed(rep["beban"]) if sehat(b, kap["slo_p95_ms"], kap["galat_maks"])),
               rep["beban"][-1])
    L.append(f"Dari level {ref['pengguna']} pengguna (level sehat tertinggi, atau terakhir bila tak ada):\n")
    L.append("| Endpoint | n | p50 ms | p95 ms | galat |")
    L.append("|---|---:|---:|---:|---:|")
    for nama, r in sorted(ref["per_endpoint"].items(), key=lambda kv: -kv[1]["p95"])[:8]:
        L.append(f"| {nama} | {r['n']} | {_id(r['p50'])} | {_id(r['p95'])} | {r['galat']} |")
    L.append("")

    L.append("## 4. Campuran beban & endpoint dilewati\n")
    tot = sum(rep["mix_endpoint"].values())
    L.append("Bobot kemunculan per sesi pengguna: " + ", ".join(
        f"`{n}` {w / tot:.0%}" for n, w in sorted(rep["mix_endpoint"].items(), key=lambda kv: -kv[1])) + ".\n")
    if rep["dilewati"]:
        L.append("Tidak diuji: " + "; ".join(f"`{n}` ({a})" for n, a in rep["dilewati"].items()) + ".\n")

    L.append("## Cara membaca & batasnya\n")
    L.append("- **Closed-loop tanpa jeda** adalah skenario terburuk bagi server; ribuan orang yang sesekali "
             "mengklik jauh lebih ringan daripada ratusan koneksi yang menembak terus.")
    L.append("- **Pembangkit beban Python** dibatasi satu inti (GIL). Peringatan ⚠ di atas muncul bila itu "
             "menjadi penghambat; gunakan mesin terpisah untuk batas atas yang sebenarnya.")
    L.append("- **Pembangkit dan server di satu mesin** saling berebut CPU; hasil di mesin produksi dengan "
             "klien terpisah umumnya lebih baik, bukan lebih buruk.")
    L.append("- Data adalah katalog nyata pada saat uji. Setelah korpus membesar, **jalankan ulang** — "
             "laporan ini sengaja dapat dieksekusi ulang, bukan dikutip.")
    L.append("- Hanya endpoint **baca (GET)** yang diuji. Unggah, pemindaian, dan harmonisasi (pekerjaan "
             "latar yang berat) tidak diukur di sini; waktu proses per dokumen ada di `hero fase2`.")
    L.append("- Ini menguji **API lapisan data** (`hero serve` / `hero bridge layanan`), bukan backend "
             "aplikasi tim — itu milik peran Backend dan memiliki infrastruktur (Postgres, proxy) berbeda.")
    return "\n".join(L) + "\n"
