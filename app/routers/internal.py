"""
Router: /api/v1/internal/articles
Endpoint INTERNAL — dipakai oleh ML pipeline untuk bulk insert hasil
ekstraksi/chunking pasal beserta embedding-nya ke tabel articles.

Endpoint ini TIDAK dimaksudkan untuk akses publik. Pastikan di-protect dengan
middleware API-key atau firewall rule di level infrastruktur sebelum production.
"""
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.article import Article
from app.schemas.article import BulkArticleIn, BulkArticleResponse

router = APIRouter()


def verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    """
    Dependency proteksi untuk endpoint service-to-service (dipanggil pipeline ML,
    bukan user via browser). Pakai API-key sederhana lewat header, bukan JWT --
    supaya script Fathir tidak perlu ikut alur login OAuth2 cuma untuk kirim data.
    """
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="API key internal tidak valid")


@router.post(
    "/articles",
    response_model=BulkArticleResponse,
    summary="[Internal] Bulk insert chunk pasal dari ML pipeline",
    dependencies=[Depends(verify_internal_api_key)],
    description=(
        "Menerima list chunk pasal hasil ekstraksi / chunking pipeline ML dan "
        "menyimpannya ke tabel `articles` secara bulk. "
        "Setiap item dapat menyertakan embedding pgvector (1536-dim) atau mengirim "
        "`null` jika embedding belum tersedia. "
        "\n\n> ⚠️ **Endpoint ini bersifat internal** — WAJIB menyertakan header "
        "X-Internal-API-Key yang cocok dengan INTERNAL_API_KEY di .env."
    ),
)
def bulk_insert_articles(
    payload: BulkArticleIn,
    db: Session = Depends(get_db),
) -> BulkArticleResponse:
    """
    Bulk insert pasal dari pipeline ML.

    Langkah:
    1. Validasi payload via Pydantic (otomatis oleh FastAPI).
    2. Konversi setiap ArticleChunkIn → ORM Article.
    3. bulk insert dengan db.add_all() + db.commit().
    4. Jika ada error, rollback & kembalikan HTTP 500.
    5. Kembalikan 200 OK dengan jumlah pasal yang tersimpan.
    """
    chunks = payload.articles

    # Bangun list ORM object
    orm_articles: List[Article] = []
    for chunk in chunks:
        article = Article(
            document_id=chunk.document_id,
            level=chunk.level,
            chapter_title=chunk.chapter_title,
            article_number=chunk.article_number,
            content_text=chunk.content_text,
            order_index=chunk.order_index,
            # pgvector menerima list[float] langsung dari SQLAlchemy
            embedding=chunk.embedding,
        )
        orm_articles.append(article)

    try:
        db.add_all(orm_articles)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menyimpan pasal ke database: {str(exc)}",
        )

    inserted_count = len(orm_articles)
    return BulkArticleResponse(
        status="ok",
        inserted_count=inserted_count,
        message=f"Berhasil menyimpan {inserted_count} pasal ke tabel articles.",
    )
