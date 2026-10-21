"""Takvim aboneliği: GET /api/calendar.ics (iCalendar, RFC 5545).

Telefon/Google/Outlook takvimi bu adrese abone olunca Fenerbahçe maçları takvime düşer,
saat değişirse takvim kendiliğinden güncellenir. Sadece veritabanını okur, API'ye istek atmaz.
Saati belli maçlar UTC saatiyle (1 saat önce hatırlatmalı), saati belli olmayanlar tüm gün etkinliği olarak yazılır."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from . import models
from .database import get_db
from .sync import TR_TZ

router = APIRouter(tags=["calendar"])

SITE = "https://fenerhub.vercel.app"
COMPETITION = {"super_lig": "Süper Lig", "uefa": "Şampiyonlar Ligi"}
MATCH_LENGTH = timedelta(hours=2)
PAST_DAYS = 120          # eski maçlar sonsuza kadar listede kalmasın


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    """75 baytı geçen satırı RFC 5545'e göre böler (UTF-8 karakteri ortadan bölünmez)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event_lines(m: models.Match, stamp: str) -> list[str]:
    home, away = m.home_team.name, m.away_team.name
    comp = COMPETITION.get(m.competition, m.competition)
    summary = f"{home} - {away}"
    if m.status == "finished" and m.home_score is not None:
        summary = f"{home} {m.home_score}-{m.away_score} {away}"
    where = "İç saha" if home == "Fenerbahçe" else "Deplasman"
    desc = f"{comp}{f' · {m.matchday}. hafta' if m.matchday else ''} · {where}\nCanlı takip: {SITE}"
    lines = ["BEGIN:VEVENT", f"UID:fenerhub-mac-{m.id}@fenerhub.vercel.app", f"DTSTAMP:{stamp}"]
    if m.kickoff_time:
        start = datetime.combine(m.match_date, m.kickoff_time, tzinfo=TR_TZ)
        lines += [f"DTSTART:{utc(start)}", f"DTEND:{utc(start + MATCH_LENGTH)}"]
    else:
        day = m.match_date
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines += [f"SUMMARY:{escape(summary)}", f"DESCRIPTION:{escape(desc)}", f"URL:{SITE}/",
              f"CATEGORIES:{escape(comp)}"]
    if m.kickoff_time and m.status == "scheduled":
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape(summary)} 1 saat sonra",
                  "TRIGGER:-PT1H", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def build_ics(matches, now: datetime | None = None) -> str:
    stamp = utc(now or datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//FenerHub//Mac Takvimi//TR", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Fenerbahçe Maçları (FenerHub)", "X-WR-TIMEZONE:Europe/Istanbul",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for m in matches:
        if m.match_date:
            lines += event_lines(m, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


@router.get("/api/calendar.ics")
def calendar(db: Session = Depends(get_db)):
    since = (datetime.now(TR_TZ) - timedelta(days=PAST_DAYS)).date()
    matches = (db.query(models.Match)
               .options(joinedload(models.Match.home_team), joinedload(models.Match.away_team))
               .filter(models.Match.match_date >= since)
               .order_by(models.Match.match_date, models.Match.kickoff_time).all())
    return Response(build_ics(matches), media_type="text/calendar; charset=utf-8", headers={
        "Content-Disposition": 'inline; filename="fenerbahce.ics"',
        "Cache-Control": "public, max-age=1800",
    })
