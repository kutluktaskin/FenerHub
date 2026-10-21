"""FastAPI uygulaması: router'lar, CORS ve açılışta migration + arka plan işleri
(auto_sync: periyodik REST senkronu, live: canlı maç WebSocket'i)."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import IS_SQLITE, db_label
from .migrate import run_migrations
from .forum import forum_router
from .routers import standings, squad, matches, absences
from .auto_sync import sync_loop
from . import cache, live, predictions, sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Şema Alembic ile yönetilir (app/migrate.py); veri silinmez
    run_migrations()
    print("Veritabanı:", db_label(), flush=True)
    if os.environ.get("RENDER") and IS_SQLITE:
        # Render'ın diski kalıcı değil: SQLite her deploy'da sıfırlanır
        print("UYARI: Render'da DATABASE_URL tanımlı değil, geçici SQLite kullanılıyor! "
              "Environment'a Neon adresini ekleyin.", flush=True)

    cache.seed_from_files()   # api_cache boşsa repodaki eski önbellek dosyalarını alır
    sync.fill_player_ids()    # oyuncu fotoğrafı eşleşmesi için kimlikler (önbellekten, istek atmaz)

    tasks = [asyncio.create_task(sync_loop()), asyncio.create_task(live.live_loop())]

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
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
        "https://fenerhub.vercel.app",
    ],
    allow_methods=["GET", "POST"],       # site sadece okur ve forumda gönderir
    allow_headers=["Content-Type"],
)


app.include_router(standings.router)
app.include_router(squad.router)
app.include_router(matches.router)
app.include_router(absences.router)
app.include_router(forum_router)
app.include_router(live.router)
app.include_router(predictions.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
