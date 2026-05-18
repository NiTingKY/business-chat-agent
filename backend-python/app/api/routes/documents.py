from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.domain.schemas import DocumentIngestRequest, DocumentIngestResponse
from app.services.embeddings import EmbeddingService
from app.services.milvus_store import new_doc_id, utc_now

router = APIRouter(tags=["documents"])


def _chunk_text(text: str, *, max_chars: int = 1800, overlap: int = 180) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(normalized) <= max_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        split_at = max(
            normalized.rfind("\n", start, end),
            normalized.rfind("。", start, end),
            normalized.rfind("；", start, end),
        )
        if split_at <= start + max_chars // 2:
            split_at = end
        chunk = normalized[start:split_at].strip()
        if chunk:
            chunks.append(chunk)
        if split_at >= len(normalized):
            break
        start = max(0, split_at - overlap)
    return chunks


@router.post("/documents/ingest", response_model=DocumentIngestResponse)
async def ingest_document(body: DocumentIngestRequest, request: Request) -> DocumentIngestResponse:
    vector_store = getattr(request.app.state, "milvus", None)
    if vector_store is None or not vector_store.connected:
        raise HTTPException(status_code=503, detail="Vector store is not connected")

    embedder = EmbeddingService()
    doc_id = new_doc_id()
    chunks = _chunk_text(body.content)
    try:
        first_vector_dim = None
        for index, chunk in enumerate(chunks, start=1):
            vector = await embedder.embed_text(chunk)
            first_vector_dim = first_vector_dim or len(vector)
            metadata = dict(body.metadata)
            metadata["chunk_index"] = index
            metadata["chunk_count"] = len(chunks)
            vector_store.insert_vector(
                doc_id=f"{doc_id}#{index:04d}",
                title=f"{body.title} #{index}",
                doc_type=body.doc_type,
                content=chunk,
                vector=vector,
                metadata=metadata,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector write failed: {exc}") from exc

    return DocumentIngestResponse(
        doc_id=doc_id,
        collection=getattr(vector_store, "collection_name", "travel_knowledge"),
        inserted_at=utc_now(),
        vector_dim=first_vector_dim,
    )


@router.get("/documents/search")
async def search_documents(
    request: Request,
    q: str = Query(..., min_length=1, description="Query text"),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    vector_store = getattr(request.app.state, "milvus", None)
    if vector_store is None or not vector_store.connected:
        raise HTTPException(status_code=503, detail="Vector store is not connected")

    embedder = EmbeddingService()
    vector = await embedder.embed_text(q)
    try:
        hits = vector_store.search(vector, top_k=top_k, query=q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc

    return {"query": q, "backend": getattr(vector_store, "backend", "milvus"), "results": hits}
