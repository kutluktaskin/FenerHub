"""Maç sonu özeti: graph / shotmap / best-players çekimi ve API'ye dönüşü."""
from datetime import datetime, timedelta

import pytest

from app import auto_sync, cache, models, sync
from app.database import SessionLocal
from app.routers import matches

API_ID = 99000555
KINDS = ("graph", "shotmap", "best-players", "summary_done")


@pytest.fixture
def finished_match():
    """3 saat önce başlamış, bitmiş bir maç."""
    ko = datetime.now(sync.TR_TZ) - timedelta(hours=3)
    with SessionLocal() as db, db.begin():
        home, away = models.Team(name="Özet Ev"), models.Team(name="Özet Dep")
        db.add_all([home, away])
        db.flush()
        m = models.Match(competition="uefa", home_team_id=home.id, away_team_id=away.id, status="finished",
                         match_date=ko.date(), kickoff_time=ko.time().replace(microsecond=0),
                         home_score=2, away_score=2, api_id=API_ID)
        db.add(m)
        db.flush()
        ids = {"id": m.id, "teams": [home.id, away.id]}
    yield ids
    with SessionLocal() as db, db.begin():
        db.query(models.Match).filter_by(id=ids["id"]).delete()
        db.query(models.Team).filter(models.Team.id.in_(ids["teams"])).delete(synchronize_session=False)
    for k in KINDS:
        cache.delete(f"detail:{API_ID}:{k}")


GRAPH = {"data": {"graphPoints": [{"minute": 1, "value": 8}, {"minute": 45.5, "value": -23}], "periodTime": 45}}
SHOTS = {"data": {"shotmap": [
    {"playerCoordinates": {"x": 11.5, "y": 48}, "xg": 0.4123, "shotType": "goal", "isHome": True,
     "player": {"name": "Golcü"}, "time": 4, "situation": "assisted", "bodyPart": "right-foot"},
    {"playerCoordinates": {}, "xg": 0.1, "shotType": "miss", "isHome": False},           # konumsuz: atlanır
]}}
BEST = {"data": {"bestHomeTeamPlayer": {"value": "8.0", "player": {"name": "Ev Yıldız", "position": "M"}, "team": {"name": "Özet Ev"}},
                 "bestAwayTeamPlayer": {"value": "7.4", "player": {"name": "Dep Yıldız"}, "team": {"name": "Özet Dep"}},
                 "leaderboard": [{"value": "8.0", "player": {"name": "Ev Yıldız"}, "team": {"name": "Özet Ev"}}]}}


def test_trims():
    g = matches.trim_graph(GRAPH["data"])
    assert g == {"points": [[1, 8], [45.5, -23]], "periodTime": 45}
    s = matches.trim_shotmap(SHOTS["data"])
    assert len(s) == 1 and s[0]["xg"] == 0.412 and s[0]["type"] == "goal" and s[0]["player"] == "Golcü"
    b = matches.trim_best(BEST["data"])
    assert b["home"]["name"] == "Ev Yıldız" and b["away"]["rating"] == "7.4" and len(b["top"]) == 1
    assert matches.trim_graph({}) is None and matches.trim_shotmap(None) is None and matches.trim_best(None) is None


def test_summary_targets_window(finished_match):
    now = datetime.now(sync.TR_TZ)
    assert API_ID in auto_sync.summary_targets(now)
    assert API_ID not in auto_sync.summary_targets(now - timedelta(hours=1))   # henüz 2 sa 15 dk olmadı
    assert API_ID not in auto_sync.summary_targets(now + timedelta(days=3))    # 2 günden eski
    cache.put(f"detail:{API_ID}:summary_done", True)
    assert API_ID not in auto_sync.summary_targets(now)                         # bir kez çekilir


def test_fetch_summary_once_and_budget(finished_match, monkeypatch):
    calls = []
    data = {"graph": GRAPH, "shotmap": SHOTS, "best-players": BEST}

    def fake_get(path):
        calls.append(path)
        return data[path.rsplit("/", 1)[1]]
    monkeypatch.setattr(sync, "api_get", fake_get)

    monkeypatch.setattr(sync, "quota_remaining", auto_sync.SUMMARY_MIN_QUOTA - 1)   # bütçe dolu
    auto_sync.fetch_summary(API_ID)
    assert calls == [] and not cache.get(f"detail:{API_ID}:summary_done")

    monkeypatch.setattr(sync, "quota_remaining", 80)
    auto_sync.fetch_summary(API_ID)
    assert len(calls) == 3 and cache.get(f"detail:{API_ID}:summary_done") is True

    with SessionLocal() as db:
        detail = matches.match_detail(finished_match["id"], db)
        listed = [m for m in matches.list_matches(None, db) if m["api_id"] == API_ID][0]
    assert detail["summary"]["graph"]["points"][0] == [1, 8]
    assert detail["summary"]["shotmap"][0]["player"] == "Golcü"
    assert detail["summary"]["best"]["home"]["name"] == "Ev Yıldız"
    assert listed["has_summary"] is True
