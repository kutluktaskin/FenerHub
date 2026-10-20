import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import cache, models
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


# ---------- Takım renkleri ve API id'leri ----------
# Veritabanında yok; sync'in önbelleğe kaydettiği maç sayfalarındaki teamColors alanından
# okunur (istek atmaz). Her maç için sorgu atılmasın diye en fazla dakikada bir yenilenir.
TEAM_INFO_TTL = 60
_team_cache = {"at": 0.0, "teams": {}}


def team_info() -> dict:
    if time.time() - _team_cache["at"] < TEAM_INFO_TTL:
        return _team_cache["teams"]
    try:
        from sync import ALIASES   # API adı -> veritabanındaki ad
    except Exception:
        ALIASES = {}
    teams = {}
    for name in ("next_0", "next_1", "last_0"):
        for e in cache.get(f"pages:{name}") or []:
            for side in ("homeTeam", "awayTeam"):
                t = e.get(side) or {}
                if not t.get("name"):
                    continue
                colors = t.get("teamColors") or {}
                teams[ALIASES.get(t["name"], t["name"])] = {
                    "api_id": t.get("id"),
                    "color": colors.get("primary"),
                    "color2": colors.get("secondary"),
                }
    _team_cache.update(at=time.time(), teams=teams)
    return teams


def serialize_match(m: models.Match, with_absences: bool = False) -> dict:
    teams = team_info()
    home = teams.get(m.home_team.name, {})
    away = teams.get(m.away_team.name, {})
    data = {
        "id": m.id,
        "api_id": m.api_id,
        "competition": m.competition,
        "match_date": m.match_date.isoformat() if m.match_date else None,
        "kickoff_time": m.kickoff_time.strftime("%H:%M") if m.kickoff_time else None,
        "home": m.home_team.name,
        "away": m.away_team.name,
        "home_score": m.home_score,
        "away_score": m.away_score,
        "status": m.status,
        "minute": m.minute,
        "status_code": m.status_code,
        "period_start": m.period_start,
        "period_initial": m.period_initial,
        # Kart renkleri ve logo eşlemesi için (bilinmiyorsa None)
        "home_api_id": home.get("api_id"),
        "away_api_id": away.get("api_id"),
        "home_color": home.get("color"),
        "home_color2": home.get("color2"),
        "away_color": away.get("color"),
        "away_color2": away.get("color2"),
    }
    if with_absences:
        data["absences"] = [serialize_absence(a) for a in m.absences]
        data["absence_count"] = sum(1 for a in m.absences if a.type != "returned")
    return data


def match_query(db: Session):
    return db.query(models.Match).options(
        joinedload(models.Match.home_team),
        joinedload(models.Match.away_team),
        joinedload(models.Match.absences).joinedload(models.Absence.player),
    )


# ---------- Maç detayı (sadece önbellekten okur, API'ye istek atmaz) ----------
def read_cache(api_id, kind):
    if not api_id:
        return None
    data = cache.get(f"detail:{api_id}:{kind}")
    return (data or {}).get("data") or None


def trim_incidents(data):
    if data is None:
        return None
    out = []
    for i in data.get("incidents") or []:
        out.append({
            "incidentType": i.get("incidentType"),
            "incidentClass": i.get("incidentClass"),
            "time": i.get("time"),
            "addedTime": i.get("addedTime"),
            "isHome": i.get("isHome"),
            "homeScore": i.get("homeScore"),
            "awayScore": i.get("awayScore"),
            "text": i.get("text"),
            "player": (i.get("player") or {}).get("name"),
        })
    return out


def trim_stats(data):
    for s in (data or {}).get("statistics") or []:
        if s.get("period") == "ALL":
            return [
                {
                    "group": g.get("groupName"),
                    "items": [
                        {"key": it.get("key"), "name": it.get("name"),
                         "home": it.get("home"), "away": it.get("away")}
                        for it in g.get("statisticsItems") or []
                    ],
                }
                for g in s.get("groups") or []
            ]
    return None


def trim_lineups(data):
    if not data or not data.get("confirmed"):
        return None

    def side(s):
        s = s or {}
        players = []
        for p in s.get("players") or []:
            pl = p.get("player") or {}
            players.append({
                "name": pl.get("name"),
                "number": p.get("shirtNumber"),
                "position": p.get("position"),
                "substitute": bool(p.get("substitute")),
            })
        return {"formation": s.get("formation"), "players": players}

    return {"confirmed": True, "home": side(data.get("home")), "away": side(data.get("away"))}

@router.get("")
def list_matches(competition: str | None = None, db: Session = Depends(get_db)):
    if competition and competition not in VALID_COMPETITIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen turnuva")

    q = match_query(db)
    if competition:
        q = q.filter(models.Match.competition == competition)

    q = q.order_by(models.Match.match_date.is_(None), models.Match.match_date)
    return [serialize_match(m) for m in q.all()]


@router.get("/upcoming")
def upcoming_matches(limit: int = 3, db: Session = Depends(get_db)):
    q = (
        match_query(db)
        .filter(models.Match.status.in_(["live", "scheduled"]))
        .filter(models.Match.match_date.is_not(None))
        .order_by(
            models.Match.status != "live",
            models.Match.match_date,
            models.Match.kickoff_time,
        )
        .limit(limit)
    )
    return [serialize_match(m, with_absences=True) for m in q.all()]


@router.get("/{match_id}/detail")
def match_detail(match_id: int, db: Session = Depends(get_db)):
    m = match_query(db).filter(models.Match.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    return {
        "match": serialize_match(m),
        "incidents": trim_incidents(read_cache(m.api_id, "incidents")),
        "statistics": trim_stats(read_cache(m.api_id, "statistics")),
        "lineups": trim_lineups(read_cache(m.api_id, "lineups")),
    }


@router.get("/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = match_query(db).filter(models.Match.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    return serialize_match(m, with_absences=True)