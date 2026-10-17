from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/standings", tags=["standings"])

VALID_COMPETITIONS = {"super_lig", "uefa"}


@router.get("/{competition}")
def get_standings(competition: str, db: Session = Depends(get_db)):
    if competition not in VALID_COMPETITIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen turnuva")

    rows = (
        db.query(models.Standing)
        .filter(models.Standing.competition == competition)
        .order_by(models.Standing.position)
        .all()
    )
    return [
        {
            "position": s.position,
            "team": s.team.name,
            "played": s.played,
            "won": s.won,
            "drawn": s.drawn,
            "lost": s.lost,
            "goal_difference": s.goal_difference,
            "points": s.points,
            "is_fenerbahce": s.team.name == "Fenerbahçe",
        }
        for s in rows
    ]