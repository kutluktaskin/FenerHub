from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/absences", tags=["absences"])


@router.get("")
def get_absences(db: Session = Depends(get_db)):
    # match_id boş olan kayıtlar = genel rapor
    rows = (
        db.query(models.Absence)
        .options(
            joinedload(models.Absence.player).joinedload(models.Player.stats)
        )
        .filter(models.Absence.match_id.is_(None))
        .order_by(models.Absence.id)
        .all()
    )

    result = []
    for a in rows:
        stat = next((s for s in a.player.stats if s.season == "2026-27"), None)
        result.append({
            "player": a.player.name,
            "position": a.player.position,
            "type": a.type,
            "reason": a.reason,
            "return_note": a.return_note,
            "appearances": stat.appearances if stat else 0,
            "goals": stat.goals if stat else 0,
            "assists": stat.assists if stat else 0,
        })
    return result