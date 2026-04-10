"""
VectorSearchEngine — búsqueda semántica de productos via OpenAI embeddings.

Cómo funciona:
  - Al iniciar, genera embeddings para los productos que no estén indexados y
    los guarda en la tabla `product_embeddings` de SQLite.
  - En cada búsqueda, embede el texto del cliente y calcula similaridad coseno
    contra la matriz de productos precargada en memoria.
  - Si la API de OpenAI no está disponible, el engine se desactiva y las
    llamadas a search() devuelven [] (fallback a búsqueda por tokens).

Uso de memoria: 63K productos × 256 dims × 4 bytes ≈ 64 MB.
Costo de generación: 63K × ~12 tokens ≈ 756K tokens ≈ $0.015 USD (una sola vez).
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import struct
import threading
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS  = 256   # reduced dimensions — cheaper, fast, good quality
BATCH_SIZE      = 512   # texts per API request (OpenAI max is 2048)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_embeddings (
    sku        TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    text_hash  TEXT NOT NULL
);
"""


def _pack(vec: list) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes):
    import numpy as np
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


def _product_text(p: dict) -> str:
    """Text we embed for each product — category + name gives the best signal."""
    cat  = str(p.get("category") or p.get("categoria") or "").strip()
    name = str(p.get("name") or p.get("model") or p.get("nombre") or "").strip()
    return f"{cat} {name}".strip()


class VectorSearchEngine:
    """
    Semantic product search backed by OpenAI embeddings stored in SQLite.

    Thread-safe: indexing runs in a background thread; search() works
    immediately (returns [] until the matrix is loaded).
    """

    def __init__(self, db_path: str, api_key: str = "") -> None:
        self._db_path = db_path
        self._enabled = bool(api_key)
        self._client  = None
        self._matrix  = None   # numpy (N, DIMS) — loaded after indexing
        self._skus: List[str] = []
        self._lock    = threading.Lock()
        self._ready   = threading.Event()
        self._stop    = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._ensure_schema()

        if not self._enabled:
            logger.info("vector_search_disabled: no api_key")
            return

        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            logger.info("vector_search_enabled")
        except Exception as exc:
            logger.warning("vector_search_openai_init_failed: %s", exc)
            self._enabled = False

    # ─── Public API ────────────────────────────────────────────────────────

    def start_indexing(self, products: List[dict]) -> None:
        """
        Kick off background indexing. Returns immediately.
        search() will return [] until ready; the app keeps running normally.
        """
        if not self._enabled or self._stop.is_set():
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._index_worker,
                args=(products,),
                daemon=True,
                name="vector-indexer",
            )
            self._thread.start()

    def search(self, query: str, top_k: int = 15) -> List[Tuple[str, float]]:
        """
        Return [(sku, similarity_score), ...] sorted descending.
        Returns [] if not ready yet or engine is disabled.
        """
        if not self._enabled or self._stop.is_set():
            return []
        with self._lock:
            if self._matrix is None:
                return []
            matrix = self._matrix
            skus   = self._skus

        try:
            import numpy as np
            q_vec = self._embed_texts([query])[0]
            q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-9)
            norms  = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
            scores = (matrix / norms) @ q_norm
            top_idx = np.argsort(scores)[::-1][:top_k]
            return [(skus[i], float(scores[i])) for i in top_idx]
        except Exception as exc:
            logger.warning("vector_search_query_failed: %s", exc)
            return []

    @property
    def is_ready(self) -> bool:
        return self._matrix is not None

    def close(self, timeout: float = 1.0) -> None:
        """Signal the background worker to stop and wait briefly for it."""
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)

    # ─── Private ───────────────────────────────────────────────────────────

    def _index_worker(self, products: List[dict]) -> None:
        conn: Optional[sqlite3.Connection] = None
        try:
            if self._stop.is_set():
                return
            conn = self._open_conn()
            self._generate_missing(conn, products)
            if self._stop.is_set():
                return
            matrix, skus = self._load_matrix(conn)
            if self._stop.is_set():
                return
            with self._lock:
                self._matrix = matrix
                self._skus   = skus
            if matrix is not None:
                self._ready.set()
                logger.info("vector_search_ready: %d products indexed", len(skus))
        except Exception as exc:
            logger.error("vector_search_index_worker_failed: %s", exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _generate_missing(self, conn: sqlite3.Connection, products: List[dict]) -> None:
        existing = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT sku, text_hash FROM product_embeddings"
            ).fetchall()
        }

        to_embed: List[Tuple[str, str, str]] = []  # (sku, text, hash)
        for p in products:
            sku = str(p.get("sku") or "").strip()
            if not sku:
                continue
            text = _product_text(p)
            h    = hashlib.sha256(text.encode()).hexdigest()[:16]
            if sku not in existing or existing[sku] != h:
                to_embed.append((sku, text, h))

        if not to_embed:
            logger.info("vector_search_index_up_to_date: %d products", len(products))
            return

        logger.info("vector_search_generating_embeddings: %d new/updated", len(to_embed))
        total = len(to_embed)
        done  = 0

        for batch_start in range(0, total, BATCH_SIZE):
            if self._stop.is_set():
                return
            batch  = to_embed[batch_start: batch_start + BATCH_SIZE]
            texts  = [b[1] for b in batch]
            try:
                vecs = self._embed_texts(texts)
            except Exception as exc:
                logger.error("vector_search_batch_failed batch=%d: %s", batch_start, exc)
                continue

            rows = [(batch[i][0], _pack(vecs[i]), batch[i][2]) for i in range(len(batch))]
            conn.executemany(
                "INSERT OR REPLACE INTO product_embeddings (sku, embedding, text_hash) VALUES (?,?,?)",
                rows,
            )
            conn.commit()
            done += len(batch)
            if done % 5000 < BATCH_SIZE:
                logger.info("vector_search_progress: %d/%d (%.0f%%)", done, total, 100 * done / total)

    def _load_matrix(self, conn: sqlite3.Connection):
        import numpy as np
        rows = conn.execute(
            "SELECT sku, embedding FROM product_embeddings ORDER BY sku"
        ).fetchall()
        if not rows:
            return None, []
        skus   = [r[0] for r in rows]
        matrix = np.stack([_unpack(r[1]) for r in rows]).astype(np.float32)
        logger.info("vector_search_matrix_loaded: shape=%s", matrix.shape)
        return matrix, skus

    def _embed_texts(self, texts: List[str]) -> list:
        resp = self._client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIMS,
        )
        ordered = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in ordered]

    def _ensure_schema(self) -> None:
        conn = self._open_conn()
        try:
            conn.execute(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _open_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)
