"""Skor tahmin oyunu, istatistik modeli ve maçın oyuncusu oylaması."""
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import cache, model, models, predictions, sync
from app.database import SessionLocal

API_ID = 99000999


def req(ip="88.1.1.1"):
    return Request({"type": "http", "method": "POST", "path": "/", "client": ("10.0.0.5", 1),
                    "headers": [(b"x-forwarded-for", ip.encode())]})


@pytest.fixture
def game(monkeypatch):
    """Fenerbahçe - Tahmin Rakip, 2 gün sonra. Tablo ve önbellek sahte."""
    predictions._ip_log.clear()
    ko = datetime.now(sync.TR_TZ) + timedelta(days=2)
    with SessionLocal() as db, db.begin():
        fb = db.query(models.Team).filter_by(name="Fenerbahçe").first()
        if not fb:
            fb = models.Team(name="Fenerbahçe")
            db.add(fb)
        rival = models.Team(name="Tahmin Rakip")
        db.add(rival)
        db.flush()
        m = models.Match(competition="super_lig", home_team_id=fb.id, away_team_id=rival.id, status="scheduled",
                         match_date=ko.date(), kickoff_time=ko.time().replace(microsecond=0), api_id=API_ID)
        db.add(m)
        db.flush()
        ids = {"id": m.id, "rival": rival.id}
    yield ids
    with SessionLocal() as db, db.begin():
        db.query(models.Prediction).filter_by(match_id=ids["id"]).delete()
        db.query(models.MotmVote).filter_by(match_id=ids["id"]).delete()
        db.query(models.Match).filter_by(id=ids["id"]).delete()
        db.query(models.Team).filter_by(id=ids["rival"]).delete()
    for k in ("lineups", "incidents", "best-players"):
        cache.delete(f"detail:{API_ID}:{k}")


def send(match_id, owner, home, away, nick="tahminci", ip="88.1.1.1"):
    data = predictions.PredictIn(match_id=match_id, owner=owner, nick=nick, home=home, away=away)
    return asyncio.run(predictions.predict(data, req(ip)))


def set_match(match_id, **fields):
    with SessionLocal() as db, db.begin():
        m = db.get(models.Match, match_id)
        for k, v in fields.items():
            setattr(m, k, v)


@pytest.mark.parametrize("pred,real,pts", [
    ((2, 1), (2, 1), 5), ((3, 2), (2, 1), 3), ((1, 1), (2, 2), 3), ((3, 0), (2, 1), 1),
    ((0, 1), (1, 3), 1), ((1, 0), (0, 0), 0), ((0, 2), (1, 0), 0),
])
def test_points(pred, real, pts):
    assert predictions.points_for(*pred, *real) == pts


def test_model_probabilities():
    rows = [{"team": "Güçlü", "played": 8, "goals_for": 24, "goals_against": 4},
            {"team": "Zayıf", "played": 8, "goals_for": 5, "goals_against": 20}]
    p = model.predict(rows, "Güçlü", "Zayıf")
    assert abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1) < 0.01
    assert p["p_home"] > 0.6 and p["home"] > p["away"]
    q = model.predict([], "A", "B")                         # tablo yoksa iki takım eşit (saha avantajı)
    assert q["p_home"] > q["p_away"]


def test_predict_change_and_lock(game):
    r = send(game["id"], "sahip-aaaa-1", 2, 1)
    assert r["ok"] and r["crowd"]["count"] == 1 and r["crowd"]["home"] == 1.0
    send(game["id"], "sahip-aaaa-1", 1, 1)                  # başlamadan değiştirilebilir
    with SessionLocal() as db:
        rows = db.query(models.Prediction).filter_by(match_id=game["id"]).all()
    mine = [p for p in rows if p.player != predictions.MODEL]
    assert len(mine) == 1 and (mine[0].home, mine[0].away) == (1, 1)
    assert any(p.player == predictions.MODEL for p in rows)   # model tahmini de bırakıldı
    assert len(mine[0].player) == 64 and "sahip" not in mine[0].player   # anahtar saklanmaz

    set_match(game["id"], match_date=(datetime.now(sync.TR_TZ) - timedelta(minutes=5)).date(),
              kickoff_time=(datetime.now(sync.TR_TZ) - timedelta(minutes=5)).time().replace(microsecond=0))
    with pytest.raises(HTTPException) as e:
        send(game["id"], "sahip-aaaa-1", 3, 0)
    assert e.value.status_code == 409                       # başladı: kilitli


def test_bad_nick_and_rate_limit(game, monkeypatch):
    with pytest.raises(HTTPException) as e:
        send(game["id"], "sahip-bbbb-1", 1, 0, nick="siktir")
    assert e.value.status_code == 400
    monkeypatch.setattr(predictions, "PREDICTIONS_PER_HOUR", 2)
    predictions._ip_log.clear()
    send(game["id"], "sahip-bbbb-2", 1, 0, ip="88.2.2.2")
    send(game["id"], "sahip-bbbb-3", 1, 0, ip="88.2.2.2")
    with pytest.raises(HTTPException) as e:
        send(game["id"], "sahip-bbbb-4", 1, 0, ip="88.2.2.2")
    assert e.value.status_code == 429


def test_settle_and_leaderboard(game):
    send(game["id"], "sahip-cccc-1", 2, 1, nick="Tamskor")
    send(game["id"], "sahip-cccc-2", 3, 2, nick="Farkci", ip="88.3.3.3")
    send(game["id"], "sahip-cccc-3", 0, 2, nick="Bilemedi", ip="88.3.3.4")
    yesterday = datetime.now(sync.TR_TZ) - timedelta(days=1)
    set_match(game["id"], status="finished", home_score=2, away_score=1,
              match_date=yesterday.date(), kickoff_time=yesterday.time().replace(microsecond=0))
    assert predictions.settle() >= 4                        # 3 taraftar + model

    board = predictions.leaderboard("season", owner="sahip-cccc-2")
    top = {r["nick"]: r for r in board["top"]}
    assert top["Tamskor"]["points"] == 5 and top["Tamskor"]["exact"] == 1 and top["Tamskor"]["rank"] == 1
    assert top["Farkci"]["points"] == 3 and top["Bilemedi"]["points"] == 0
    assert board["me"]["nick"] == "Farkci" and board["me"]["me"] is True
    assert board["model"]["nick"] == predictions.MODEL_NICK
    assert "player" not in board["top"][0]                  # kimlik özeti dışarı verilmez
    assert predictions.leaderboard("week")["fans"]["count"] >= 3     # dün oynandı: haftalıkta da var


def test_motm_vote(game):
    cache.put(f"detail:{API_ID}:lineups", {"data": {"home": {"players": [
        {"player": {"name": "Kaleci"}, "substitute": False},
        {"player": {"name": "Golcü"}, "substitute": False},
        {"player": {"name": "Yedek Oynamadı"}, "substitute": True}]}, "away": {"players": []}}})
    cache.put(f"detail:{API_ID}:incidents", {"data": {"incidents": [
        {"incidentType": "substitution", "isHome": True, "playerIn": {"name": "Giren"}, "playerOut": {"name": "Golcü"}}]}})
    cache.put(f"detail:{API_ID}:best-players", {"data": {"leaderboard": [
        {"value": "8.1", "player": {"name": "Golcü"}, "team": {"name": "Fenerbahçe"}}],
        "bestHomeTeamPlayer": {"value": "8.1", "player": {"name": "Golcü"}, "team": {"name": "Fenerbahçe"}}}})
    assert predictions.motm()["open"] is False              # maç henüz bitmedi

    ko = datetime.now(sync.TR_TZ) - timedelta(hours=3)
    set_match(game["id"], status="finished", home_score=1, away_score=0,
              match_date=ko.date(), kickoff_time=ko.time().replace(microsecond=0))
    info = predictions.motm(owner="oy-sahibi-1")
    assert info["open"] and [c["name"] for c in info["candidates"]] == ["Kaleci", "Golcü", "Giren"]
    assert info["api_best"] == "Golcü"

    def vote(choice, owner, ip="88.4.4.4"):
        return asyncio.run(predictions.vote(predictions.MotmIn(match_id=game["id"], owner=owner, choice=choice), req(ip)))
    assert vote("Golcü", "oy-sahibi-1")["ok"]
    with pytest.raises(HTTPException) as e:
        vote("Kaleci", "oy-sahibi-1")
    assert e.value.status_code == 409                       # kişi başı bir oy
    with pytest.raises(HTTPException) as e:
        vote("Yedek Oynamadı", "oy-sahibi-2")
    assert e.value.status_code == 400                       # oynamayan oyuncu seçilemez
    info = predictions.motm(owner="oy-sahibi-1")
    golcu = [c for c in info["candidates"] if c["name"] == "Golcü"][0]
    assert info["mine"] == "Golcü" and golcu["votes"] == 1 and golcu["rating"] == "8.1"

    late = datetime.now(sync.TR_TZ) - timedelta(hours=30)
    set_match(game["id"], match_date=late.date(), kickoff_time=late.time().replace(microsecond=0))
    assert predictions.motm()["open"] is False              # 24 saat doldu
