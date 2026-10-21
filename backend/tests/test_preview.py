"""Maç öncesi: h2h + pregame-form, Fenerbahçe açısından ve günde bir kez."""
from datetime import datetime, timedelta

import pytest

from app import auto_sync, cache, models, sync
from app.database import SessionLocal
from app.routers import matches

API_ID = 99000888
H2H = {"data": {"teamDuel": {"homeWins": 5, "awayWins": 2, "draws": 3}}}
FORM = {"data": {"homeTeam": {"form": ["W", "W", "L", "W", "W"], "position": 1},
                 "awayTeam": {"form": ["L", "D", "W", "W", "W"], "position": 3}}}


@pytest.fixture
def away_derby():
    """3 gün sonra deplasmanda bir maç (Fenerbahçe deplasman takımı)."""
    ko = datetime.now(sync.TR_TZ) + timedelta(days=3)
    with SessionLocal() as db, db.begin():
        fb = db.query(models.Team).filter_by(name="Fenerbahçe").first() or models.Team(name="Fenerbahçe")
        rival = models.Team(name="Önizleme Rakip")
        db.add_all([fb, rival])
        db.flush()
        m = models.Match(competition="super_lig", home_team_id=rival.id, away_team_id=fb.id, status="scheduled",
                         match_date=ko.date(), kickoff_time=ko.time().replace(microsecond=0), api_id=API_ID)
        db.add(m)
        db.flush()
        ids = {"id": m.id, "rival": rival.id}
    yield ids
    with SessionLocal() as db, db.begin():
        db.query(models.Match).filter_by(id=ids["id"]).delete()
        db.query(models.Team).filter_by(id=ids["rival"]).delete()
    for k in ("h2h", "pregame-form"):
        cache.delete(f"detail:{API_ID}:{k}")


def test_preview_from_fenerbahce_side(away_derby):
    cache.put(f"detail:{API_ID}:h2h", H2H)
    cache.put(f"detail:{API_ID}:pregame-form", FORM)
    with SessionLocal() as db:
        m = matches.match_query(db).filter(models.Match.id == away_derby["id"]).first()
        p = matches.read_preview(db, m)
    # Fenerbahçe deplasmanda: ev sahibinin galibiyetleri rakibin hanesine yazılır
    assert p["h2h"] == {"fb_wins": 2, "rival_wins": 5, "draws": 3}
    assert p["form"] == {"fb": ["L", "D", "W", "W", "W"], "rival": ["W", "W", "L", "W", "W"]}
    assert p["positions"] == {"fb": 3, "rival": 1}            # puan durumu yoksa API'nin sırası
    assert p["rival"] == "Önizleme Rakip"


def test_no_preview_without_data(away_derby):
    with SessionLocal() as db:
        m = matches.match_query(db).filter(models.Match.id == away_derby["id"]).first()
        assert matches.read_preview(db, m) is None


def test_preview_fetched_once_a_day(away_derby, monkeypatch):
    calls = []
    monkeypatch.setattr(auto_sync, "fetch_kind",
                        lambda a, k: calls.append((a, k)) or cache.put(f"detail:{a}:{k}", {"data": {}}))
    monkeypatch.setattr(auto_sync, "refresh_matches", lambda full: None)
    monkeypatch.setattr(auto_sync, "refresh_standings", lambda: None)
    monkeypatch.setattr(auto_sync, "summary_targets", lambda: [])
    monkeypatch.setattr(auto_sync.absences_sync, "apply_v6_injuries", lambda: None)
    monkeypatch.setattr(sync, "quota_remaining", 80)
    auto_sync.backoff.clear()
    auto_sync.reset()
    auto_sync.tick()
    assert (API_ID, "h2h") in calls and (API_ID, "pregame-form") in calls
    calls.clear()
    auto_sync.reset()
    auto_sync.tick()
    assert not [c for c in calls if c[0] == API_ID]           # aynı gün tekrar istenmez
