-- Script ini otomatis dijalankan PostgreSQL saat container pertama kali dibuat
-- (via docker-entrypoint-initdb.d)

-- Aktifkan ekstensi pgvector untuk kolom embedding
CREATE EXTENSION IF NOT EXISTS vector;

-- Verifikasi ekstensi aktif
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
