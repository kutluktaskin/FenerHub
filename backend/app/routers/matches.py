from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/matches", tags=["matches"])

VALID_COMPETITIONS = {"super_lig", "uefa"}


def serialize_absence(a: models.Absence) -> dict:
    return {
        "player": a.player.name,
        "type": a.type,            # injury | suspension | returned
        "reason": a.reason,
        "return_note": a.return_note,
    }


def serialize_match(m: models.Match, with_absences: bool = False) -> dict:
    data = {
        "id": m.id,
        "competition": m.competition,
        "match_date": m.match_date.isoformat() if m.match_date else None,
        "kickoff_time": m.kickoff_time.strftime("%H:%M") if m.kickoff_time else None,
        "home": m.home_team.name,
        "away": m.away_team.name,
        "home_score": m.home_score,
        "away_score": m.away_score,
        "status": m.status,
        "minute": m.minute,
    }
    if with_absences:
        data["absences"] = [serialize_absence(a) for a in m.absences]
        # "returned" kayıtları eksik sayılmaz
        data["absence_count"] = sum(1 for a in m.absences if a.type != "returned")
    return data


def match_query(db: Session):
    return db.query(models.Match).options(
        joinedload(models.Match.home_team),
        joinedload(models.Match.away_team),
        joinedload(models.Match.absences).joinedload(models.Absence.player),
    )


@router.get("")
def list_matches(competition: str | None = None, db: Session = Depends(get_db)):
    if competition and competition not in VALID_COMPETITIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen turnuva")

    q = match_query(db)
    if competition:
        q = q.filter(models.Match.competition == competition)

    # Tarihi belirsiz maçlar ("Sezon Sonu") en sona
    q = q.order_by(models.Match.match_date.is_(None), models.Match.match_date)
    return [serialize_match(m) for m in q.all()]


@router.get("/upcoming")
def upcoming_matches(limit: int = 3, db: Session = Depends(get_db)):
    q = (
        match_query(db)
        .filter(models.Match.status.in_(["live", "scheduled"]))
        .filter(models.Match.match_date.is_not(None))
        # canlı maç her zaman en başta
        .order_by(models.Match.status != "live", models.Match.match_date)
        .limit(limit)
    )
    return [serialize_match(m, with_absences=True) for m in q.all()]


@router.get("/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = match_query(db).filter(models.Match.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    return serialize_match(m, with_absences=True)