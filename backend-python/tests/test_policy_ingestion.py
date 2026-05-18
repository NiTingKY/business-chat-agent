from __future__ import annotations

from pathlib import Path

from app.services.milvus_store import MilvusDocumentStore
from app.services.policy_ingestion import build_policy_chunks


POLICY_SAMPLE = (
    "\u6d59\u6c5f\u5de5\u4e1a\u5927\u5b66\u5dee\u65c5\u8d39\u7ba1\u7406\u89c4\u5b9a\n"
    "\u7b2c\u4e8c\u5341\u6761? "
    "\u51fa\u5dee\u4eba\u5458\u51fa\u5dee\u7ed3\u675f\u540e\uff0c"
    "\u5e94\u5728\u4e00\u4e2a\u6708\u5185\u529e\u7406\u62a5\u9500\u624b\u7eed\u3002\n"
    "\u5206\u5730\u533a\u3001\u5206\u7ea7\u522b\u5dee\u65c5\u4f4f\u5bbf\u8d39\u623f\u578b\n"
    "\u5317\u4eac\u3001\u4e0a\u6d77\u3001\u6d77\u5357\u3001"
    "\u897f\u85cf\u3001\u9752\u6d77\u3001\u6df1\u5733\n"
    "800\n"
    "500\n"
    "350\n"
)


def test_policy_ingestion_builds_article_and_table_chunks() -> None:
    chunks = build_policy_chunks(POLICY_SAMPLE, source="travel.doc")
    texts = [chunk.content for chunk in chunks]

    assert any(
        "\u7b2c\u4e8c\u5341\u6761" in text
        and "\u4e00\u4e2a\u6708\u5185\u529e\u7406\u62a5\u9500\u624b\u7eed" in text
        for text in texts
    )
    assert any(
        "\u5317\u4eac\u3001\u4e0a\u6d77\u3001\u6d77\u5357\u3001"
        "\u897f\u85cf\u3001\u9752\u6d77\u3001\u6df1\u5733" in text
        and "\u5176\u4f59\u4eba\u5458350\u5143/\u5929" in text
        for text in texts
    )
    assert all("????" not in text for text in texts)


def test_policy_store_keyword_boost_finds_exact_policy_clause(tmp_path: Path) -> None:
    store = MilvusDocumentStore(host="localhost", port=19530, sqlite_path=tmp_path / "rag.db")
    store.use_sqlite_fallback()
    chunks = build_policy_chunks(POLICY_SAMPLE, source="travel.doc")
    for chunk in chunks:
        store.insert_vector(
            doc_id=chunk.chunk_id,
            title=chunk.title,
            doc_type="policy",
            content=chunk.content,
            vector=[0.01] * 768,
            metadata=chunk.metadata,
        )

    results = store.search(
        [0.0] * 768,
        top_k=1,
        query="\u5317\u4eac \u4e0a\u6d77 \u5176\u4f59\u4eba\u5458 \u4f4f\u5bbf\u8d39 \u6807\u51c6",
    )

    assert "\u5176\u4f59\u4eba\u5458350\u5143/\u5929" in results[0]["content"]
