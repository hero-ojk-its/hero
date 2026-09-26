"""
scripts/perf_search.py
Uji performa pencarian Knowledge Base (Langkah 4).
Menguji 2.000 dokumen sintetis pada database hero_test, mengukur latency p50 dan p95
untuk 30 query campuran (masing-masing 3 kali repetisi), serta mencetak EXPLAIN (ANALYZE, BUFFERS)
sebagai bukti pemanfaatan indeks GIN.
"""
import os
import sys
import time
import random
import string
from datetime import date, timedelta
from typing import List

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.config import settings
from app.models.document import Document
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    MetodeEkstraksi,
)
from app.services.search_service import SearchService, SearchParams, SearchMode, SearchSort

# Kosakata Bahasa Indonesia untuk teks sintetis
ID_WORDS = [
    "keuangan", "perbankan", "transaksi", "nasabah", "kredit", "likuiditas", "resiko",
    "manajemen", "laporan", "tahunan", "otoritas", "jasa", "keuangan", "stabilitas",
    "sistem", "kebijakan", "makroprudensial", "mikroprudensial", "pasar", "modal",
    "asuransi", "dana", "pensiun", "lembaga", "pembiayaan", "efek", "emiten",
    "kustodian", "investasi", "reksadana", "obligasi", "sukuk", "tata", "kelola",
    "kepatuhan", "audit", "pengawasan", "direksi", "komisaris", "pemegang", "saham",
    "anggaran", "pendapatan", "belanja", "digital", "inovasi", "teknologi", "keamanan",
    "siber", "perlindungan", "data", "konsumen", "sanksi", "administrasi", "pidana"
]

def generate_random_text(word_count: int) -> str:
    return " ".join(random.choices(ID_WORDS, k=word_count))

def main():
    # Gunakan hero_test atau TEST_DATABASE_URL
    test_db_url = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://hero_user:hero_password@127.0.0.1:5432/hero_test")
    print(f"==> Menghubungkan ke database pengujian: {test_db_url}")
    engine = create_engine(test_db_url)

    # 1. Setup Data Sintetis 2.000 Dokumen
    print("==> Menyiapkan 2.000 dokumen sintetis...")
    synthetic_doc_ids: List[int] = []

    with Session(engine) as session:
        # Buat kategori uji jika belum ada
        cat = session.query(Category).filter(Category.name == "Uji Kategori").first()
        if not cat:
            cat = Category(name="Uji Kategori", auto_created=True)
            session.add(cat)
            session.flush()
        cat_id = cat.id

        reg_types = ["POJK", "SEOJK", "UU", "PP"]
        statuses = [
            StatusKeberlakuan.berlaku,
            StatusKeberlakuan.berlaku,
            StatusKeberlakuan.berlaku,
            StatusKeberlakuan.diubah,
            StatusKeberlakuan.dicabut,
        ]

        docs_to_insert = []
        base_date = date(2020, 1, 1)

        for i in range(1, 2001):
            reg_type = random.choice(reg_types)
            reg_year = 2020 + (i % 5)
            reg_num = f"{i}/{reg_type}.03/{reg_year}"
            title = f"Peraturan {reg_type} Nomor {i} Tahun {reg_year} tentang {generate_random_text(8)}"
            
            # Teks ~20.000 karakter (± 2.500 kata)
            raw_text = generate_random_text(2500)

            # Sisipkan frasa "sepatu roda" pada 15 dokumen
            if 1 <= i <= 15:
                raw_text = f"Dokumen regulasi mencakup ketentuan peralatan sepatu roda untuk operasional. {raw_text}"
            # Sisipkan "sepatu" dan "roda" secara terpisah pada 30 dokumen (dokumen 16 s.d. 45)
            elif 16 <= i <= 45:
                raw_text = f"Penyediaan perlengkapan sepatu pelindung kerja. {raw_text[:10000]} Putaran roda organisasi perbankan. {raw_text[10000:]}"

            # Dokumen 100 bernomor spesifik untuk pengujian
            if i == 100:
                reg_num = "11/POJK.03/2022"
                reg_type = "POJK"
                title = "Peraturan OJK tentang Penyelenggaraan Produk Bank Umum"

            status_keb = random.choice(statuses)
            if i <= 300:
                status_keb = StatusKeberlakuan.dicabut

            doc = Document(
                title=title[:250],
                regulation_number=reg_num,
                regulation_type=reg_type,
                release_date=base_date + timedelta(days=i % 1500),
                file_path_pdf=f"kb/{reg_type}/{reg_year}/doc_{i}.pdf",
                file_hash=f"hash_{i:06d}_{random.choice(string.ascii_lowercase)}",
                file_size_bytes=100000 + i * 50,
                standardized_filename=f"{reg_num.replace('/', '-')} {reg_year}.pdf",
                access_classification=KlasifikasiAkses.publik,
                document_role=PeranDokumen.corpus_eksisting,
                status_keberlakuan=status_keb,
                processing_status=StatusPemrosesan.terindeks,
                extraction_method=MetodeEkstraksi.teks_langsung,
                full_text=raw_text,
                category_id=cat_id,
            )
            docs_to_insert.append(doc)

        # Batch insert
        session.bulk_save_objects(docs_to_insert, return_defaults=True)
        session.commit()

        # Ambil ID dokumen yang baru dibuat
        all_inserted = session.query(Document.id).filter(Document.file_hash.like("hash_%")).all()
        synthetic_doc_ids = [r[0] for r in all_inserted]
        print(f"==> Berhasil memasukkan {len(synthetic_doc_ids)} dokumen sintetis.")

    try:
        # 2. Benchmark 30 Query Campuran
        print("\n==> Menjalankan benchmark 30 query campuran (masing-masing 3 repetisi)...")
        queries = [
            # Frasa eksak
            SearchParams(q="sepatu roda", mode=SearchMode.phrase),
            SearchParams(q="tata kelola", mode=SearchMode.phrase),
            SearchParams(q="manajemen resiko", mode=SearchMode.phrase),
            SearchParams(q="sistem stabilitas", mode=SearchMode.phrase),
            SearchParams(q="perlindungan data konsumen", mode=SearchMode.phrase),
            
            # Mode all (kata terpisah)
            SearchParams(q="sepatu roda", mode=SearchMode.all),
            SearchParams(q="bank nasabah likuiditas", mode=SearchMode.all),
            SearchParams(q="kredit pengawasan audit", mode=SearchMode.all),
            SearchParams(q="keamanan siber inovasi", mode=SearchMode.all),
            SearchParams(q="pasar modal reksadana", mode=SearchMode.all),
            
            # Mode web
            SearchParams(q='"sepatu roda" OR digital', mode=SearchMode.web),
            SearchParams(q='asuransi -investasi', mode=SearchMode.web),
            SearchParams(q='obligasi OR sukuk', mode=SearchMode.web),
            
            # Nomor regulasi
            SearchParams(q="11/POJK.03/2022"),
            SearchParams(q="11-POJK.03-2022"),
            SearchParams(regulation_number="11-POJK.03-2022"),
            SearchParams(regulation_number="POJK.03"),
            SearchParams(regulation_number="50/POJK"),
            
            # Filter jenis & status
            SearchParams(regulation_type="POJK", status_keberlakuan=[StatusKeberlakuan.berlaku]),
            SearchParams(regulation_type="SEOJK", status_keberlakuan=[StatusKeberlakuan.dicabut]),
            SearchParams(regulation_type="UU", sort=SearchSort.release_date_desc),
            SearchParams(regulation_type="PP", year=2022),
            
            # Filter rentang tanggal
            SearchParams(date_from=date(2021, 1, 1), date_to=date(2023, 12, 31)),
            SearchParams(q="keuangan", date_from=date(2022, 1, 1), sort=SearchSort.relevance),
            SearchParams(q="laporan tahunan", year=2023),
            
            # Pengurutan
            SearchParams(q="perbankan", sort=SearchSort.release_date_asc),
            SearchParams(q="transaksi", sort=SearchSort.created_desc),
            SearchParams(q="otoritas jasa", sort=SearchSort.title_asc),
            
            # Pagination & edge case
            SearchParams(q="keuangan", skip=40, limit=20),
            SearchParams(q="   ", status_keberlakuan=[StatusKeberlakuan.berlaku]),
        ]

        latencies_ms = []

        with Session(engine) as session:
            svc = SearchService(session)
            for idx, q_param in enumerate(queries, 1):
                query_times = []
                count_res = 0
                for _ in range(3):
                    t0 = time.perf_counter()
                    count_res, items = svc.search(q_param)
                    t1 = time.perf_counter()
                    query_times.append((t1 - t0) * 1000.0)
                
                avg_time = sum(query_times) / len(query_times)
                latencies_ms.extend(query_times)
                # print(f"Query {idx:02d} ({q_param.q or 'no-q'}, mode={q_param.mode}): {avg_time:.2f} ms (matches: {count_res})")

        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
        max_t = latencies_ms[-1]

        print("\n==================================================")
        print("HASIL PENGUJIAN PERFORMA PENCARIAN (2.000 DOKUMEN)")
        print("==================================================")
        print(f"Total eksekusi query : {len(latencies_ms)} kali (30 skenario x 3 repetisi)")
        print(f"Latency p50          : {p50:.2f} ms")
        print(f"Latency p95          : {p95:.2f} ms")
        print(f"Latency p99          : {p99:.2f} ms")
        print(f"Latency Max          : {max_t:.2f} ms")
        print(f"Syarat (p95 < 1000ms): {'LULUS [OK]' if p95 < 1000 else 'GAGAL [FAIL]'}")
        print("==================================================\n")

        # 3. EXPLAIN (ANALYZE, BUFFERS)
        print("==> EXPLAIN (ANALYZE, BUFFERS) - 1. Query Frasa 'sepatu roda':")
        with engine.connect() as conn:
            phrase_explain = conn.execute(text("""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, title, regulation_number, ts_rank_cd(search_vector, phraseto_tsquery('simple', 'sepatu roda')) AS rank
                FROM documents
                WHERE search_vector @@ phraseto_tsquery('simple', 'sepatu roda')
                ORDER BY rank DESC
                LIMIT 20;
            """)).fetchall()
            for row in phrase_explain:
                print("  ", row[0])

            print("\n==> EXPLAIN (ANALYZE, BUFFERS) - 1b. Query Frasa dengan GIN Index Scan (enable_seqscan=off):")
            conn.execute(text("SET enable_seqscan = off;"))
            phrase_gin_explain = conn.execute(text("""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, title, regulation_number, ts_rank_cd(search_vector, phraseto_tsquery('simple', 'sepatu roda')) AS rank
                FROM documents
                WHERE search_vector @@ phraseto_tsquery('simple', 'sepatu roda')
                ORDER BY rank DESC
                LIMIT 20;
            """)).fetchall()
            for row in phrase_gin_explain:
                print("  ", row[0])

            print("\n==> EXPLAIN (ANALYZE, BUFFERS) - 2. Query Nomor Reg Trigram '11/POJK.03/2022' (enable_seqscan=off):")
            reg_explain = conn.execute(text("""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, title, regulation_number
                FROM documents
                WHERE regulation_number ILIKE '%11/POJK.03/2022%'
                LIMIT 20;
            """)).fetchall()
            for row in reg_explain:
                print("  ", row[0])
            conn.execute(text("SET enable_seqscan = on;"))

    finally:
        # 4. Cleanup Data Sintetis
        print("\n==> Membersihkan data sintetis dari hero_test...")
        with Session(engine) as session:
            deleted = session.query(Document).filter(Document.file_hash.like("hash_%")).delete(synchronize_session=False)
            session.commit()
            print(f"==> Selesai. {deleted} dokumen sintetis dibersihkan.")

if __name__ == "__main__":
    main()
