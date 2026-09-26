"""
Router: /api/v1/ingest
Endpoint untuk menerima upload dokumen dari scraper / manual upload.
Menyimpan metadata + path PDF, siap menerima data blok teks terstruktur,
serta mencatat tracking proses ke tabel JobIngest.
"""
from datetime import datetime, date
import hashlib
import os
from typing import Optional, List
import aiofiles

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.database import get_db
from app.config import settings
from app.models.document import Document
from app.models.job_ingest import JobIngest
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    JenisJobIngest,
    StatusJobIngest,
    StatusKeberlakuan,
    StatusPemrosesan,
)

router = APIRouter()


@router.post("/upload-pdf", summary="Upload PDF regulasi baru (mendukung unggah jamak / multiple files)")
async def upload_pdf(
    files: List[UploadFile] = File(
        ...,
        description="Daftar file PDF regulasi yang diunggah (bisa jamak / multiple files)"
    ),
    access_classification: KlasifikasiAkses = Form(
        ...,
        description="Klasifikasi akses (publik / non_publik) - WAJIB untuk kepatuhan NDA"
    ),
    title: Optional[str] = Form(
        None,
        description="Judul dokumen (opsional jika unggah jamak, default menggunakan nama file)"
    ),
    regulation_number: Optional[str] = Form(
        None,
        description="Nomor regulasi unik, misal: PP-24-2005 (opsional)"
    ),
    regulation_type: Optional[str] = Form(
        None,
        description="Jenis regulasi, misal: UU, PP, Permen"
    ),
    document_role: PeranDokumen = Form(
        PeranDokumen.corpus_eksisting,
        description="Peran dokumen: corpus_eksisting | draft_kajian"
    ),
    job_type: JenisJobIngest = Form(
        JenisJobIngest.unggah_manual,
        description="Jenis job ingest: scraping | unggah_manual | sinkron_folder"
    ),
    category_id: Optional[str] = Form(
        None,
        description="ID kategori KB terkait"
    ),
    release_date: Optional[str] = Form(
        None,
        description="Tanggal terbit, format: YYYY-MM-DD"
    ),
    source_url: Optional[str] = Form(
        None,
        description="URL asal dokumen"
    ),
    db: Session = Depends(get_db),
):
    """
    [US-15] Endpoint untuk upload PDF regulasi / draft kajian.
    Mendukung unggah jamak (multiple files):
    - Menerima `List[UploadFile]`
    - Melakukan validasi format, deduplikasi hash SHA-256, dan penyimpanan per file
    - Melacak proses batch secara keseluruhan ke tabel `JobIngest`
    - Mengembalikan rangkuman hasil (berhasil, duplikat, gagal beserta detailnya)
    """
    if not files:
        raise HTTPException(status_code=400, detail="Tidak ada file yang diunggah.")

    # 1. Inisialisasi JobIngest record untuk melacak batch unggah jamak
    filenames = [f.filename for f in files if f and f.filename]
    source_ref = ", ".join(filenames)[:250] if filenames else "multiple_files.pdf"

    job = JobIngest(
        job_type=job_type,
        source_ref=source_ref,
        triggered_by="manual_upload",
        status=StatusJobIngest.berjalan,
        success_count=0,
        duplicate_count=0,
        failed_count=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Direktori penyimpanan PDF
    pdf_dir = os.path.join(settings.storage_path, "pdf")
    os.makedirs(pdf_dir, exist_ok=True)

    # Parse metadata umum secara aman
    parsed_release_date = None
    if release_date and release_date.strip():
        try:
            parsed_release_date = date.fromisoformat(release_date.strip())
        except ValueError:
            pass

    parsed_category_id = None
    if category_id and str(category_id).strip().isdigit():
        parsed_category_id = int(str(category_id).strip())

    results = []
    success_count = 0
    duplicate_count = 0
    failed_count = 0

    # 2. Looping (perulangan) untuk memproses tiap file satu per satu
    for idx, file in enumerate(files):
        fname = file.filename or f"unknown_{idx + 1}"

        # Validasi ekstensi harus PDF
        if not fname.lower().endswith(".pdf"):
            failed_count += 1
            results.append({
                "filename": fname,
                "status": "failed",
                "error": "Hanya file PDF yang diterima (format salah)",
            })
            continue

        try:
            # 3. Baca konten file & hitung SHA-256 hash serta ukuran file
            content = await file.read()
            file_hash = hashlib.sha256(content).hexdigest()
            file_size = len(content)

            # [US-19] Cek duplikasi: ditolak HANYA JIKA nilai file_hash DAN file_size_bytes keduanya sama persis
            existing = db.query(Document).filter(
                Document.file_hash == file_hash,
                Document.file_size_bytes == file_size,
            ).first()
            if existing:
                duplicate_count += 1
                results.append({
                    "filename": fname,
                    "status": "duplicate",
                    "message": (
                        f"Dokumen duplikat terdeteksi (Hash SHA-256 & ukuran {file_size} bytes cocok persis "
                        f"dengan ID: {existing.id}, Reg: {existing.regulation_number or '-'})"
                    ),
                    "document_id": existing.id,
                    "regulation_number": existing.regulation_number,
                    "file_hash": file_hash,
                    "file_size_bytes": file_size,
                })
                continue

            # 4. Tentukan nama file yang aman & simpan fisik file ke storage
            raw_basename = os.path.basename(fname)
            clean_basename = "".join(c for c in raw_basename if c.isalnum() or c in "._- ")
            if not clean_basename.lower().endswith(".pdf"):
                clean_basename += ".pdf"

            if len(files) == 1 and regulation_number and regulation_number.strip():
                safe_filename = f"{regulation_number.strip().replace('/', '-')}.pdf"
            else:
                safe_filename = f"{file_hash[:12]}_{clean_basename}"

            file_path = os.path.join(pdf_dir, safe_filename)
            async with aiofiles.open(file_path, "wb") as out_file:
                await out_file.write(content)

            # 5. Tentukan judul dan nomor regulasi
            if len(files) == 1:
                doc_title = title.strip() if (title and title.strip()) else fname
                doc_reg_number = regulation_number.strip() if (regulation_number and regulation_number.strip()) else None
            else:
                if title and title.strip():
                    doc_title = f"{title.strip()} - {fname}"
                else:
                    doc_title = fname.rsplit(".", 1)[0] if "." in fname else fname

                if regulation_number and regulation_number.strip():
                    doc_reg_number = f"{regulation_number.strip()}_{idx + 1}"
                else:
                    doc_reg_number = None

            # 6. Simpan metadata ke tabel documents
            doc = Document(
                title=doc_title[:255],
                regulation_number=doc_reg_number[:100] if doc_reg_number else None,
                regulation_type=regulation_type.strip() if (regulation_type and regulation_type.strip()) else None,
                release_date=parsed_release_date,
                source_url=source_url.strip() if (source_url and source_url.strip()) else None,
                file_path_pdf=file_path,
                file_hash=file_hash,
                file_size_bytes=file_size,
                standardized_filename=safe_filename[:255],
                access_classification=access_classification,
                document_role=document_role,
                status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
                processing_status=StatusPemrosesan.diterima,
                category_id=parsed_category_id,
                job_id=job.id,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            success_count += 1
            results.append({
                "filename": fname,
                "status": "success",
                "document_id": doc.id,
                "title": doc.title,
                "regulation_number": doc.regulation_number,
                "file_size_bytes": doc.file_size_bytes,
                "file_hash": doc.file_hash,
            })

        except Exception as item_exc:
            db.rollback()
            failed_count += 1
            results.append({
                "filename": fname,
                "status": "failed",
                "error": f"Gagal memproses file: {str(item_exc)}",
            })

    # 7. Selesaikan status JobIngest
    job.success_count = success_count
    job.duplicate_count = duplicate_count
    job.failed_count = failed_count
    job.finished_at = func.now()

    if success_count == 0 and failed_count > 0:
        job.status = StatusJobIngest.gagal
    else:
        job.status = StatusJobIngest.selesai

    db.commit()
    db.refresh(job)

    # 8. Rangkuman response hasil proses
    return {
        "message": (
            f"Proses unggah selesai: {success_count} berhasil, "
            f"{duplicate_count} duplikat, {failed_count} gagal "
            f"dari total {len(files)} file."
        ),
        "job_id": job.id,
        "total_files": len(files),
        "success_count": success_count,
        "duplicate_count": duplicate_count,
        "failed_count": failed_count,
        "details": results,
    }


@router.get("/jobs", summary="Riwayat job ingest")
def list_jobs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[StatusJobIngest] = None,
    job_type: Optional[JenisJobIngest] = None,
    db: Session = Depends(get_db),
):
    """Mengembalikan riwayat JobIngest dengan pagination dan filter opsional."""
    query = db.query(JobIngest)
    if status:
        query = query.filter(JobIngest.status == status)
    if job_type:
        query = query.filter(JobIngest.job_type == job_type)

    total = query.count()
    jobs = query.order_by(JobIngest.id.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "source_ref": j.source_ref,
                "triggered_by": j.triggered_by,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "status": j.status,
                "success_count": j.success_count,
                "duplicate_count": j.duplicate_count,
                "failed_count": j.failed_count,
            }
            for j in jobs
        ],
    }


@router.get("/check-duplicate", summary="Screening dedup sebelum upload (hemat bandwidth scraper)")
def check_duplicate(
    file_hash: Optional[str] = None,
    file_size: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Endpoint ringan untuk pengecekan duplikasi **sebelum** scraper ML melakukan upload penuh.

    Alur yang direkomendasikan untuk scraper:
    1. Hitung SHA-256 hash file di sisi scraper (tanpa upload).
    2. Panggil endpoint ini dengan `file_hash` tersebut.
    3. Jika `is_duplicate: true` → lewati upload, hemat bandwidth.
    4. Jika `is_duplicate: false` → lanjutkan ke `/upload-pdf`.

    Query params (minimal satu harus diisi):
    - **file_hash**: SHA-256 hash file (rekomendasi utama, paling akurat).
    - **file_size**: Ukuran file dalam byte (opsional, hanya sebagai info tambahan).
    """
    if not file_hash and file_size is None:
        raise HTTPException(
            status_code=400,
            detail="Minimal satu parameter harus diisi: 'file_hash' atau 'file_size'.",
        )

    # [US-19] Jika kedua parameter diberikan, filter kedua kondisi secara persis
    if file_hash and file_size is not None:
        existing = db.query(Document).filter(
            Document.file_hash == file_hash,
            Document.file_size_bytes == file_size,
        ).first()
        if existing:
            return {
                "is_duplicate": True,
                "message": (
                    f"Dokumen duplikat terdeteksi (Hash dan ukuran {existing.file_size_bytes} bytes cocok persis). "
                    f"ID: {existing.id}, "
                    f"Nomor regulasi: {existing.regulation_number or 'tidak tersedia'}, "
                    f"Judul: {existing.title}."
                ),
                "existing_document_id": existing.id,
                "regulation_number": existing.regulation_number,
            }
        return {
            "is_duplicate": False,
            "message": "Dokumen dengan hash dan ukuran file tersebut tidak ditemukan di database. Aman untuk diupload.",
            "existing_document_id": None,
            "regulation_number": None,
        }

    # Cek jika hanya file_hash yang diberikan
    if file_hash:
        existing = db.query(Document).filter(Document.file_hash == file_hash).first()
        if existing:
            return {
                "is_duplicate": True,
                "message": (
                    f"Dokumen sudah ada di database (berdasarkan hash). "
                    f"ID: {existing.id}, "
                    f"Nomor regulasi: {existing.regulation_number or 'tidak tersedia'}, "
                    f"Judul: {existing.title}."
                ),
                "existing_document_id": existing.id,
                "regulation_number": existing.regulation_number,
            }
        return {
            "is_duplicate": False,
            "message": "Hash tidak ditemukan di database. Dokumen aman untuk diupload.",
            "existing_document_id": None,
            "regulation_number": None,
        }

    # Fallback: hanya file_size yang diberikan (tidak cukup untuk dedup akurat)
    return {
        "is_duplicate": False,
        "message": (
            "Pengecekan berdasarkan ukuran file saja tidak cukup akurat untuk memastikan duplikasi. "
            "Sertakan 'file_hash' (SHA-256) untuk hasil yang tepat."
        ),
        "existing_document_id": None,
        "regulation_number": None,
    }


@router.get("/status", summary="Status ingest pipeline")
def ingest_status(db: Session = Depends(get_db)):
    """Cek ringkasan dokumen dan job di pipeline ingest."""
    total_docs = db.query(Document).count()
    berlaku_docs = db.query(Document).filter(Document.status_keberlakuan == StatusKeberlakuan.berlaku).count()
    total_jobs = db.query(JobIngest).count()
    return {
        "total_documents": total_docs,
        "berlaku_documents": berlaku_docs,
        "total_jobs": total_jobs,
        "storage_path": settings.storage_path,
    }


@router.post("/scrape-url", summary="Trigger scraping dokumen dari URL JDIH/OJK")
async def trigger_scraping(
    source_url: str = Form(..., description="URL target JDIH atau portal regulasi resmi"),
    title: str = Form(..., description="Prediksi judul regulasi"),
    access_classification: KlasifikasiAkses = Form(
        ..., description="Klasifikasi akses (publik / non_publik) - WAJIB NDA"
    ),
    category_id: Optional[int] = Form(None, description="ID kategori KB terkait"),
    db: Session = Depends(get_db),
):
    """
    Endpoint untuk memicu proses scraping dari URL eksternal (JDIH/OJK).
    """
    job = JobIngest(
        job_type=JenisJobIngest.scraping,
        source_ref=source_url,
        triggered_by="backend_trigger",
        status=StatusJobIngest.berjalan,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        return {
            "message": "Job scraping berhasil diinisiasi",
            "job_id": job.id,
            "source_url": source_url,
            "status": job.status,
            "note": "Menunggu proses penarikan file PDF oleh worker scraping."
        }

    except Exception as exc:
        db.rollback()
        job.status = StatusJobIngest.gagal
        job.failed_count = 1
        job.finished_at = func.now()
        db.commit()
        raise HTTPException(status_code=500, detail=f"Gagal memicu scraping: {str(exc)}")