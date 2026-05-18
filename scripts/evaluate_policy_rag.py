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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


CASES = [
    {
        "name": "省外伙食补助",
        "query": "省外出差伙食补助费每天多少钱",
        "expected": ["每人每天100元"],
    },
    {
        "name": "省外公杂费",
        "query": "省外出差公杂费补助标准是多少",
        "expected": ["每人每天80元"],
    },
    {
        "name": "上海其余人员住宿费",
        "query": "北京上海其余人员住宿费限额标准",
        "expected": ["其余人员350元/天"],
    },
    {
        "name": "报销时限材料",
        "query": "出差结束后多久报销 需要提供什么材料",
        "expected": ["一个月内办理报销手续", "出差审批、报销单"],
    },
    {
        "name": "无住宿发票",
        "query": "实际发生住宿但没有住宿费发票能报伙食补助费和公杂费吗",
        "expected": ["不得报销伙食补助费和公杂费"],
    },
]


async def evaluate(top_k: int) -> dict:
    store = get_milvus_store()
    store.connect()
    embedder = EmbeddingService()
    results = []
    passed = 0
    for case in CASES:
        vector = await embedder.embed_text(case["query"])
        hits = store.search(vector, top_k=top_k, query=case["query"])
        joined = "\n".join(hit.get("content", "") for hit in hits)
        ok = all(token in joined for token in case["expected"])
        passed += int(ok)
        results.append(
            {
                "name": case["name"],
                "ok": ok,
                "query": case["query"],
                "expected": case["expected"],
                "hits": [
                    {
                        "title": hit.get("title"),
                        "score": hit.get("score"),
                        "keyword_score": hit.get("keyword_score"),
                        "content": str(hit.get("content", ""))[:260],
                    }
                    for hit in hits
                ],
            }
        )
    return {"backend": store.backend, "passed": passed, "total": len(CASES), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate policy RAG retrieval quality.")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.top_k))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
