import json
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/standings", tags=["standings"])

VALID_COMPETITIONS = {"super_lig", "uefa"}
SEASON = "2026-27"

# routers -> app -> backend
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(BACKEND_DIR, "standings_cache.json")


def from_cache(competition):
    """Tablo henüz doldurulmadıysa sync.py'nin JSON önbelleğinden oku."""
    try:
        with open(CACHE, encoding="utf-8") as f:
            rows = json.load(f).get("tables", {}).get(competition, [])
    except (FileNotFoundError, ValueError):
        return []
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


@router.get("/{competition}")
def get_standings(competition: str, db: Session = Depends(get_db)):
    if competition not in VALID_COMPETITIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen turnuva")
    rows = (
        db.query(models.Standing, models.Team)
        .join(models.Team, models.Standing.team_id == models.Team.id)
        .filter(models.Standing.competition == competition, models.Standing.season == SEASON)
        .order_by(models.Standing.position)
        .all()
    )
    result = [
        {
            "position": s.position,
            "team": t.name,
            "played": s.played,
            "won": s.won,
            "drawn": s.drawn,
            "lost": s.lost,
            "goal_difference": s.goal_difference,
            "points": s.points,
            "is_fenerbahce": t.name == "Fenerbahçe",
        }
        for s, t in rows
    ] or from_cache(competition)
    if not result:
        # Sayfa mevcut tabloyu korusun
        raise HTTPException(status_code=503, detail="Puan durumu henüz hazır değil")
    return result
