import json
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/standings", tags=["standings"])

VALID_COMPETITIONS = {"super_lig", "uefa"}

# routers -> app -> backend
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(BACKEND_DIR, "standings_cache.json")


@router.get("/{competition}")
def get_standings(competition: str):
    if competition not in VALID_COMPETITIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen turnuva")
    try:
        with open(CACHE, encoding="utf-8") as f:
            rows = json.load(f).get("tables", {}).get(competition, [])
    except (FileNotFoundError, ValueError):
        # Dosya yok ya da o an yazılıyor: sayfa mevcut tabloyu korusun
        raise HTTPException(status_code=503, detail="Puan durumu henüz hazır değil")
    return [
        {
            "position": r["position"],
            "team": r["team"],
            "played": r["played"],
            "won": r["won"],
            "drawn": r["drawn"],
            "lost": r["lost"],
            "goal_difference": r["goal_diff"],
            "points": r["points"],
            "is_fenerbahce": r["team"] == "Fenerbahçe",
        }
        for r in rows
    ]