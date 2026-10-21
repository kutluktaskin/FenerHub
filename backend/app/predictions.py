"""Skor tahmin oyunu (12. Adam) ve maçın oyuncusu oylaması.

Kimlik: hesap yok. Tarayıcı forumdaki cihaz anahtarını (fhOwner) gönderir; sunucuda anahtarın
özeti (player) saklanır. İleride giriş eklenirse bu özet bir hesaba bağlanabilir.
Kurallar:
  - tahmin maç başlayana kadar değiştirilebilir, başlama saatinde kilitlenir (sunucu saati)
  - puan: tam skor 5, doğru gol farkı 3, doğru sonuç 1 (maç bitince settle() hesaplar)
  - istatistik modeli (app/model.py) "model" oyuncusu olarak her maça tahmin bırakır
  - IP başına saatte en fazla PREDICTIONS_PER_HOUR tahmin isteği
  - maçın oyuncusu: maç bitince (başlama + 2 sa) 24 saat açık, kişi başı bir oy;
    taraftar oyu ile SportsAPI puanı yan yana
"""
import hashlib
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from . import cache, model, models, sync
from .database import SessionLocal
from .net import client_ip
from .profanity import mask
from .routers.matches import match_query, read_cache, trim_best

router = APIRouter(tags=["tahmin"])

MODEL = "model"
MODEL_NICK = "İstatistik modeli"
OPEN_DAYS = 14                          # en fazla bu kadar gün sonraki maçlara tahmin
PREDICTIONS_PER_HOUR = 30
MOTM_OPEN_AFTER = timedelta(hours=2)    # başlamadan bu kadar sonra (maç bitmiş sayılır)
MOTM_HOURS = 24
LEADERBOARD_SIZE = 20
_ip_log: dict[str, list[float]] = {}


def player_key(owner: str) -> str:
    return hashlib.sha256(f"fenerhub-player:{owner}".encode()).hexdigest()


def kickoff(m: models.Match):
    if not (m.match_date and m.kickoff_time):
        return None
    return datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)


def points_for(ph: int, pa: int, h: int, a: int) -> int:
    """Tam skor 5, doğru gol farkı 3, doğru sonuç 1, yanlış 0."""
    if (ph, pa) == (h, a):
        return 5
    if ph - pa == h - a:
        return 3
    if (ph > pa) == (h > a) and (ph < pa) == (h < a):
        return 1
    return 0


def model_prediction(m: models.Match) -> dict:
    tables = cache.get("standings") or {}
    return model.predict(tables.get(m.competition) or [], m.home_team.name, m.away_team.name)


def store_model_prediction(db, m: models.Match) -> None:
    """Modelin tahmini, maç kilitlenmeden önce bir kez kaydedilir (sonradan değişmez)."""
    exists = db.query(models.Prediction.id).filter_by(match_id=m.id, player=MODEL).first()
    if exists:
        return
    p = model_prediction(m)
    db.add(models.Prediction(match_id=m.id, player=MODEL, nick=MODEL_NICK, home=p["home"], away=p["away"],
                             ts=int(time.time())))


def settle(now: datetime | None = None) -> int:
    """Biten maçların tahminlerini puanlar; yaklaşan (24 saat içinde) maçlara model tahmini bırakır.
    auto_sync her tam kontrolde çağırır; istek atmaz. Puanlanan tahmin sayısını döndürür."""
    now = now or datetime.now(sync.TR_TZ)
    scored = 0
    with SessionLocal() as db, db.begin():
        upcoming = match_query(db).filter(models.Match.status == "scheduled").all()
        for m in upcoming:
            ko = kickoff(m)
            if ko and now <= ko <= now + timedelta(hours=24):
                store_model_prediction(db, m)
        finished = (
            db.query(models.Match)
            .join(models.Prediction, models.Prediction.match_id == models.Match.id)
            .filter(models.Match.status == "finished", models.Prediction.points.is_(None),
                    models.Match.home_score.is_not(None))
            .distinct().all()
        )
        for m in finished:
            for p in db.query(models.Prediction).filter_by(match_id=m.id).filter(models.Prediction.points.is_(None)):
                p.points = points_for(p.home, p.away, m.home_score, m.away_score)
                scored += 1
    return scored


# ---------- İstekler ----------
class PredictIn(BaseModel):
    match_id: int
    owner: str = Field(min_length=8, max_length=64)
    nick: str = Field(min_length=2, max_length=20)
    home: int = Field(ge=0, le=20)
    away: int = Field(ge=0, le=20)


class MotmIn(BaseModel):
    match_id: int
    owner: str = Field(min_length=8, max_length=64)
    choice: str = Field(min_length=2, max_length=80)


def _rate_limit(request: Request) -> None:
    ip = client_ip(request)
    now = time.time()
    recent = [t for t in _ip_log.get(ip, []) if now - t < 3600]
    if len(recent) >= PREDICTIONS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Çok fazla istek; biraz sonra tekrar dene.")
    _ip_log[ip] = recent + [now]


def _crowd(db, match_id: int) -> dict:
    """Taraftar tahminlerinin dağılımı (model hariç): ev / beraberlik / deplasman yüzdesi."""
    rows = db.query(models.Prediction.home, models.Prediction.away).filter(
        models.Prediction.match_id == match_id, models.Prediction.player != MODEL).all()
    n = len(rows)
    if not n:
        return {"count": 0}
    h = sum(1 for a, b in rows if a > b)
    d = sum(1 for a, b in rows if a == b)
    return {"count": n, "home": round(h / n, 3), "draw": round(d / n, 3), "away": round((n - h - d) / n, 3)}


@router.get("/api/predict/open")
def open_matches(owner: str = ""):
    """Tahmine açık maçlar: başlamamış, en fazla 14 gün sonra. Benim tahminim, model ve dağılım."""
    now = datetime.now(sync.TR_TZ)
    me = player_key(owner) if owner else None
    out = []
    with SessionLocal() as db:
        rows = match_query(db).filter(models.Match.status == "scheduled").all()
        for m in sorted((m for m in rows if kickoff(m)), key=kickoff):
            ko = kickoff(m)
            if not (now < ko <= now + timedelta(days=OPEN_DAYS)):
                continue
            mine = db.query(models.Prediction).filter_by(match_id=m.id, player=me).first() if me else None
            out.append({
                "match_id": m.id, "home": m.home_team.name, "away": m.away_team.name,
                "competition": m.competition, "kickoff": ko.isoformat(),
                "mine": {"home": mine.home, "away": mine.away} if mine else None,
                "model": model_prediction(m), "crowd": _crowd(db, m.id),
            })
    return out


@router.post("/api/predict")
async def predict(data: PredictIn, request: Request):
    _rate_limit(request)
    nick = mask(data.nick)
    if len(nick) < 2 or "*" in nick:
        raise HTTPException(status_code=400, detail="Geçerli bir takma ad yaz.")
    who = player_key(data.owner)

    def save():
        with SessionLocal() as db, db.begin():
            m = match_query(db).filter(models.Match.id == data.match_id).first()
            if not m:
                raise HTTPException(status_code=404, detail="Maç yok")
            ko = kickoff(m)
            if m.status != "scheduled" or not ko or datetime.now(sync.TR_TZ) >= ko:
                raise HTTPException(status_code=409, detail="Maç başladı, tahminler kilitlendi.")
            store_model_prediction(db, m)
            p = db.query(models.Prediction).filter_by(match_id=m.id, player=who).first()
            if p:
                p.home, p.away, p.nick, p.ts = data.home, data.away, nick, int(time.time())
            else:
                db.add(models.Prediction(match_id=m.id, player=who, nick=nick, home=data.home,
                                         away=data.away, ts=int(time.time())))
            db.flush()
            return {"ok": True, "home": data.home, "away": data.away, "crowd": _crowd(db, m.id)}

    return await run_in_threadpool(save)


@router.get("/api/predict/leaderboard")
def leaderboard(scope: str = "season", owner: str = ""):
    """Puan tablosu: scope=season (sezon) ya da week (son 7 günün maçları). Model ayrı satırda."""
    if scope not in ("season", "week"):
        raise HTTPException(status_code=400, detail="scope: season | week")
    me = player_key(owner) if owner else None
    with SessionLocal() as db:
        q = (
            db.query(models.Prediction.player,
                     func.max(models.Prediction.nick),
                     func.sum(models.Prediction.points),
                     func.count(models.Prediction.id),
                     func.sum(case((models.Prediction.points == 5, 1), else_=0)))
            .join(models.Match, models.Match.id == models.Prediction.match_id)
            .filter(models.Prediction.points.is_not(None))
        )
        if scope == "week":
            since = (datetime.now(sync.TR_TZ) - timedelta(days=7)).date()
            q = q.filter(models.Match.match_date >= since)
        rows = q.group_by(models.Prediction.player).all()
    table = sorted(
        ({"player": p, "nick": n, "points": int(pts or 0), "played": c, "exact": int(ex or 0)} for p, n, pts, c, ex in rows),
        key=lambda r: (-r["points"], -r["exact"], r["nick"]),
    )
    model_row = next((r for r in table if r["player"] == MODEL), None)
    fans = [r for r in table if r["player"] != MODEL]
    for i, r in enumerate(fans, 1):
        r["rank"] = i
        r["me"] = r["player"] == me
    my_row = next((r for r in fans if r["me"]), None)
    clean = lambda r: {k: v for k, v in r.items() if k != "player"} if r else None
    avg = round(sum(r["points"] for r in fans) / len(fans), 1) if fans else None
    return {
        "scope": scope,
        "top": [clean(r) for r in fans[:LEADERBOARD_SIZE]],
        "me": clean(my_row),
        "model": clean(model_row),
        "fans": {"count": len(fans), "avg_points": avg, "best": fans[0]["points"] if fans else None},
    }


# ---------- Maçın oyuncusu ----------
def motm_match(db, now: datetime | None = None):
    """Oylamaya açık maç: bitmiş, başlamasından 2-26 saat geçmiş en yeni maç."""
    now = now or datetime.now(sync.TR_TZ)
    rows = match_query(db).filter(models.Match.status == "finished").all()
    open_ = [m for m in rows if kickoff(m) and kickoff(m) + MOTM_OPEN_AFTER <= now
             <= kickoff(m) + MOTM_OPEN_AFTER + timedelta(hours=MOTM_HOURS)]
    return max(open_, key=kickoff) if open_ else None


def motm_candidates(m: models.Match) -> list[str]:
    """Fenerbahçe'de oynayan oyuncular: ilk 11 + oyuna girenler (kadro ve olaylar önbellekten)."""
    lineups = read_cache(m.api_id, "lineups") or {}
    fb_home = m.home_team.name == "Fenerbahçe"
    side = (lineups.get("home") if fb_home else lineups.get("away")) or {}
    names = [(p.get("player") or {}).get("name") for p in side.get("players") or [] if not p.get("substitute")]
    for i in (read_cache(m.api_id, "incidents") or {}).get("incidents") or []:
        if i.get("incidentType") == "substitution" and i.get("isHome") == fb_home:
            names.append((i.get("playerIn") or {}).get("name"))
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _api_ratings(m: models.Match) -> dict:
    data = read_cache(m.api_id, "best-players") or {}
    out = {}
    for e in (data.get("leaderboard") or []):
        name = (e.get("player") or {}).get("name")
        if name:
            out[name] = e.get("value")
    return out


@router.get("/api/motm")
def motm(owner: str = ""):
    with SessionLocal() as db:
        m = motm_match(db)
        if not m:
            return {"open": False}
        candidates = motm_candidates(m)
        votes = dict(db.query(models.MotmVote.choice, func.count()).filter_by(match_id=m.id)
                     .group_by(models.MotmVote.choice).all())
        mine = None
        if owner:
            v = db.query(models.MotmVote).filter_by(match_id=m.id, player=player_key(owner)).first()
            mine = v.choice if v else None
        ko = kickoff(m)
    ratings = _api_ratings(m)
    total = sum(votes.values())
    best = trim_best(read_cache(m.api_id, "best-players")) or {}
    fb_best = (best.get("home") if m.home_team.name == "Fenerbahçe" else best.get("away")) or {}
    return {
        "open": True, "match_id": m.id, "home": m.home_team.name, "away": m.away_team.name,
        "score": [m.home_score, m.away_score],
        "closes": (ko + MOTM_OPEN_AFTER + timedelta(hours=MOTM_HOURS)).isoformat(),
        "total": total, "mine": mine, "api_best": fb_best.get("name"),
        "candidates": [{"name": n, "votes": votes.get(n, 0), "rating": ratings.get(n)} for n in candidates],
    }


@router.post("/api/motm")
async def vote(data: MotmIn, request: Request):
    _rate_limit(request)
    who = player_key(data.owner)

    def save():
        with SessionLocal() as db, db.begin():
            m = motm_match(db)
            if not m or m.id != data.match_id:
                raise HTTPException(status_code=409, detail="Bu maç için oylama kapalı.")
            if data.choice not in motm_candidates(m):
                raise HTTPException(status_code=400, detail="Bu oyuncu bu maçta oynamadı.")
            try:
                with db.begin_nested():
                    db.add(models.MotmVote(match_id=m.id, player=who, choice=data.choice, ts=int(time.time())))
            except IntegrityError:
                raise HTTPException(status_code=409, detail="Bu maç için zaten oy verdin.")
            return {"ok": True}

    return await run_in_threadpool(save)
