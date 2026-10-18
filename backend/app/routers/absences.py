"""Takım sakatlık & ceza raporu: GET /api/absences"""
from fastapi import APIRouter

from ..database import SessionLocal
from .. import models

router = APIRouter(prefix="/api", tags=["absences"])


@router.get("/absences")
def list_absences():
    db = SessionLocal()
    try:
        # match_id boş olanlar genel rapordur; maça özel kayıtlar maç kartlarında gösterilir
        rows = (
            db.query(models.Absence)
            .filter(models.Absence.match_id.is_(None))
            .filter(models.Absence.type.in_(["injury", "suspension"]))
            .order_by(models.Absence.id)
            .all()
        )
        result = []
        for a in rows:
            player = db.query(models.Player).filter_by(id=a.player_id).first()
            if not player:
                continue
            stat = db.query(models.PlayerStat).filter_by(player_id=player.id).first()
            result.append({
                "player": player.name,
                "position": player.position,
                "type": a.type,
                "reason": a.reason,
                "return_note": a.return_note,
                "appearances": stat.appearances if stat else 0,
                "goals": stat.goals if stat else 0,
                "assists": stat.assists if stat else 0,
            })
        return result
    finally:
        db.close()
