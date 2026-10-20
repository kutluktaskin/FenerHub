"""Kadro ve oyuncu istatistikleri: GET /api/squad"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/squad", tags=["squad"])

SEASON = "2026-27"
STATUS_MAP = {"injury": "injured", "suspension": "suspended"}


@router.get("")
def get_squad(db: Session = Depends(get_db)):
    players = (
        db.query(models.Player)
        .options(joinedload(models.Player.stats))
        .order_by(models.Player.id)
        .all()
    )

    # match_id boş olan kayıtlar = genel sakatlık/ceza raporu
    general_absences = (
        db.query(models.Absence)
        .filter(models.Absence.match_id.is_(None))
        .all()
    )
    absence_by_player = {a.player_id: a for a in general_absences}

    result = []
    for p in players:
        stat = next((s for s in p.stats if s.season == SEASON), None)
        absence = absence_by_player.get(p.id)
        result.append({
            "id": p.id,
            "name": p.name,
            "position": p.position,
            "shirt_number": p.shirt_number,
            "appearances": stat.appearances if stat else 0,
            "goals": stat.goals if stat else 0,
            "assists": stat.assists if stat else 0,
            "status": STATUS_MAP.get(absence.type, "available") if absence else "available",
            "status_reason": absence.reason if absence else None,
            "return_note": absence.return_note if absence else None,
        })
    return result