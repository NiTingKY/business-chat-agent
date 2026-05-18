from __future__ import annotations

import hashlib
import math

from openai import AsyncOpenAI

from app.config import settings


class EmbeddingService:
    def __init__(self, model: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key or "dummy",
            base_url=settings.openai_base_url,
        )
        self._model = model or settings.openai_embedding_model

    @staticmethod
    def _local_embedding(text: str, dim: int | None = None) -> list[float]:
        dim = dim or settings.embedding_dimension
        values: list[float] = []
        seed = text.encode("utf-8") or b"empty"
        counter = 0
        while len(values) < dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend(((b / 255.0) * 2.0 - 1.0) for b in digest)
            counter += 1
        vec = values[:dim]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_text(self, text: str) -> list[float]:
        if not settings.openai_api_key:
            return self._local_embedding(text)
        try:
            resp = await self._client.embeddings.create(model=self._model, input=text[:8000])
            return list(resp.data[0].embedding)
        except Exception:
            if settings.enable_local_embeddings_fallback:
                return self._local_embedding(text)
            raise
