"""Worker ekstraksi: antrian backend → OCR/metadata/pasal/vektor → backend.

Alur satu dokumen (kontrak ``ingest-extraction-contract.md`` §1):

    POST /internal/extraction/claim          ambil antrian (SKIP LOCKED)
    GET  /internal/documents/{id}/pdf        unduh PDF asli
      ↓ probe_pdf         magic bytes %PDF- + perbaikan pikepdf bila rusak
      ↓ extract_pdf       teks per halaman, OCR otomatis untuk halaman gambar
      ↓ extract_metadata  jenis / nomor / tanggal / dasar hukum / status
      ↓ read_identity     dari mana tiap unsur dibaca → keyakinan per field
      ↓ parse_structure   BAB / Pasal / ayat; lampiran dipisahkan
      ↓ ArticleEmbedder   satu vektor per pasal (LSA deterministik / semantik)
    PATCH /internal/documents/{id}/extraction   metadata + teks + keyakinan
    POST  /internal/articles                    pasal (+ embedding) per batch

Tiga hal yang membuat worker ini aman dijalankan berulang:

* **Tidak ada pasal ganda.** ``POST /internal/articles`` hanya INSERT, jadi
  buku besar lokal (``hero/bridge/state.py``) menolak mengirim pasal untuk
  dokumen+hash yang sudah pernah terkirim.
* **Kegagalan dilaporkan, bukan ditelan.** PDF rusak/terenkripsi dikirim
  sebagai ``error`` sehingga masuk ``ingest_failures`` dan bisa di-*retry*
  dari UI, bukan dibiarkan menggantung berstatus ``diproses``.
* **Dokumen tidak tersangkut.** Bila worker gagal sebelum mengirim apa pun,
  dokumen di-*requeue* ke status ``diterima``.

Mode Deterministik: seluruh jalur di atas offline dan tanpa AI. Satu-satunya
komponen yang bisa diminta model adalah embedding semantik — model lokal ONNX,
tidak ada teks yang keluar dari server (penting untuk dokumen ber-NDA).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hero.bridge import mapping
from hero.bridge.client import BackendClient, BackendError
from hero.bridge.config import BridgeSettings
from hero.bridge.embed import ArticleEmbedder, EmbedderUnavailable
from hero.bridge.state import BridgeState, default_path
from hero.config import Settings

log = logging.getLogger("hero.bridge.extract")

ENGINE = "hero-pipeline/deterministik"


@dataclass
class Outcome:
    document_id: int
    status: str                 # terindeks | perlu_koreksi | gagal_dicatat | dilewati | error
    articles: int = 0
    vectors: int = 0
    detail: str = ""
    seconds: float = 0.0

    def line(self) -> str:
        return (f"dok {self.document_id}: {self.status} · {self.articles} pasal"
                f"{f' · {self.vectors} vektor' if self.vectors else ''}"
                f"{f' · {self.detail}' if self.detail else ''} ({self.seconds:.1f}s)")


@dataclass
class RunReport:
    outcomes: list[Outcome] = field(default_factory=list)
    claimed: int = 0
    seconds: float = 0.0

    def count(self, status: str) -> int:
        return sum(1 for o in self.outcomes if o.status == status)

    def as_dict(self) -> dict[str, Any]:
        return {"diklaim": self.claimed, "detik": round(self.seconds, 1),
                "per_status": {s: self.count(s) for s in
                               ("terindeks", "perlu_koreksi", "gagal_dicatat", "dilewati", "error")
                               if self.count(s)},
                "pasal": sum(o.articles for o in self.outcomes),
                "vektor": sum(o.vectors for o in self.outcomes),
                "dokumen": [o.line() for o in self.outcomes]}


class ExtractionWorker:
    def __init__(self, settings: Settings, bridge: BridgeSettings, *,
                 client: BackendClient | None = None, state: BridgeState | None = None,
                 embedder: ArticleEmbedder | None = None,
                 staging: Path | None = None):
        self.settings = settings
        self.bridge = bridge
        self.client = client or BackendClient(bridge)
        self.state = state or BridgeState(default_path(settings))
        self.embedder = embedder if embedder is not None else ArticleEmbedder(settings, bridge)
        self.staging = Path(staging or (Path(settings.staging_dir) / "bridge"))
        self.staging.mkdir(parents=True, exist_ok=True)
        self._embed_warned = False
        self._rules = None

    # -- satu dokumen ----------------------------------------------------
    def process_one(self, item: dict[str, Any]) -> Outcome:
        from hero.extract.metadata import extract_metadata
        from hero.extract.pdf import extract_pdf, probe_pdf
        from hero.extract.quality import assess_quality
        from hero.extract.structure import parse_structure

        doc_id = int(item["document_id"])
        started = time.perf_counter()
        self.state.begin_extraction(doc_id, file_hash=item.get("file_hash"),
                                    attempt=int(item.get("attempt") or 0))
        pdf_path = self.staging / f"doc-{doc_id}.pdf"
        try:
            self.client.download_pdf(doc_id, pdf_path)
        except BackendError as exc:
            # Berkas tidak ada di penyimpanan backend: itu kegagalan ingest,
            # bukan kegagalan ekstraksi — dilaporkan agar muncul di UI.
            return self._fail(doc_id, "ekstraksi_gagal",
                              f"PDF tidak dapat diunduh dari backend: {exc}", started)

        try:
            probe = probe_pdf(pdf_path, self.settings.pdf)
            if not probe.get("valid"):
                return self._fail(doc_id, "ekstraksi_gagal",
                                  f"bukan PDF yang dapat dibaca: {probe.get('error')}", started)

            result = extract_pdf(pdf_path, self.settings.ocr, self.settings.pdf)
            if result.error and not result.char_count:
                code = "ocr_gagal" if result.is_scanned else "ekstraksi_gagal"
                return self._fail(doc_id, code, result.error or "tidak ada teks terbaca", started)

            md = extract_metadata(result.text, probe.get("pdf_metadata"),
                                 item.get("original_filename") or pdf_path.name)
            struct = parse_structure(result.pages)
            quality = assess_quality(result)
            identity = self._identity(pdf_path)

            payload = mapping.extraction_payload(
                md, result, identity=identity, quality=quality, bidang=self._bidang(md, result.text),
                send_full_text=self.bridge.send_full_text,
                max_chars=self.bridge.max_full_text_chars, engine=ENGINE)
            payload.pop("_grade", None)
            res = self.client.patch_extraction(doc_id, payload, force=True)
            backend_status = str(res.get("status") or "")

            # Dasar hukum, penerbit, tahun, status dari teks: tidak ada
            # tempatnya di skema backend, tapi graf relasi memerlukannya.
            self.state.record_metadata(doc_id, md.to_dict())

            sent, vectors = self._push_articles(doc_id, item, struct)
            detail = []
            if res.get("low_confidence_fields"):
                detail.append("keyakinan rendah: " + ", ".join(res["low_confidence_fields"]))
            if res.get("ignored_fields"):
                detail.append("koreksi manual dipertahankan: " + ", ".join(res["ignored_fields"]))
            if quality.get("grade") in ("perlu-review", "cukup"):
                detail.append(f"mutu ekstraksi {quality['grade']}")

            self.state.finish_extraction(doc_id, status="selesai", backend_status=backend_status,
                                         articles=sent, vectors=vectors,
                                         embedder=self.embedder.name)
            self.state.log("ekstraksi", str(doc_id),
                           {"status": backend_status, "pasal": sent, "vektor": vectors})
            return Outcome(doc_id, backend_status or "terindeks", sent, vectors,
                           " · ".join(detail), time.perf_counter() - started)
        except BackendError as exc:
            self.state.finish_extraction(doc_id, status="gagal", error=str(exc))
            self._requeue(doc_id)
            return Outcome(doc_id, "error", detail=str(exc), seconds=time.perf_counter() - started)
        except Exception as exc:                                 # noqa: BLE001
            log.exception("ekstraksi dokumen %s gagal tak terduga", doc_id)
            return self._fail(doc_id, "ekstraksi_gagal", f"{type(exc).__name__}: {exc}", started)
        finally:
            pdf_path.unlink(missing_ok=True)

    # -- bagian-bagian ---------------------------------------------------
    def _bidang(self, md, text: str) -> str | None:
        """Kategori peraturan sebagai label ``bidang`` backend (filter di layar KB).

        Aturannya ada di ``config/kategori.yaml`` (ADR-07), bukan di kode. Yang
        dikirim adalah labelnya ("IKNB"), bukan kode slug-nya ("iknb"), karena
        nilai itu tampil apa adanya di UI.
        """
        try:
            from hero.kb.classify import classify
            if self._rules is None:
                from hero.kb.classify import load_rules
                self._rules = load_rules(self.settings.classification.rules_file)
            code, _hits = classify(md, text, None, self._rules)
            return next((c.label for c in self._rules.kategori if c.kode == code), None)
        except Exception as exc:                                 # noqa: BLE001
            log.debug("klasifikasi kategori dilewati: %s", exc)
            return None

    def _identity(self, pdf_path: Path):
        """Dari mana tiap unsur identitas dibaca — dasar keyakinan per field.

        Dibungkus try/except karena ini hanya memperkaya keyakinan: kegagalan
        membacanya tidak boleh membatalkan ekstraksi yang sudah berhasil.
        """
        try:
            from hero.extract.firstpage import read_identity
            return read_identity(pdf_path, mode=self.settings.naming.mode,
                                 ocr_settings=self.settings.ocr)
        except Exception as exc:                                 # noqa: BLE001
            log.debug("identitas halaman 1 tidak terbaca (%s) — keyakinan memakai default", exc)
            return None

    def _push_articles(self, doc_id: int, item: dict[str, Any], struct) -> tuple[int, int]:
        already = self.state.articles_already_sent(doc_id, item.get("file_hash"))
        if already:
            log.info("dokumen %s sudah punya %s pasal terkirim — tidak dikirim ulang",
                     doc_id, already)
            return already, 0
        articles = [a for a in struct.articles if not a.in_attachment]
        if not articles:
            return 0, 0

        vectors: list[list[float] | None] | None = None
        if self.embedder.enabled:
            try:
                vectors = self.embedder.article_vectors([a.text for a in articles])
            except EmbedderUnavailable as exc:
                if not self._embed_warned:
                    log.warning("embedding dilewati: %s", exc)
                    self._embed_warned = True
            except Exception as exc:                             # noqa: BLE001
                log.warning("embedding gagal (%s) — pasal tetap dikirim tanpa vektor", exc)

        rows = mapping.article_payloads(doc_id, articles, vectors=vectors,
                                        push_ayat=self.bridge.push_ayat)
        # Halaman tiap pasal dicatat lokal: kolom halaman belum ada di tabel
        # articles backend, sedangkan bukti temuan harmonisasi wajib menyebutnya.
        # Kunci memakai label yang sama dengan yang dikirim ke backend
        # ("Pasal 2"), bukan nomor mentah — supaya cermin korpus bisa
        # mencocokkannya kembali.
        self.state.record_article_pages(
            doc_id, [(mapping.pasal_label(a.number), a.page) for a in articles])
        sent = 0
        n_vec = 0
        for start in range(0, len(rows), self.bridge.batch_articles):
            batch = rows[start:start + self.bridge.batch_articles]
            res = self.client.post_articles(batch)
            sent += int(res.get("inserted_count") or 0)
            n_vec += sum(1 for r in batch if r.get("embedding"))
            # Catat kemajuan tiap batch: worker yang mati di tengah tidak boleh
            # mengirim ulang batch yang sudah masuk.
            self.state.finish_extraction(doc_id, status="berjalan", articles=sent, vectors=n_vec,
                                         embedder=self.embedder.name)
        return sent, n_vec

    def _fail(self, doc_id: int, code: str, message: str, started: float) -> Outcome:
        try:
            res = self.client.patch_extraction(doc_id, mapping.failure_payload(code, message),
                                               force=True)
            status = str(res.get("status") or "gagal_dicatat")
        except BackendError as exc:
            log.error("tidak bisa melaporkan kegagalan dokumen %s: %s", doc_id, exc)
            status = "error"
        self.state.finish_extraction(doc_id, status="gagal", backend_status=status, error=message)
        self.state.log("kegagalan", str(doc_id), {"kode": code, "pesan": message[:300]})
        return Outcome(doc_id, status, detail=f"{code}: {message[:160]}",
                       seconds=time.perf_counter() - started)

    def _requeue(self, doc_id: int) -> None:
        try:
            self.client.requeue(doc_id)
        except BackendError as exc:
            log.warning("requeue dokumen %s gagal: %s", doc_id, exc)

    # -- loop ------------------------------------------------------------
    def run_once(self, limit: int | None = None,
                 progress: Callable[[str], None] | None = None) -> RunReport:
        say = progress or (lambda m: None)
        started = time.perf_counter()
        rep = RunReport()
        items = self.client.claim_extraction(limit or self.bridge.claim_documents)
        rep.claimed = len(items)
        if not items:
            rep.seconds = time.perf_counter() - started
            return rep
        say(f"{len(items)} dokumen diklaim")
        for item in items:
            out = self.process_one(item)
            rep.outcomes.append(out)
            say(f"  {out.line()}")
        rep.seconds = time.perf_counter() - started
        return rep

    def run_forever(self, *, max_batches: int | None = None,
                    stop: Callable[[], bool] | None = None,
                    progress: Callable[[str], None] | None = None) -> RunReport:
        """Polling sampai dihentikan. Antrian kosong = tidur ``poll_seconds``."""
        total = RunReport()
        batches = 0
        while not (stop and stop()):
            rep = self.run_once(progress=progress)
            total.outcomes.extend(rep.outcomes)
            total.claimed += rep.claimed
            total.seconds += rep.seconds
            batches += 1
            if max_batches and batches >= max_batches:
                break
            if not rep.claimed:
                time.sleep(self.bridge.poll_seconds)
        return total

    def close(self) -> None:
        self.client.close()
        self.state.close()
