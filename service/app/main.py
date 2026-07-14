"""SubFly FastAPI application: REST + WebSocket live subtitles."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import __version__
from app.config import Settings, get_settings
from app.engine import WhisperEngine
from app.session import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("subfly")

engine: WhisperEngine | None = None
sessions: SessionManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, sessions
    settings = get_settings()
    engine = WhisperEngine(settings)
    # Load model in a thread so startup stays responsive for /healthz readiness flip
    await asyncio.to_thread(engine.load)
    sessions = SessionManager(settings, engine)
    log.info("SubFly %s ready on %s:%s", __version__, settings.host, settings.port)
    yield
    # Stop all sessions on shutdown
    if sessions:
        for sid in list(sessions._sessions.keys()):
            await sessions.stop(sid)


app = FastAPI(title="SubFly", version=__version__, lifespan=lifespan)
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.allow_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_token(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_token:
        return
    token = None
    if x_api_token:
        token = x_api_token
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != settings.api_token:
        raise HTTPException(status_code=401, detail="invalid token")


class StartRequest(BaseModel):
    media_path: str = Field(..., description="Kodi file path or stream URL")
    start_seconds: float = 0.0
    language: str = "en"


class SeekRequest(BaseModel):
    position: float


class PauseRequest(BaseModel):
    paused: bool = True


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "model_ready": bool(engine and engine.ready),
    }


@app.get("/v1/info")
async def info(settings: Settings = Depends(get_settings), _: None = Depends(require_token)):
    return {
        "version": __version__,
        "model_size": settings.model_size,
        "device": settings.device,
        "compute_type": settings.compute_type,
        "language": settings.language,
        "sample_rate": settings.sample_rate,
        "chunk_seconds": settings.chunk_seconds,
        "path_maps": settings.path_map_pairs(),
    }


@app.post("/v1/sessions")
async def create_session(body: StartRequest, _: None = Depends(require_token)):
    assert sessions is not None
    try:
        state = await sessions.start_url_session(
            body.media_path,
            start_seconds=body.start_seconds,
            language=body.language,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": state.session_id,
        "resolved_path": state.resolved_path,
        "ws_url": f"/v1/ws/{state.session_id}",
    }


@app.post("/v1/sessions/{session_id}/seek")
async def seek_session(session_id: str, body: SeekRequest, _: None = Depends(require_token)):
    assert sessions is not None
    if not sessions.get(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    await sessions.seek(session_id, body.position)
    return {"ok": True}


@app.post("/v1/sessions/{session_id}/pause")
async def pause_session(session_id: str, body: PauseRequest, _: None = Depends(require_token)):
    assert sessions is not None
    if not sessions.get(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    await sessions.set_paused(session_id, body.paused)
    return {"ok": True}


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str, _: None = Depends(require_token)):
    assert sessions is not None
    await sessions.stop(session_id)
    return {"ok": True}


@app.websocket("/v1/ws/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    """Stream subtitle events for an existing session.

    Client may also send JSON control messages:
      {"type":"position","position":123.4}
      {"type":"pause","paused":true}
      {"type":"seek","position":50.0}
      {"type":"stop"}
    """
    assert sessions is not None
    settings = get_settings()

    # Optional token via query ?token=
    token = websocket.query_params.get("token", "")
    if settings.api_token and token != settings.api_token:
        await websocket.close(code=4401)
        return

    state = sessions.get(session_id)
    if not state:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    log.info("ws connected session=%s", session_id)

    async def pump_out() -> None:
        while True:
            msg = await state.outbound.get()
            await websocket.send_json(msg)
            if msg.get("type") in {"session_stopped", "pipeline_done"}:
                break

    async def pump_in() -> None:
        while True:
            data = await websocket.receive_json()
            typ = data.get("type")
            if typ == "position":
                state.playback_position = float(data.get("position", 0))
            elif typ == "pause":
                await sessions.set_paused(session_id, bool(data.get("paused", True)))
            elif typ == "seek":
                await sessions.seek(session_id, float(data.get("position", 0)))
            elif typ == "stop":
                await sessions.stop(session_id)
                break

    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        done, pending = await asyncio.wait(
            {out_task, in_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        log.info("ws disconnected session=%s", session_id)
    finally:
        for t in (out_task, in_task):
            if not t.done():
                t.cancel()
        await sessions.stop(session_id)


@app.websocket("/v1/live")
async def live_pcm_ws(websocket: WebSocket):
    """Accept raw mono s16le PCM frames and return live English subtitles.

    Protocol:
      1. Client connects (optional ?token=&language=en)
      2. Server sends {"type":"session_started",...}
      3. Client sends binary PCM frames (16kHz mono s16le) OR JSON controls
      4. Server sends {"type":"subtitle","start":..,"end":..,"text":"..."}
    """
    assert sessions is not None
    settings = get_settings()
    token = websocket.query_params.get("token", "")
    if settings.api_token and token != settings.api_token:
        await websocket.close(code=4401)
        return

    language = websocket.query_params.get("language") or settings.language
    await websocket.accept()
    state = await sessions.start_pcm_session(language=language)
    session_id = state.session_id

    async def pump_out() -> None:
        while True:
            msg = await state.outbound.get()
            await websocket.send_json(msg)
            if msg.get("type") in {"session_stopped"}:
                break

    out_task = asyncio.create_task(pump_out())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"] is not None:
                await sessions.ingest_pcm(session_id, message["bytes"])
            elif "text" in message and message["text"] is not None:
                import json

                data = json.loads(message["text"])
                typ = data.get("type")
                if typ == "position":
                    state.playback_position = float(data.get("position", 0))
                elif typ == "pause":
                    await sessions.set_paused(session_id, bool(data.get("paused", True)))
                elif typ == "stop":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        out_task.cancel()
        await sessions.stop(session_id)


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
