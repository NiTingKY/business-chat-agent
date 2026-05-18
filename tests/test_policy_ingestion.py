from __future__ import annotations

from pathlib import Path

from app.services.milvus_store import MilvusDocumentStore
from app.services.policy_ingestion import build_policy_chunks, clean_policy_text


def test_policy_ingestion_builds_article_and_table_chunks() -> None:
    raw = Path("docs/travel_doc_extracted_policy.txt").read_text(encoding="utf-8")
    chunks = build_policy_chunks(raw, source="travel.doc")
    texts = [chunk.content for chunk in chunks]

    assert any("第二十条" in text and "一个月内办理报销手续" in text for text in texts)
    assert any("北京、上海、海南、西藏、青海、深圳" in text and "其余人员350元/天" in text for text in texts)
    assert all("????" not in text for text in texts)


def test_policy_store_keyword_boost_finds_exact_policy_clause(tmp_path: Path) -> None:
    store = MilvusDocumentStore(host="localhost", port=19530, sqlite_path=tmp_path / "rag.db")
    store.use_sqlite_fallback()
    chunks = build_policy_chunks(
        """
浙江工业大学差旅费管理规定
第二十条? 出差人员出差结束后，应在一个月内办理报销手续。
北京、上海、海南、西藏、青海、深圳
800
500
350
""",
        source="travel.doc",
    )
    for chunk in chunks:
        store.insert_vector(
            doc_id=chunk.chunk_id,
            title=chunk.title,
            doc_type="policy",
            content=chunk.content,
            vector=[0.01] * 768,
            metadata=chunk.metadata,
        )

    results = store.search([0.0] * 768, top_k=1, query="北京 上海 其余人员 住宿费 标准")

    assert "其余人员350元/天" in results[0]["content"]
