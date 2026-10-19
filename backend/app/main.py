import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine, Base
from .routers import standings, squad, matches, absences
from .auto_sync import sync_loop
from .forum import router as forum_router 

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()


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
        "https://fenerhub-frontend.vercel.app",  # Vercel'deki canlı site adresin
    ],
    allow_methods=["*"],  # Tüm HTTP metodlarına izin ver
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

