# Deploy otomatis ke VPS

Setelah CI hijau di `main`, GitHub Actions menerapkan perubahan ke VPS **tanpa Anda mengubah apa pun
secara manual**. Frontend tetap lewat Vercel dan GitHub Pages (tidak diubah).

```
merge ke main
   │
   ├─ backend/**  → Backend CI hijau  → [runner] bangun image → GHCR ─┐
   │                                                                   ├─▶ deploy-vps.yml ─ SSH ─▶ VPS
   └─ pipeline/** → Pipeline CI hijau → [runner] arsip kode ───────────┘        (kunci terbatas)
```

| Komponen | Cara sampai ke VPS | Yang dilakukan di VPS |
|---|---|---|
| **Backend** (Docker) | image dibangun di runner GitHub, ditarik VPS dari `ghcr.io` | cadangan DB → **gladi migrasi pada salinan data** → ganti image → verifikasi `/health` → pulihkan image lama bila gagal |
| **Lapisan data** (`hero`) | arsip `pipeline/hero` dikirim lewat SSH | cadangkan kode lama → timpa → restart layanan → uji asap → pulihkan bila gagal |
| Frontend | Vercel / GitHub Pages | tidak ada hubungannya dengan VPS |

Berkas: [`ci-entry.sh`](ci-entry.sh) (pintu masuk kunci), [`deploy-backend.sh`](deploy-backend.sh),
[`deploy-pipeline.sh`](deploy-pipeline.sh), uji di [`tests/`](tests/test_deploy.sh), workflow
[`deploy-vps.yml`](../../.github/workflows/deploy-vps.yml) dan
[`deploy-vps-check.yml`](../../.github/workflows/deploy-vps-check.yml).

> **Mengapa image dibangun di GitHub, bukan di VPS?** VPS hanya 1,9 GB RAM dan sudah memakai swap ±1,6 GB.
> Membangun image di sana (yang dulu dilakukan manual) menekan Nextcloud dan database. Runner GitHub gratis dan
> 7 GB RAM; VPS cukup menarik hasil jadinya.

---

## Persiapan satu kali

Urutan penting. Langkah 1–4 aman: tidak mengubah produksi.

### 1. Pasang skrip di VPS (milik root, tidak bisa diubah kunci deploy)

Dari Mac, di akar repo:

```bash
scp deploy/vps/ci-entry.sh deploy/vps/deploy-backend.sh deploy/vps/deploy-pipeline.sh myvps:/tmp/
ssh myvps 'sudo install -d -m 755 -o root -g root /opt/hero/ci &&
           sudo install -m 755 -o root -g root /tmp/ci-entry.sh /tmp/deploy-backend.sh /tmp/deploy-pipeline.sh /opt/hero/ci/ &&
           rm -f /tmp/ci-entry.sh /tmp/deploy-backend.sh /tmp/deploy-pipeline.sh && ls -la /opt/hero/ci'
```

Skrip ini **sengaja tidak ikut ter-deploy otomatis**: kunci deploy tidak boleh mengubah skripnya sendiri.
Bila skrip di repo berubah, ulangi langkah ini (jarang).

### 2. Buat kunci SSH khusus deploy

```bash
ssh-keygen -t ed25519 -N "" -C hero-deploy-gha -f ~/.ssh/hero_deploy_gha
```

Daftarkan **kunci publiknya** di VPS dengan batasan — kunci ini hanya bisa menjalankan `ci-entry.sh`, tanpa shell:

```bash
PUB="$(cat ~/.ssh/hero_deploy_gha.pub)"
ssh myvps "echo 'restrict,command=\"/opt/hero/ci/ci-entry.sh\" $PUB' >> ~/.ssh/authorized_keys"
```

Uji bahwa batasannya bekerja (harus **ditolak**, bukan membuka shell):

```bash
ssh -i ~/.ssh/hero_deploy_gha -o IdentitiesOnly=yes ubuntu@43.128.102.71 'whoami'
# ditolak: perintah tidak dikenal atau argumen tidak valid
```

### 3. Siapkan GitHub Environment `vps-production`

Repo → **Settings → Environments → New environment → `vps-production`**, lalu:

- **Required reviewers**: tambahkan diri Anda (sangat disarankan, lihat "Keamanan" di bawah).
- **Environment secrets**:

| Secret | Isi |
|---|---|
| `VPS_HOST` | `43.128.102.71` |
| `VPS_USER` | `ubuntu` |
| `VPS_SSH_KEY` | isi berkas **privat** `~/.ssh/hero_deploy_gha` |
| `VPS_KNOWN_HOSTS` | keluaran `ssh-keyscan -t ed25519 43.128.102.71` (menyematkan sidik jari server; mencegah penyadapan) |

Atau lewat `gh`:

```bash
gh secret set VPS_HOST       --env vps-production --body "43.128.102.71"
gh secret set VPS_USER       --env vps-production --body "ubuntu"
gh secret set VPS_SSH_KEY    --env vps-production < ~/.ssh/hero_deploy_gha
ssh-keyscan -t ed25519 43.128.102.71 2>/dev/null | gh secret set VPS_KNOWN_HOSTS --env vps-production
```

### 4. Isi `ML_SERVICE_URL` di backend VPS (sekali)

Tanpa ini gateway `/api/v1/ml/*` menjawab 503 `layanan_analisa_belum_dikonfigurasi`:

```bash
ssh myvps 'sudo sh -c "echo ML_SERVICE_URL=http://172.17.0.1:8100 >> /opt/hero/backend/.env.prod"'
```

Sudah diverifikasi (26 Okt) dari dalam kontainer `hero_backend`: `http://172.17.0.1:8100/health` dapat dijangkau dan menjawab `siap`.

### 5. Gladi (aman) lalu aktifkan

**Actions → Deploy VPS → Run workflow** → `komponen: backend`, centang **gladi_saja**. Ini menarik image,
membuat cadangan database, dan melatih migrasi pada salinan data, **tanpa mengganti backend produksi**.
Periksa lognya. Bila bersih, **nyalakan deploy otomatis**:

```bash
gh variable set DEPLOY_VPS_ENABLED --body true
```

Mulai saat itu, setiap merge ke `main` yang lolos CI men-deploy sendiri. **Mematikan seketika**
(tombol darurat): `gh variable set DEPLOY_VPS_ENABLED --body false`. Selama variabel ini belum `true`,
merge PR ke `main` tidak men-deploy apa pun (menjalankan manual lewat *Run workflow* tetap bisa).

---

## Memakai

- **Otomatis:** merge PR ke `main` → CI → (persetujuan reviewer bila diaktifkan) → deploy.
- **Manual:** Actions → *Deploy VPS* → *Run workflow* (pilih komponen, opsional commit tertentu).
- **Melihat hasil:** ringkasan di halaman run; di VPS `sudo journalctl -t hero-deploy -n 50`.

## Bila gagal

| Gagal di | Artinya | Produksi |
|---|---|---|
| gladi migrasi | migrasi tidak jalan di salinan data produksi | **utuh**, tidak disentuh |
| `docker pull` / disk | image tak bisa ditarik / ruang kurang | utuh |
| verifikasi `/health` | backend baru tidak sehat dalam 150 s | **image lama dipasang kembali** otomatis |
| uji asap lapisan data | `hero` tak bisa diimpor / layanan analisa tak menjawab | **kode lama dipulihkan** otomatis |

Pemulihan manual dari cadangan: database di `/opt/hero/data/cadangan-deploy/hero_db-*.sql.gz` (14 terakhir),
kode di `hero-kode-*.tar.gz` (5 terakhir).

---

## Keamanan dan batas — baca ini

1. **Pemulihan image tidak memulihkan skema.** Bila migrasi produksi sudah berjalan lalu `/health` gagal, image
   lama dipasang kembali tetapi skema tetap yang baru. Migrasi proyek ini aditif sehingga kode lama biasanya tetap
   jalan, dan **gladi** di langkah 4 skrip menangkap sebagian besar masalah *sebelum* produksi disentuh. Namun ini
   bukan jaminan: gladi memakai data yang sama, bukan beban nyata.
2. **`main` tidak diproteksi** (cek 26 Okt: tidak ada aturan proteksi). Siapa pun dengan akses tulis bisa push langsung,
   dan push itu akan men-deploy ke produksi. Aktifkan *Branch protection* (wajib PR dan status check) **dan**
   *Required reviewers* di environment `vps-production` — keduanya, karena yang pertama mencegah push langsung dan
   yang kedua memberi satu klik persetujuan sebelum produksi diubah.
3. **SSH VPS masih menerima login kata sandi dan root** (`PasswordAuthentication yes`, `PermitRootLogin yes` pada
   `sshd -T`). Itu terbuka bagi seluruh internet. Setelah kunci Anda terbukti jalan, matikan keduanya di
   `/etc/ssh/sshd_config` dan `sudo systemctl reload ssh` (uji dari sesi kedua dulu agar tidak terkunci). Tidak
   diubah otomatis karena bisa mengunci Anda.
4. **Kunci deploy yang bocor** hanya dapat meminta dua hal: menarik image `hero-backend` milik repo ini, atau
   mengirim kode lapisan data. Ia tidak bisa membuka shell. Namun mengirim kode lapisan data berarti **kode yang
   berjalan sebagai layanan di VPS** — jaga rahasia `VPS_SSH_KEY` setara kunci produksi.
5. **Repo ini publik.** Workflow deploy hanya berjalan dari `push` ke `main` / `workflow_dispatch`, tidak dari PR
   atau fork, sehingga rahasia tidak terbaca pihak luar. Image di GHCR tidak berisi rahasia (rahasia ada di
   `.env.prod` di VPS), tetapi berisi kode backend yang memang sudah publik.
6. **Yang belum diotomatiskan:** unit systemd, `Caddyfile`, dan `.env.prod`. Perubahan di sana tetap manual.
7. **Diuji vs belum diuji.** Logika skrip (urutan, pemulihan, penolakan perintah/arsip jahat) diuji dengan
   `docker`/`curl`/`systemctl` palsu — 69 tes, plus *mutation test*. Yang **belum** diuji adalah jalannya di VPS
   sungguhan; itulah gunanya langkah **gladi** di atas.
