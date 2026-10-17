from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine, Base
from .routers import standings, squad, matches

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fenerbahçe Match Center API",
    description="Maçlar, kadro, sakatlıklar ve puan durumu için REST API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(standings.router)
app.include_router(squad.router)
app.include_router(matches.router)
@app.get("/api/health")
def health():
    return {"status": "ok"}