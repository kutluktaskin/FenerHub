"""Canlı maç modülü: önbellek, maç seçimi ve gelen mesajların işlenmesi (ağ bağlantısı yok)."""
import asyncio
import time
from datetime import datetime, timedelta

import pytest

from app import cache, live, models, sync
from app.database import SessionLocal

API_ID = 99000001
TR = sync.TR_TZ


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def match():
    """Yarım saat önce başlamış, bitmemiş bir Fenerbahçe maçı."""
    ko = datetime.now(TR) - timedelta(minutes=30)
    with SessionLocal() as db, db.begin():
        home = models.Team(name="Test FB")
        away = models.Team(name="Test Rakip")
        db.add_all([home, away])
        db.flush()
        m = models.Match(competition="uefa", home_team_id=home.id, away_team_id=away.id,
                         match_date=ko.date(), kickoff_time=ko.time().replace(microsecond=0),
                         status="scheduled", api_id=API_ID)
        db.add(m)
        db.flush()
        ids = {"id": m.id, "home": home.id, "away": away.id}
    yield ids
    with SessionLocal() as db, db.begin():
        db.query(models.Match).filter_by(id=ids["id"]).delete()
        db.query(models.Team).filter(models.Team.id.in_([ids["home"], ids["away"]])).delete()
    for kind in ("incidents", "statistics", "lineups", "done"):
        cache.delete(f"detail:{API_ID}:{kind}")
    live.state.clear()


def test_cache_put_get_age_delete():
    cache.put("test:x", {"a": [1, "ş"]})
    assert cache.get("test:x") == {"a": [1, "ş"]}
    assert cache.age("test:x") < 5
    cache.put("test:x", [2], fetched_at=0)          # 0 = süresi dolmuş
    assert cache.get("test:x") == [2] and cache.age("test:x") > 1e9
    cache.delete("test:x")
    assert cache.get("test:x") is None and cache.age("test:x") == float("inf")


def test_score_and_finish_helpers():
    inc = [
        {"incidentType": "period", "text": "FT", "homeScore": 2, "awayScore": 1, "time": 90, "addedTime": 999},
        {"incidentType": "goal", "homeScore": 2, "awayScore": 1, "time": 88},
        {"incidentType": "card", "time": 70},
        {"incidentType": "goal", "homeScore": 1, "awayScore": 1, "time": 40},
    ]
    assert live.score_from(inc) == (2, 1)
    assert live.is_finished(inc)
    assert not live.is_finished(inc[1:])
    assert live.score_from([]) is None


def test_merge_incidents_full_list_and_single():
    full = {"incidents": [{"id": 1, "incidentType": "card"}]}
    assert live.merge_incidents(None, full) is full
    merged = live.merge_incidents(full, {"id": 2, "incidentType": "goal"})
    assert [i["id"] for i in merged["incidents"]] == [2, 1]
    again = live.merge_incidents(merged, {"id": 2, "incidentType": "goal", "time": 5})
    assert [i["id"] for i in again["incidents"]] == [2, 1] and again["incidents"][0]["time"] == 5
    assert live.merge_incidents(full, {"foo": 1}) is full


def test_pick_match_window(match):
    now = datetime.now(TR)
    assert live.pick_match(now)["api_id"] == API_ID
    assert live.pick_match(now - timedelta(hours=2)) is None or \
        live.pick_match(now - timedelta(hours=2))["api_id"] != API_ID      # 15 dk'dan erken
    assert live.pick_match(now + timedelta(hours=5)) is None or \
        live.pick_match(now + timedelta(hours=5))["api_id"] != API_ID      # 4 saat geçti
    cache.put(f"detail:{API_ID}:done", True)
    assert (live.pick_match(now) or {}).get("api_id") != API_ID           # bitmiş sayılır


class Recorder:
    def __init__(self):
        self.sent = []

    async def broadcast(self, data):
        self.sent.append(data)


def test_follower_handles_ws_messages(match, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(live, "hub", rec)
    f = live.Follower(live.pick_match())
    run(f.start())
    assert rec.sent[-1]["type"] == "state" and live.state["match"]["home"] == "Test FB"

    def msg(suffix, data, kind="update"):
        return {"channel": f"match:{API_ID}{suffix}", "type": kind, "data": data}

    # başka maç ve abonelik mesajları yok sayılır
    run(f.handle({"type": "subscribed", "channel": f"match:{API_ID}"}))
    run(f.handle({"channel": f"match:{API_ID}0:incidents", "type": "update", "data": {"incidents": []}}))
    # maç öncesi istatistik 404'ü yok sayılır
    run(f.handle(msg(":stats", {"error": {"code": 404}}, "snapshot")))
    assert live.state["statistics"] is None

    goal = {"id": 7, "incidentType": "goal", "incidentClass": "regular", "time": 12, "isHome": True,
            "homeScore": 1, "awayScore": 0, "player": {"name": "Golcü"}}
    run(f.handle(msg(":incidents", {"incidents": []}, "snapshot")))
    run(f.handle(msg(":incidents", {"incidents": [goal]})))
    types = [m["type"] for m in rec.sent]
    assert "goal" not in types                       # ilk skor (önceki skor bilinmiyor) gol bildirimi değil
    assert live.state["match"]["home_score"] == 1 and live.state["match"]["status"] == "live"

    goal2 = dict(goal, id=8, time=50, homeScore=2)
    run(f.handle(msg(":incidents", {"incidents": [goal2, goal]})))
    goal_msg = [m for m in rec.sent if m["type"] == "goal"][-1]
    assert goal_msg["score"] == (2, 0) and goal_msg["incident"]["player"] == "Golcü"
    # önbelleğe REST ile aynı biçimde yazıldı
    assert cache.get(f"detail:{API_ID}:incidents")["data"]["incidents"][0]["id"] == 8

    stats = {"statistics": [{"period": "ALL", "groups": [{"groupName": "Match overview", "statisticsItems": [
        {"key": "ballPossession", "name": "Ball possession", "home": "60%", "away": "40%"}]}]}]}
    run(f.handle(msg(":stats", stats)))
    assert live.state["statistics"][0]["items"][0]["home"] == "60%"

    ft = {"incidentType": "period", "text": "FT", "homeScore": 2, "awayScore": 0, "time": 90, "addedTime": 999}
    run(f.handle(msg(":incidents", {"incidents": [ft, goal2, goal]})))
    assert f.ft_at is not None and cache.get(f"detail:{API_ID}:done") is True
    assert live.state["match"]["status"] == "finished"
    f.ft_at = time.time() - live.AFTER_FT - 1
    assert f.done()


def test_follower_score_status_event(match, monkeypatch):
    monkeypatch.setattr(live, "hub", Recorder())
    f = live.Follower(live.pick_match())
    run(f.start())
    run(f.handle({"channel": f"match:{API_ID}", "type": "update", "data": {
        "status": {"type": "inprogress", "code": 7}, "homeScore": {"current": 0},
        "awayScore": {"current": 1}, "time": {"currentPeriodStartTimestamp": 1700000000, "initial": 2700}}}))
    m = live.state["match"]
    assert (m["home_score"], m["away_score"], m["status"], m["status_code"]) == (0, 1, "live", 7)
    assert m["period_start"] == 1700000000 and m["period_initial"] == 2700


def test_rest_budget(monkeypatch):
    f = live.Follower({"id": 0, "api_id": 1, "kickoff": time.time()})
    for q, expected in ((None, 60), (90, 60), (50, 300), (40, None), (5, None)):
        monkeypatch.setattr(sync, "quota_remaining", q)
        assert f.rest_interval() == expected


def test_live_rest_endpoint_idle():
    live.state.clear()
    assert live.live_state() == {"type": "idle"}
    live.state.update({"source": "ws", "match_id": 1})
    assert live.live_state() == {"type": "state", "source": "ws", "match_id": 1}
    live.state.clear()


def test_auto_sync_skips_rest_while_ws_covers(match, monkeypatch):
    """Canlı WS maçı izlerken auto_sync o maç için olay/istatistik/kadro isteği atmaz."""
    from app import auto_sync
    calls = []
    monkeypatch.setattr(auto_sync, "fetch_kind", lambda a, k: calls.append((a, k)) or {})
    monkeypatch.setattr(auto_sync, "refresh_matches", lambda full: None)
    monkeypatch.setattr(auto_sync, "refresh_standings", lambda: None)
    auto_sync.backoff.clear()

    auto_sync.tick()
    assert (API_ID, "incidents") in calls          # izlenmiyorken REST çalışır
    calls.clear()
    cache.delete(f"detail:{API_ID}:incidents")
    cache.delete(f"detail:{API_ID}:statistics")
    live.covered.add(API_ID)
    try:
        auto_sync.tick()
    finally:
        live.covered.discard(API_ID)
    assert not [c for c in calls if c[0] == API_ID]
