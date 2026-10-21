"""Demo üretimi: canlı kayıttan /ws/live biçiminde zaman çizelgesi (scripts/build_demo.py)."""
import json

from scripts import build_demo

API = 555
BASE = {"id": "demo", "home": "Fenerbahçe", "away": "Rakip", "match_date": "2026-10-20",
        "competition": "uefa", "status": "scheduled", "home_score": None, "away_score": None,
        "status_code": None, "period_start": None, "period_initial": None}


def write(tmp_path, rows):
    p = tmp_path / "kayit.jsonl"
    p.write_text("\n".join(json.dumps({"t": t, "msg": m}) for t, m in rows), encoding="utf-8")
    return p


def msg(suffix, data, kind="update"):
    return {"channel": f"match:{API}{suffix}", "type": kind, "data": data}


def goal(t, h, a):
    return {"incidentType": "goal", "time": t, "isHome": h > a, "homeScore": h, "awayScore": a,
            "player": {"name": "Golcü"}}


def test_build_timeline(tmp_path):
    lineups = {"confirmed": True, "home": {"players": [], "formation": "4-3-3"},
               "away": {"players": [], "formation": "4-4-2"}}
    stats = {"statistics": [{"period": "ALL", "groups": []}]}
    rows = [
        (900, {"type": "welcome"}),                                            # yok sayılır
        (850, msg(":lineups", lineups)),                                       # oynatma başından önce: başlangıç kadrosu
        (980, msg("", {"homeScore.current": 0, "awayScore.current": 0})),      # başlamadan: yok sayılır
        (1000, msg("", {"status.code": 6, "status.type": "inprogress",
                        "time.currentPeriodStartTimestamp": 1000, "time.initial": 0})),
        (1100, msg(":stats", stats)),
        (1130, msg(":stats", stats)),                                          # aynı içerik: atlanır
        (1300, msg(":incidents", {"incidents": [goal(5, 1, 0)]})),
        (1301, msg("", {"homeScore.current": 1})),
        (1302, msg("", {"homeScore.current": 1})),                             # değişiklik yok: atlanır
        (3700, msg("", {"status.code": 31})),
        (4600, msg("", {"status.code": 7, "time.currentPeriodStartTimestamp": 4600, "time.initial": 2700})),
        (7400, msg("", {"status.code": 100, "status.type": "finished"})),
        (9999, msg(":incidents", {"incidents": [goal(5, 1, 0)]})),             # bitiş + 90 sn sonrası: alınmaz
    ]
    demo = build_demo.build(write(tmp_path, rows), API, BASE)

    assert demo["meta"]["title"] == "Fenerbahçe 1-0 Rakip"
    assert demo["meta"]["start"] == 1000 - build_demo.LEAD_IN
    state = demo["events"][0][1]
    assert state["type"] == "state" and state["lineups"]["home"]["formation"] == "4-3-3"
    assert state["match"]["status"] == "scheduled"

    updates = [(t, e["kind"], e["data"]) for t, e in demo["events"][1:]]
    match = [(t, d["status"], d["status_code"], d["home_score"]) for t, k, d in updates if k == "match"]
    assert match == [
        (120.0, "live", 6, 0),
        (421.0, "live", 6, 1),
        (2820.0, "live", 31, 1),
        (3720.0, "live", 7, 1),
        (6520.0, "finished", None, 1),
    ]
    assert [k for _, k, _ in updates].count("statistics") == 1
    assert [k for _, k, _ in updates].count("incidents") == 1
    times = [t for t, _, _ in updates]
    assert times == sorted(times)
