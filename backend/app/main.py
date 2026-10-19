
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine, Base
from .forum import forum_router
from .routers import standings, squad, matches, absences
from .auto_sync import sync_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    task = asyncio.create_task(sync_loop())

    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Fenerbahçe Match Center API",
    description="Maçlar, kadro, sakatlıklar ve puan durumu için REST API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://fenerhub-frontend.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(standings.router)
app.include_router(squad.router)
app.include_router(matches.router)
app.include_router(absences.router)
app.include_router(forum_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
