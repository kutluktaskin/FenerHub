"""Maçlar: GET /api/matches, /upcoming, /{id}, /{id}/detail (detay önbellekten, istek atmaz)."""
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
        "source": a.source,        # api | manual
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
        from ..sync import ALIASES   # API adı -> veritabanındaki ad
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
        "matchday": m.matchday,
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
            # Simülasyon için: değişiklikte giren/çıkan, golde asist (yoksa None)
            "playerIn": (i.get("playerIn") or {}).get("name"),
            "playerOut": (i.get("playerOut") or {}).get("name"),
            "assist": (i.get("assist1") or {}).get("name"),
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


# ---------- Maç sonu özeti (graph / shotmap / best-players; auto_sync maç bitince bir kez çeker) ----------
SUMMARY_KINDS = ("graph", "shotmap", "best-players")


def trim_graph(data):
    """Baskı grafiği: [[dakika, değer], ...]; değer > 0 ev sahibi, < 0 deplasman baskısı."""
    points = (data or {}).get("graphPoints") or []
    if not points:
        return None
    return {"points": [[p.get("minute"), p.get("value")] for p in points],
            "periodTime": data.get("periodTime") or 45}


def trim_shotmap(data):
    """Şutlar: x = kaleye uzaklık (saha boyunun %'si), y = yan konum (0-100), xg, sonuç."""
    shots = (data or {}).get("shotmap") or []
    if not shots:
        return None
    out = []
    for s in shots:
        c = s.get("playerCoordinates") or {}
        if c.get("x") is None or c.get("y") is None:
            continue
        out.append({
            "x": c["x"], "y": c["y"], "xg": round(s.get("xg") or 0, 3),
            "type": s.get("shotType"),            # goal | save | miss | block | post
            "isHome": s.get("isHome"),
            "player": (s.get("player") or {}).get("name"),
            "time": s.get("time"), "addedTime": s.get("addedTime"),
            "situation": s.get("situation"), "bodyPart": s.get("bodyPart"),
        })
    return out or None


def trim_best(data):
    """En iyi oyuncular: maçın ilk 5'i ve iki takımın en iyisi (puan)."""
    if not data:
        return None
    def row(e):
        if not e:
            return None
        return {"name": (e.get("player") or {}).get("name"), "position": (e.get("player") or {}).get("position"),
                "team": (e.get("team") or {}).get("name"), "rating": e.get("value")}
    top = [row(e) for e in (data.get("leaderboard") or [])[:5]]
    best = {"home": row(data.get("bestHomeTeamPlayer")), "away": row(data.get("bestAwayTeamPlayer")), "top": top}
    return best if (best["home"] or best["away"] or top) else None


def read_summary(api_id):
    if not api_id:
        return None
    graph = trim_graph(read_cache(api_id, "graph"))
    shots = trim_shotmap(read_cache(api_id, "shotmap"))
    best = trim_best(read_cache(api_id, "best-players"))
    if not (graph or shots or best):
        return None
    return {"graph": graph, "shotmap": shots, "best": best}


def summary_ids(db) -> set:
    """Özeti önbellekte olan maçların api id'leri (tek sorgu; fikstürdeki "Maç özeti" düğmesi için)."""
    keys = db.query(models.ApiCache.key).filter(models.ApiCache.key.like("detail:%:best-players")).all()
    return {int(k.split(":")[1]) for (k,) in keys if k.split(":")[1].isdigit()}


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
    with_summary = summary_ids(db)
    return [{**serialize_match(m), "has_summary": m.api_id in with_summary} for m in q.all()]


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
        "summary": read_summary(m.api_id),
    }


@router.get("/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = match_query(db).filter(models.Match.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")
    return serialize_match(m, with_absences=True)