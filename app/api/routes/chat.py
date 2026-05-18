from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.domain.schemas import ChatRequest, ChatResponse, StreamChunk, StreamChunkType
from app.gateway.api import ApiGateway

router = APIRouter(tags=["chat"])


def get_gateway(request: Request) -> ApiGateway:
    return request.app.state.gateway


@router.post("/chat", response_model=None)
async def chat(
    body: ChatRequest,
    gateway: ApiGateway = Depends(get_gateway),
) -> Union[ChatResponse, StreamingResponse]:
    if body.stream:

        async def event_gen() -> AsyncIterator[str]:
            idx = 0
            try:
                async for chunk in gateway.stream_chat(body):
                    payload = chunk.model_dump(mode="json")
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    idx += 1
            except Exception as exc:
                err = StreamChunk(
                    type=StreamChunkType.ERROR,
                    index=idx,
                    error=str(exc),
                )
                yield f"data: {json.dumps(err.model_dump(mode='json'), ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    result = await gateway.complete_chat(body)
    raw = result.raw_response
    return ChatResponse(
        id=raw["id"],
        created=raw["created"],
        model=raw["model"],
        choices=raw["choices"],
        usage=raw.get("usage"),
        session_id=result.session_id,
    )
