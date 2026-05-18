from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.embeddings import EmbeddingService
from app.services.milvus_store import get_milvus_store
from app.services.policy_ingestion import build_policy_chunks, clean_policy_text
from scripts.ingest_policy_doc import DEFAULT_DOC, extract_doc_text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


async def build(doc_path: Path, *, replace: bool) -> dict:
    raw_text = extract_doc_text(doc_path)
    clean_text = clean_policy_text(raw_text)
    chunks = build_policy_chunks(clean_text, source=doc_path.name)

    out_dir = ROOT / "docs" / "policy_rag"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "travel_policy_clean.txt").write_text(clean_text, encoding="utf-8")
    (out_dir / "travel_policy_chunks.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                }
                for chunk in chunks
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    store = get_milvus_store()
    store.connect()
    if replace:
        store.clear()

    embedder = EmbeddingService()
    for chunk in chunks:
        vector = await embedder.embed_text(chunk.content)
        store.insert_vector(
            doc_id=chunk.chunk_id,
            title=chunk.title,
            doc_type="policy",
            content=chunk.content,
            vector=vector,
            metadata=chunk.metadata,
        )

    return {
        "doc": str(doc_path),
        "backend": store.backend,
        "raw_chars": len(raw_text),
        "clean_chars": len(clean_text),
        "chunk_count": len(chunks),
        "clean_text": str(out_dir / "travel_policy_clean.txt"),
        "chunks_json": str(out_dir / "travel_policy_chunks.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build structured policy RAG index from travel.doc.")
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    parser.add_argument("--replace", action="store_true", help="Clear existing policy vectors first.")
    args = parser.parse_args()
    result = asyncio.run(build(Path(args.doc), replace=args.replace))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
