"""Maç günü eksikleri ve genel sakatlık raporu: missingPlayers'tan otomatik güncelleme."""
from datetime import date

import pytest

from app import absences_sync, auto_sync, models
from app.database import SessionLocal

API_ID = 99000077


@pytest.fixture
def world():
    """Fenerbahçe (ev sahibi), rakip, bir maç ve üç oyuncu."""
    with SessionLocal() as db, db.begin():
        fb = db.query(models.Team).filter_by(name="Fenerbahçe").first()
        if not fb:
            fb = models.Team(name="Fenerbahçe")
            db.add(fb)
            db.flush()
        rival = models.Team(name="Test Rakip FC")
        db.add(rival)
        db.flush()
        m = models.Match(competition="super_lig", home_team_id=fb.id, away_team_id=rival.id,
                         status="scheduled", api_id=API_ID)
        players = [models.Player(name=n, team_id=fb.id) for n in ("Test Diz", "Test Ceza", "Test Elle")]
        db.add_all([m, *players])
        db.flush()
        ids = {"match": m.id, "fb": fb.id, "rival": rival.id, **{p.name: p.id for p in players}}
        # Elle girilmiş kayıt: otomatik güncelleme dokunmamalı
        db.add(models.Absence(player_id=ids["Test Elle"], match_id=m.id, type="injury",
                              reason="Elle not", source="manual"))
    yield ids
    with SessionLocal() as db, db.begin():
        pids = [ids["Test Diz"], ids["Test Ceza"], ids["Test Elle"]]
        db.query(models.Absence).filter(models.Absence.player_id.in_(pids)).delete(synchronize_session=False)
        db.query(models.Player).filter(models.Player.id.in_(pids)).delete(synchronize_session=False)
        db.query(models.Match).filter_by(id=ids["match"]).delete()
        db.query(models.Team).filter_by(id=ids["rival"]).delete()


def missing(name, desc, kind="missing", end="2099-12-10T00:00:00+00:00"):
    return {"player": {"name": name}, "type": kind, "description": desc, "expectedEndDate": end}


def lineups(items):
    return {"confirmed": False, "home": {"missingPlayers": items}, "away": {"missingPlayers": [
        missing("Rakip Oyuncu", "Knee Injury")]}}


def rows(match_id):
    with SessionLocal() as db:
        q = db.query(models.Absence).join(models.Player)
        q = q.filter(models.Absence.match_id.is_(None) if match_id is None else models.Absence.match_id == match_id)
        return {(a.player.name, a.type, a.reason, a.return_note, a.source) for a in q
                if a.player.name.startswith("Test ")}


def test_parse_and_translate():
    assert absences_sync.reason_tr("Knee Injury") == "Diz sakatlığı"
    assert absences_sync.reason_tr("Some New Problem") == "Some New Problem"
    assert absences_sync.parse_missing(missing("X", "Red card"))["type"] == "suspension"
    assert absences_sync.parse_missing(missing("X", "Muscle Injury", "doubtful"))["reason"] == "Şüpheli · Kas sakatlığı"
    today = date(2026, 10, 20)
    assert absences_sync.return_note("2026-12-10T00:00:00+00:00", today) == "10 Aralık"
    assert absences_sync.return_note("2027-03-01T00:00:00+00:00", today) == "1 Mart 2027"
    assert absences_sync.return_note("2026-01-01T00:00:00+00:00", today) == "Belirsiz"


def test_match_and_general_report(world):
    absences_sync.apply_lineups(API_ID, lineups([
        missing("Test Diz", "Knee Injury"),
        missing("Tést Ceza", "Yellow card suspension"),     # aksan farkı eşleşir
        missing("Test Elle", "Ankle Injury"),               # elle kaydı var: atlanır
        missing("Kadroda Yok", "Illness"),                   # loglanır, eklenmez
    ]))
    match = rows(world["match"])
    assert ("Test Diz", "injury", "Diz sakatlığı", "10 Aralık 2099", "api") in match
    assert ("Test Ceza", "suspension", "Sarı kart cezası", "10 Aralık 2099", "api") in match
    assert ("Test Elle", "injury", "Elle not", None, "manual") in match      # elle kayıt aynen kaldı
    assert len(match) == 3
    general = rows(None)
    assert {r[0] for r in general} == {"Test Diz", "Test Ceza", "Test Elle"}


def test_recovered_player_is_removed_manual_kept(world):
    absences_sync.apply_lineups(API_ID, lineups([missing("Test Diz", "Knee Injury")]))
    assert {r[0] for r in rows(world["match"])} == {"Test Diz", "Test Elle"}
    absences_sync.apply_lineups(API_ID, lineups([]))        # oyuncu iyileşti
    assert {r[0] for r in rows(world["match"])} == {"Test Elle"}
    assert not {r[0] for r in rows(None)} & {"Test Diz"}


def test_bad_payload_is_ignored(world):
    absences_sync.apply_lineups(API_ID, None)
    absences_sync.apply_lineups(API_ID, {"error": {"code": 404}})
    absences_sync.apply_lineups(12345, lineups([missing("Test Diz", "Knee Injury")]))   # bilinmeyen maç
    assert {r[0] for r in rows(world["match"])} == {"Test Elle"}


def test_lineups_schedule():
    assert auto_sync.lineups_every(-25 * 60) is None          # 24 saatten önce sorgulanmaz
    assert auto_sync.lineups_every(-10 * 60) == 3 * 3600      # son 24 saatte 3 saatte bir
    assert auto_sync.lineups_every(-90) == 1800               # son 2 saatte 30 dakikada bir
    assert auto_sync.lineups_every(10) is None                # maç başladı: WS ya da durur


V6_INJURIES = {"success": True, "injuries": [
    {"player": {"id": "v6diz", "name": ""}, "type": 1, "reason": "Knee injury", "endTime": 0},
    {"player": {"id": "v6aşil", "name": ""}, "type": 1, "reason": "Achilles tendon problems",
     "endTime": 4102444800},                                          # 1 Ocak 2100
    {"player": {"id": "v6yok", "name": ""}, "type": 1, "reason": "Illness", "endTime": 0},
]}
V6_NAMES = {"v6diz": "Test Diz", "v6aşil": "Test Ceza", "v6yok": "Kadroda Olmayan"}


def fake_v6(calls):
    def api_get(path, base=None):
        calls.append(path)
        if path.endswith("/injuries"):
            return V6_INJURIES
        return {"player": {"name": V6_NAMES[path.rsplit("/", 1)[1]]}}
    return api_get


def test_v6_injuries_merge_and_name_cache(world, monkeypatch):
    from app import cache, sync
    for k in ("absences:lineups", "absences:v6", *[f"v6player:{p}" for p in V6_NAMES]):
        cache.delete(k)
    calls = []
    monkeypatch.setattr(sync, "api_get", fake_v6(calls))

    # Kadro verisinde Test Diz var (dönüş tarihiyle): iki kaynakta da olunca kadro verisi kazanır
    absences_sync.apply_lineups(API_ID, lineups([missing("Test Diz", "Knee Injury")]))
    absences_sync.apply_v6_injuries()
    general = {r[0]: r for r in rows(None)}
    assert general["Test Diz"][3] == "10 Aralık 2099"                 # kadro verisinden
    assert general["Test Ceza"][2:] == ("Aşil tendonu sorunu", "1 Ocak 2100", "api")   # V6'dan
    assert len(calls) == 4                                             # liste + 3 yeni oyuncu adı

    calls.clear()
    absences_sync.apply_v6_injuries()
    assert calls == ["/team/59gklziew2a17xd/injuries"]                 # adlar artık önbellekten

    # Oyuncu iyileşti: V6 listesinden çıktı, kadro verisinde de yok -> rapordan düşer
    monkeypatch.setattr(absences_sync, "V6_NEW_PLAYERS_MAX", 0)
    V6_INJURIES_SAVED = list(V6_INJURIES["injuries"])
    V6_INJURIES["injuries"] = V6_INJURIES_SAVED[:1]
    try:
        absences_sync.apply_lineups(API_ID, lineups([]))
        absences_sync.apply_v6_injuries()
        assert {r[0] for r in rows(None)} == {"Test Diz"}
    finally:
        V6_INJURIES["injuries"] = V6_INJURIES_SAVED


def test_v6_new_player_limit(world, monkeypatch):
    from app import cache, sync
    for k in ("absences:lineups", "absences:v6", *[f"v6player:{p}" for p in V6_NAMES]):
        cache.delete(k)
    calls = []
    monkeypatch.setattr(sync, "api_get", fake_v6(calls))
    monkeypatch.setattr(absences_sync, "V6_NEW_PLAYERS_MAX", 1)
    absences_sync.apply_v6_injuries()
    assert len(calls) == 2                       # liste + sadece 1 yeni oyuncu (kota)
    absences_sync.apply_v6_injuries()
    assert len(calls) == 4                       # sonraki çalışmada bir yeni oyuncu daha


def test_merge_general_precedence():
    a = [{"name": "Tést Kişi", "reason": "kadro"}]
    b = [{"name": "Test Kişi", "reason": "v6"}, {"name": "Başka", "reason": "v6"}]
    assert [i["reason"] for i in absences_sync.merge_general(a, b)] == ["kadro", "v6"]
