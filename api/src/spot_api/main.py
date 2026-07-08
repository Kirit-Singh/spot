"""FastAPI app for spot. Chunk 5 exposes a health probe; real routes land per
chunk. The app imports no heavy engine code at module load."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="spot", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
