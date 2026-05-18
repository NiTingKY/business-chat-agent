from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "travel_knowledge"


def _load_pymilvus() -> tuple[Any, ...]:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )

    return (Collection, CollectionSchema, DataType, FieldSchema, connections, utility)


@dataclass
class MilvusDocumentStore:
    host: str
    port: int
    sqlite_path: str | Path | None = None
    collection_name: str = COLLECTION_NAME
    _collection: Any = None
    _connected: bool = field(default=False, init=False)
    _backend: str = field(default="milvus", init=False)
    _memory_docs: list[dict[str, Any]] = field(default_factory=list, init=False)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def backend(self) -> str:
        return self._backend

    def connect(self) -> bool:
        if self._connected and self._collection is not None:
            return True
        try:
            (
                MilvusCollection,
                MilvusCollectionSchema,
                DataType,
                FieldSchema,
                connections,
                utility,
            ) = _load_pymilvus()
            alias = "default"
            connections.connect(alias=alias, host=self.host, port=str(self.port), timeout=2)
            if not utility.has_collection(self.collection_name):
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
                    FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=32),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(
                        name="embedding",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=settings.embedding_dimension,
                    ),
                ]
                schema = MilvusCollectionSchema(fields, description="Business travel knowledge base")
                col = MilvusCollection(name=self.collection_name, schema=schema)
                index = {
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": 128},
                }
                col.create_index(field_name="embedding", index_params=index)
            self._collection = MilvusCollection(self.collection_name)
            self._collection.load()
            self._connected = True
            return True
        except Exception as exc:
            logger.warning("milvus.connect_failed", error=str(exc))
            if settings.enable_memory_vector_store:
                self.use_sqlite_fallback()
                logger.warning("milvus.sqlite_fallback_enabled")
                return True
            self._connected = False
            self._collection = None
            return False

    def use_sqlite_fallback(self) -> None:
        self._backend = "sqlite"
        self._collection = None
        self._connected = True
        self._init_sqlite()

    def _sqlite_file(self) -> Path:
        if self.sqlite_path is not None:
            return Path(self.sqlite_path)
        url = settings.database_url
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix):
            return Path(url[len(prefix) :])
        return Path("travel_agent_vectors.db")

    def _sqlite_connect(self) -> sqlite3.Connection:
        path = self._sqlite_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        with self._sqlite_connect() as conn:
            conn.execute(
                """
                create table if not exists policy_document_vectors (
                    id text primary key,
                    title text not null,
                    doc_type text not null,
                    content text not null,
                    embedding text not null,
                    metadata_json text,
                    created_at text not null
                )
                """
            )
            cols = {
                row["name"]
                for row in conn.execute("pragma table_info(policy_document_vectors)").fetchall()
            }
            if "metadata_json" not in cols:
                conn.execute("alter table policy_document_vectors add column metadata_json text")

    def insert_vector(
        self,
        doc_id: str,
        title: str,
        doc_type: str,
        content: str,
        vector: List[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._backend == "sqlite":
            with self._sqlite_connect() as conn:
                conn.execute(
                    """
                    insert or replace into policy_document_vectors
                    (id, title, doc_type, content, embedding, metadata_json, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        title,
                        doc_type,
                        content,
                        json.dumps(vector),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        utc_now().isoformat(),
                    ),
                )
            return
        if self._backend == "memory":
            self._memory_docs.append(
                {
                    "id": doc_id,
                    "title": title,
                    "doc_type": doc_type,
                    "content": content,
                    "embedding": vector,
                    "metadata": metadata or {},
                }
            )
            return
        if not self._collection:
            raise RuntimeError("Milvus not connected")
        self._collection.insert(
            [
                [doc_id],
                [title[:512]],
                [doc_type[:32]],
                [content[:65530]],
                [vector],
            ]
        )
        self._collection.flush()

    def clear(self) -> None:
        if self._backend == "sqlite":
            with self._sqlite_connect() as conn:
                conn.execute("delete from policy_document_vectors")
            return
        if self._backend == "memory":
            self._memory_docs.clear()
            return
        if self._collection is not None:
            self._collection.delete("id != ''")
            self._collection.flush()

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        *,
        query: str | None = None,
    ) -> List[Dict[str, Any]]:
        if self._backend == "sqlite":
            return self._search_sqlite(vector, top_k, query=query)
        if self._backend == "memory":
            return self._search_memory(vector, top_k, query=query)
        if not self._collection:
            raise RuntimeError("Milvus not connected")
        self._collection.load()
        res = self._collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=["title", "doc_type", "content"],
        )
        hits: List[Dict[str, Any]] = []
        for hit in res[0]:
            ent: Dict[str, Any] = {}
            raw = getattr(hit, "entity", None)
            if raw is not None:
                if hasattr(raw, "to_dict"):
                    ent = raw.to_dict()
                elif isinstance(raw, dict):
                    ent = raw
                else:
                    try:
                        ent = dict(raw)
                    except Exception:
                        ent = {}
            dist = getattr(hit, "distance", None)
            hits.append(
                {
                    "id": getattr(hit, "id", None),
                    "score": float(dist) if dist is not None else 0.0,
                    "title": ent.get("title"),
                    "doc_type": ent.get("doc_type"),
                    "content": str(ent.get("content") or "")[:2000],
                }
            )
        return hits

    def _search_memory(
        self,
        vector: List[float],
        top_k: int,
        *,
        query: str | None = None,
    ) -> List[Dict[str, Any]]:
        def cosine(a: list[float], b: list[float]) -> float:
            n = min(len(a), len(b))
            if n == 0:
                return 0.0
            dot = sum(a[i] * b[i] for i in range(n))
            na = sqrt(sum(a[i] * a[i] for i in range(n))) or 1.0
            nb = sqrt(sum(b[i] * b[i] for i in range(n))) or 1.0
            return dot / (na * nb)

        ranked = sorted(
            self._memory_docs,
            key=lambda item: cosine(vector, item["embedding"])
            + _keyword_score(query or "", f"{item['title']} {item['content']}"),
            reverse=True,
        )
        return [
            {
                "id": item["id"],
                "score": cosine(vector, item["embedding"])
                + _keyword_score(query or "", f"{item['title']} {item['content']}"),
                "title": item["title"],
                "doc_type": item["doc_type"],
                "content": str(item["content"])[:2000],
                "backend": "memory",
                "metadata": item.get("metadata", {}),
            }
            for item in ranked[:top_k]
        ]

    def _search_sqlite(
        self,
        vector: List[float],
        top_k: int,
        *,
        query: str | None = None,
    ) -> List[Dict[str, Any]]:
        with self._sqlite_connect() as conn:
            rows = conn.execute(
                "select id, title, doc_type, content, embedding, metadata_json from policy_document_vectors"
            ).fetchall()

        def cosine(a: list[float], b: list[float]) -> float:
            n = min(len(a), len(b))
            if n == 0:
                return 0.0
            dot = sum(a[i] * b[i] for i in range(n))
            na = sqrt(sum(a[i] * a[i] for i in range(n))) or 1.0
            nb = sqrt(sum(b[i] * b[i] for i in range(n))) or 1.0
            return dot / (na * nb)

        ranked: list[dict[str, Any]] = []
        for row in rows:
            embedding = json.loads(row["embedding"])
            vector_score = cosine(vector, embedding)
            keyword_score = _keyword_score(query or "", f"{row['title']} {row['content']}")
            ranked.append(
                {
                    "id": row["id"],
                    "score": vector_score + keyword_score,
                    "vector_score": vector_score,
                    "keyword_score": keyword_score,
                    "title": row["title"],
                    "doc_type": row["doc_type"],
                    "content": row["content"],
                    "backend": "sqlite",
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]


def _keyword_score(query: str, text: str) -> float:
    if not query:
        return 0.0
    terms = _query_terms(query)
    if not terms:
        return 0.0
    score = 0.0
    for term in terms:
        if term in text:
            score += 0.08 + min(len(term), 8) * 0.015
    return score


def _query_terms(query: str) -> list[str]:
    raw_terms = [term for term in re.split(r"[\s,，、。；;:：？?]+", query) if term]
    terms: set[str] = set(raw_terms)
    for raw in raw_terms:
        cjk = "".join(ch for ch in raw if "\u4e00" <= ch <= "\u9fff")
        if len(cjk) < 2:
            continue
        for size in (2, 3, 4, 5, 6):
            if len(cjk) < size:
                continue
            for index in range(0, len(cjk) - size + 1):
                terms.add(cjk[index : index + size])
    return sorted(terms, key=len, reverse=True)


def get_milvus_store() -> MilvusDocumentStore:
    return MilvusDocumentStore(host=settings.milvus_host, port=settings.milvus_port)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_doc_id() -> str:
    return str(uuid.uuid4())
