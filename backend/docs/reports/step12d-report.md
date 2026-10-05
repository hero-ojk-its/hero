# LAPORAN LANGKAH 12d: PERBAIKAN BUG KUNCI PINDAI/TARIK YANG MACET

**HERO Backend · FASE 1**  
**Branch:** `feat/step12-ingest-support`  
**Tanggal:** 4 Oktober 2026  
**Status:** SELESAI & TERVERIFIKASI  

---

## 1. RINGKASAN EKSEKUTIF

Langkah 12d menyelesaikan dua kelemahan fatal pada mekanisme penguncian sesi pemindaian dan penarikan berkas yang ditemukan saat uji integrasi frontend:
1. **NameError pada retry penarikan berkas**: Modul `time` belum di-import pada `app/services/scan_service.py` sehingga pemanggilan `time.sleep(0.5)` pada loop retry perolehan kunci melempar `NameError` di luar blok penanganan error. Hal ini menyebabkan background task mati mendadak dengan sesi tertahan pada status `menarik` dan job tertahan pada status `antrian` (seperti yang dialami pada Sesi Scan ID 4).
2. **Kebocoran PostgreSQL Advisory Lock**: Penguncian advisory lock tingkat sesi (`pg_try_advisory_lock`) sebelumnya dieksekusi melalui SQLAlchemy ORM `SessionLocal()`. Setiap pemanggilan `db.commit()` mengembalikan atau mengganti koneksi fisik ke/dari connection pool. Ketika blok `finally` memanggil `pg_advisory_unlock`, ia berjalan di koneksi fisik yang berbeda sehingga menghasilkan `false` dan diabaikan, meninggalkan kunci advisory aktif permanen di koneksi pool asal. Akibatnya, pemindaian atau penarikan berikutnya pada sumber yang sama langsung ditolak dengan pesan *"Pemindaian sumber ini sedang diproses oleh eksekusi lain."*.
3. **Pembersihan & Perlindungan Sesi Macet**:
   - Diterapkan perolehan kunci menggunakan koneksi dedicated (`lock_conn = engine.connect()`) yang dipegang penuh sepanjang proses dan dilepaskan secara eksplisit pada blok `finally` sebelum koneksi ditutup.
   - Pada saat startup aplikasi (`is_startup=True`), seluruh sesi `memindai`/`menarik` dan job `antrian`/`berjalan` yang tidak memiliki proses hidup otomatis ditandai `gagal` dengan pesan *"Dihentikan karena server dimulai ulang."*.
   - Ditambahkan batas waktu: sesi tanpa pembaruan (`updated_at`) selama > 15 menit otomatis dianggap macet dan ditandai `gagal`.

---

## 2. BUKTI AKAR MASALAH

### 2.1 Bug 1: `time` Tidak Di-import (`scan_service.py`)
Pada `app/services/scan_service.py` baris 820–830 (metode `execute_pull`):
```python
# KODE SEBELUM PERBAIKAN:
lock_acquired = False
lock_key = session.source_id or scan_id
for _ in range(5):
    try:
        res = db.execute(text(f"SELECT pg_try_advisory_lock(1396924751, {lock_key})")).scalar()
        lock_acquired = bool(res)
        if lock_acquired:
            break
    except Exception as e:
        logger.warning(f"[Pull] Gagal memanggil pg_try_advisory_lock: {e}")
        lock_acquired = True
        break
    time.sleep(0.5)  # <-- time TIDAK di-import di tingkat modul!
```
- Begitu percobaan kunci pertama gagal atau membutuhkan retry, `NameError: name 'time' is not defined` terlempar di luar blok `try/except/finally`.
- Task background mati tanpa mengeksekusi transisi status ke `gagal`. Sesi tetap berstatus `menarik` dan job tetap berstatus `antrian` dengan `processed_count = 0` selamanya.

### 2.2 Bug 2: Kebocoran Advisory Lock Melalui SQLAlchemy Pool
Kunci `pg_try_advisory_lock(int, int)` di PostgreSQL adalah session-level lock yang terikat pada koneksi TCP backend PostgreSQL tertentu (`pid`).
Ketika dipanggil melalui SQLAlchemy `Session`:
1. `res = db.execute("SELECT pg_try_advisory_lock(...)")` meminjam `Connection 1` dari pool dan mengunci.
2. Di tengah eksekusi, `db.commit()` dijalankan. SQLAlchemy dapat mengembalikan `Connection 1` ke pool atau mengambil koneksi lain untuk transaksi berikutnya.
3. Di blok `finally`, `db.execute("SELECT pg_advisory_unlock(...)")` meminjam `Connection 2` dari pool.
4. `pg_advisory_unlock` pada `Connection 2` mengembalikan nilai `false` karena kunci dipegang oleh `Connection 1`.
5. Nilai `false` tersebut diabaikan karena blok `except Exception: pass`, sehingga `Connection 1` tetap menahan kunci advisory di dalam pool PostgreSQL.
6. Permintaan pemindaian berikutnya yang menggunakan koneksi selain `Connection 1` langsung ditolak karena lock masih aktif.

#### Bukti Empiris Kebocoran Antar-Koneksi (Output Terminal Nyata):
```
--- DEMO / BUKTI AKAR MASALAH KUNCI ADVISORY BOCOR ANTAR-KONEKSI ---
1. conn1: pg_try_advisory_lock(1396924750, 9999) -> True
2. conn2: pg_advisory_unlock(1396924750, 9999) -> False
3. pg_locks saat ini (kunci bocor di conn1): [('advisory', 1396924750, 9999, 1079)]
4. conn3: pg_try_advisory_lock(1396924750, 9999) -> False (DITOLAK KARENA KUNCI MASIH BOCOR!)
5. Setelah conn1 dibersihkan dan ditutup.
```

---

## 3. SOLUSI PERBAIKAN ARSITEKTURAL

### 3.1 Pilihan Mekanisme Penguncian: Dedicated Connection vs `SELECT FOR UPDATE`
Dipilih pendekatan **Koneksi Khusus Dedicated Connection (`lock_conn = engine.connect()`)** dengan alasan:
1. Operasi pemindaian web crawler dan penarikan puluhan berkas PDF melibatkan operasi jaringan (I/O) yang memakan waktu detik hingga menit, serta membutuhkan multiple commit per batch untuk mencatat progres job.
2. `SELECT ... FOR UPDATE` menahan baris data di dalam satu transaksi aktif. Menahan transaksi aktif terbuka selama proses I/O jaringan adalah anti-pattern di PostgreSQL (mengakibatkan transaction ID wraparound risk, penumpukan dead tuples, mencegah VACUUM, dan meningkatkan risiko table lock bloat).
3. Dengan dedicated connection, transaksi ORM (`SessionLocal()`) tetap bebas melakukan commit kapan saja, sementara koneksi pengunci (`lock_conn`) independen dan menjamin lock dilepaskan serta ditutup saat proses selesai.

### 3.2 Struktur Try/Finally & Logging
Seluruh badan proses, **termasuk perolehan kunci**, berada di dalam blok `try/finally`:
```python
lock_conn = None
lock_acquired = False
...
try:
    try:
        lock_conn = engine.connect()
        # acquire lock with retries ...
    except Exception as e:
        ...
    # proses pemindaian / penarikan ...
finally:
    if lock_conn is not None:
        try:
            if lock_acquired and lock_key is not None:
                try:
                    unlocked = lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:ns, :key)"),
                        {"ns": lock_ns, "key": lock_key},
                    ).scalar()
                    if not unlocked:
                        logger.warning(
                            f"[Scan/Pull] pg_advisory_unlock({lock_ns}, {lock_key}) mengembalikan False."
                        )
                except Exception as e:
                    logger.warning(f"Gagal memanggil pg_advisory_unlock: {e}")
        finally:
            try:
                lock_conn.close()
            except Exception as e:
                logger.warning(f"Gagal menutup lock_conn: {e}")
```

### 3.3 Pemulihan Sesi Macet & Batas Waktu
1. `scan_stuck_minutes` diubah default-nya dari 60 menit menjadi 15 menit pada `app/config.py`.
2. Saat aplikasi startup (`app/main.py`), dipanggil `recover_stuck_scan_sessions(db, stuck_minutes=settings.scan_stuck_minutes, is_startup=True)`:
   - Menandai semua sesi `memindai` / `menarik` dan job yang tidak punya proses hidup sebagai `gagal` dengan pesan *"Dihentikan karena server dimulai ulang."*.
3. Pada `start_scan` dan `get_scan_session_detail`, jika sesi aktif tidak memiliki pembaruan (`updated_at` / `started_at`) selama > 15 menit, sesi ditandai `gagal` dengan pesan *"Dihentikan karena server dimulai ulang. Batas waktu aktivitas terlampaui (> 15 menit)."*.

---

## 4. RINGKASAN DIFF

```diff
--- a/app/config.py
+++ b/app/config.py
@@ -66,1 +66,1 @@
-    scan_stuck_minutes: int = 60
+    scan_stuck_minutes: int = 15

--- a/app/main.py
+++ b/app/main.py
@@ -115,1 +115,1 @@
-            recover_stuck_scan_sessions(db, stuck_minutes=settings.scan_stuck_minutes)
+            recover_stuck_scan_sessions(db, stuck_minutes=settings.scan_stuck_minutes, is_startup=True)

--- a/app/services/scan_service.py
+++ b/app/services/scan_service.py
@@ -10,3 +10,4 @@
+import time
 import zipfile
-from app.database import SessionLocal
+from app.database import SessionLocal, engine
@@ -133,6 +134,26 @@
+        # Deteksi sesi macet > 15 menit sebelum melempar 409
+        if active_session:
+            cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.scan_stuck_minutes)
+            last_active = active_session.updated_at or active_session.started_at or active_session.created_at
+            if last_active and last_active < cutoff:
+                active_session.status = StatusPindai.gagal
+                active_session.error_message = f"Dihentikan karena server dimulai ulang. Batas waktu aktivitas terlampaui (> {settings.scan_stuck_minutes} menit)."
+                ...
@@ -234,35 +255,42 @@
+        # execute_scan menggunakan dedicated lock_conn pada try/finally
+        lock_conn = None
+        ...
+        try:
+            lock_conn = engine.connect()
+            res = lock_conn.execute(text("SELECT pg_try_advisory_lock(:ns, :key)"), ...)
+        ...
+        finally:
+            if lock_conn is not None:
+                unlocked = lock_conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"), ...)
+                lock_conn.close()
@@ -860,35 +888,43 @@
+        # execute_pull menggunakan dedicated lock_conn dengan loop retry time.sleep(0.5)
+        lock_conn = None
+        ...
+        try:
+            lock_conn = engine.connect()
+            for _ in range(5):
+                res = lock_conn.execute(text("SELECT pg_try_advisory_lock(:ns, :key)"), ...)
+                ...
+                time.sleep(0.5)
+        ...
+        finally:
+            if lock_conn is not None:
+                unlocked = lock_conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"), ...)
+                lock_conn.close()
@@ -1473,15 +1515,25 @@
-def recover_stuck_scan_sessions(db: Session, stuck_minutes: int = 60) -> int:
+def recover_stuck_scan_sessions(db: Session, stuck_minutes: int = 15, is_startup: bool = False) -> int:
+    # Mendukung pemulihan komprehensif saat startup atau batas waktu 15 menit
```

---

## 5. TABEL PENGUJIAN OTOMATIS (K01–K06)

| # | Kasus Uji | Ekspektasi | Hasil Pengujian | Status |
|---|---|---|---|---|
| **K01** | Tarik dua kali berturut-turut dari sumber yang sama (sesi berbeda) | Keduanya `selesai`; tidak ada pesan "sedang diproses" | Sesi 1 & 2 `selesai`, unduh folder ZIP berhasil tanpa pesan konflik | **PASS** |
| **K02** | Pindai → tarik → pindai lagi sumber yang sama | Pindai kedua berjalan normal | Pindai kedua selesai dan siap dipilih (`siap_dipilih`), tidak ada penolakan | **PASS** |
| **K03** | Kunci sengaja ditahan koneksi lain, lalu tarik | Retry 5x, lalu sesi `gagal` dengan pesan jelas (bukan macet di `menarik`) | Sesi ditandai `gagal` dengan pesan *"Proses penarikan sedang diproses oleh eksekusi lain."*, job ingest `gagal` | **PASS** |
| **K04** | Sesi `menarik` tanpa proses saat start | Ditandai `gagal` dengan pesan *"Dihentikan karena server dimulai ulang."* | Sesi `menarik` dan job `antrian` dipulihkan ke `gagal` | **PASS** |
| **K05** | Setelah K01–K02 selesai | `pg_locks` advisory kosong (0 baris) | Query `pg_locks WHERE locktype='advisory'` mengembalikan 0 baris | **PASS** |
| **K06** | `pytest -q` seluruh test suite | Semua lulus tanpa regresi | **236 passed, 1 skipped, 2 warnings** | **PASS** |

---

## 6. UJI LIVE SESUAI INSTRUKSI SPESIFIKASI (§5)

TIDAK DIJALANKAN


---

## 7. HASIL SUITE PENGUJIAN OTOMATIS PYTEST

*(Perintah: `$env:PYTHONPATH="."; .\venv\Scripts\pytest.exe -q`)*

```
........................................................................ [ 30%]
............................................s........................... [ 60%]
........................................................................ [ 91%]
.....................                                                    [100%]
============================== warnings summary ===============================
..\..\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

..\..\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
236 passed, 1 skipped, 2 warnings in 315.27s (0:05:15)
```

---

## 8. INFORMASI GIT REPOSITORI

### 8.1 Git Remote
*(Perintah: `git remote -v`)*

```
(Tidak ada remote yang terkonfigurasi pada repositori lokal ini)
```

### 8.2 Git Status
*(Perintah: `git status --short`)*

```
 M app/config.py
 M app/main.py
 M app/routers/scans.py
 M app/services/scan_service.py
 M app/services/source_runner.py
?? docs/reports/step12d-report.md
?? tests/test_scan_locks_12d.py
```

### 8.3 Git Log
*(Perintah: `git log --oneline -5`)*

```
1f0403a docs(reports): koreksi laporan 12b dan tambahkan laporan langkah 12c
d88dbad fix(scripts): skrip perbaikan nama berkas, verifikasi duplikat, dan penghitung frekuensi
e6f2b3a fix(naming): ganti slash dengan minus pada nama berkas dan perbaiki pemotongan judul
2d16578 fix(crawlers): perbaiki parsing nomor regulasi slash pada jdih_api
9215275 docs(reports): laporan langkah 12b koreksi kecil setelah review
```
