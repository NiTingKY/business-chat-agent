from __future__ import annotations

from pathlib import Path

import pytest

from app.services.milvus_store import MilvusDocumentStore
from app.tools.travel import check_travel_policy, set_policy_document_store


def _vec(seed: float) -> list[float]:
    return [seed] * 1536


def test_sqlite_vector_store_persists_and_searches_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "vectors.db"
    store = MilvusDocumentStore(host="localhost", port=19530, sqlite_path=db_path)
    store.use_sqlite_fallback()

    store.insert_vector(
        doc_id="policy-1#0001",
        title="差旅政策",
        doc_type="policy",
        content="经理级员工出差预算超过3000元需要提前审批。",
        vector=_vec(0.5),
    )

    reopened = MilvusDocumentStore(host="localhost", port=19530, sqlite_path=db_path)
    reopened.use_sqlite_fallback()
    results = reopened.search(_vec(0.5), top_k=1)

    assert results[0]["id"] == "policy-1#0001"
    assert "提前审批" in results[0]["content"]
    assert results[0]["backend"] == "sqlite"


@pytest.mark.asyncio
async def test_policy_tool_appends_vector_policy_evidence() -> None:
    class FakePolicyStore:
        connected = True

        def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
            return [
                {
                    "id": "policy-doc#0001",
                    "score": 0.99,
                    "title": "差旅制度",
                    "content": "经理级员工单次出差预算超过3000元，应在出行前完成审批。",
                }
            ]

    async def fake_embed(text: str) -> list[float]:
        return _vec(0.25)

    set_policy_document_store(FakePolicyStore(), embed_text=fake_embed)
    try:
        result = await check_travel_policy(
            {
                "employee_id": "u1",
                "grade": "manager",
                "origin_city": "北京",
                "destination_city": "上海",
                "departure_date": "2026-06-01",
                "estimated_total_cny": 3500,
            }
        )
    finally:
        set_policy_document_store(None)

    assert "向量库政策依据" in result
    assert "超过3000元" in result
