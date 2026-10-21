"""Takvim aboneliği (/api/calendar.ics)."""
from datetime import date, datetime, time, timezone
from types import SimpleNamespace as NS

from app import ical


def match(**kw):
    base = dict(id=7, competition="super_lig", matchday=9, match_date=date(2026, 10, 25), kickoff_time=time(20, 0),
                home_team=NS(name="Fenerbahçe"), away_team=NS(name="Göztepe"), status="scheduled",
                home_score=None, away_score=None)
    base.update(kw)
    return NS(**base)


def unfold(text):
    return text.replace("\r\n ", "")


def test_timed_match_is_utc_with_alarm():
    ics = ical.build_ics([match()], now=datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    body = unfold(ics)
    assert "DTSTART:20261025T170000Z" in body and "DTEND:20261025T190000Z" in body   # 20:00 TSİ = 17:00 UTC
    assert "SUMMARY:Fenerbahçe - Göztepe" in body
    assert "Süper Lig · 9. hafta · İç saha" in body
    assert "TRIGGER:-PT1H" in body and "UID:fenerhub-mac-7@fenerhub.vercel.app" in body


def test_finished_untimed_and_away():
    ics = unfold(ical.build_ics([
        match(id=1, status="finished", home_score=2, away_score=1),
        match(id=2, kickoff_time=None, home_team=NS(name="Slavia, Prag"), away_team=NS(name="Fenerbahçe"),
              competition="uefa", matchday=None),
        match(id=3, match_date=None),                       # tarihi belirsiz: yazılmaz
    ]))
    assert "SUMMARY:Fenerbahçe 2-1 Göztepe" in ics
    assert ics.count("BEGIN:VALARM") == 0                    # bitmiş ve saatsiz maça hatırlatma yok
    assert "DTSTART;VALUE=DATE:20261025" in ics and "DTEND;VALUE=DATE:20261026" in ics
    assert "SUMMARY:Slavia\\, Prag - Fenerbahçe" in ics and "Deplasman" in ics
    assert ics.count("BEGIN:VEVENT") == 2


def test_long_lines_are_folded_on_char_boundary():
    folded = ical.fold("DESCRIPTION:" + "ğ" * 80)
    parts = folded.split("\r\n ")
    assert len(parts) > 1 and all(len(p.encode("utf-8")) <= 75 for p in parts)
    assert "".join(parts) == "DESCRIPTION:" + "ğ" * 80


def test_endpoint_reads_db():
    from app.database import SessionLocal
    with SessionLocal() as db:
        r = ical.calendar(db)
    assert r.media_type.startswith("text/calendar")
    assert r.body.decode().startswith("BEGIN:VCALENDAR")
