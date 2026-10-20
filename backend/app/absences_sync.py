"""Sakatlık ve cezaların otomatik güncellenmesi (kaynak: kadro verisindeki missingPlayers).

SportsAPI'nin /match/{id}/lineups cevabı (ve WS lineups kanalı) her takım için
missingPlayers listesi verir: oyuncu adı, eksik/şüpheli, açıklama ("Knee Injury"),
tahmini dönüş tarihi. Buradan iki şey güncellenir:
  - o maçın eksikleri (absences.match_id = maç)
  - genel sakatlık raporu (match_id boş): en yeni kadro verisindeki liste esas alınır

Sadece source="api" kayıtlar değişir; elle girilenler (source="manual") korunur. Aynı
oyuncu için elle girilmiş kayıt varsa otomatik kayıt eklenmez (elle girilen kazanır).
Kadroda bulunamayan isimler loglanır.
"""
import unicodedata
from datetime import date, datetime

from . import models
from .database import SessionLocal

FB = "Fenerbahçe"
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# API açıklamaları (İngilizce) -> sitede gösterilen Türkçe karşılık
REASONS = {
    "knee injury": "Diz sakatlığı", "meniscus injury": "Menisküs sakatlığı",
    "cruciate ligament injury": "Çapraz bağ sakatlığı", "ligament injury": "Bağ sakatlığı",
    "muscle injury": "Kas sakatlığı", "hamstring injury": "Arka adale sakatlığı",
    "thigh injury": "Uyluk sakatlığı", "calf injury": "Baldır sakatlığı",
    "groin injury": "Kasık sakatlığı", "ankle injury": "Ayak bileği sakatlığı",
    "foot injury": "Ayak sakatlığı", "achilles tendon problems": "Aşil tendonu sorunu",
    "back injury": "Sırt sakatlığı", "hip injury": "Kalça sakatlığı",
    "shoulder injury": "Omuz sakatlığı", "head injury": "Kafa travması",
    "concussion": "Beyin sarsıntısı", "illness": "Hastalık", "virus": "Hastalık",
    "knock": "Darbe", "injury": "Sakatlık", "fitness": "Kondisyon eksikliği",
    "red card": "Kırmızı kart cezası", "yellow card suspension": "Sarı kart cezası",
    "suspension": "Ceza", "suspended": "Ceza",
}
SUSPENSION_WORDS = ("card", "suspen")


def norm(name: str) -> str:
    s = unicodedata.normalize("NFD", name or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def reason_tr(description: str | None) -> str | None:
    if not description:
        return None
    return REASONS.get(description.strip().lower(), description.strip())


def return_note(expected: str | None, today: date | None = None) -> str | None:
    """'2026-12-10T00:00:00+00:00' -> '10 Aralık' (geçmiş tarihse 'Belirsiz')."""
    if not expected:
        return None
    try:
        d = datetime.fromisoformat(expected.replace("Z", "+00:00")).date()
    except ValueError:
        return None
    if d < (today or date.today()):
        return "Belirsiz"
    return f"{d.day} {MONTHS[d.month - 1]}" + (f" {d.year}" if d.year != (today or date.today()).year else "")


def parse_missing(item: dict) -> dict:
    desc = item.get("description") or ""
    suspended = any(w in desc.lower() for w in SUSPENSION_WORDS)
    reason = reason_tr(desc)
    if item.get("type") == "doubtful":
        reason = f"Şüpheli · {reason}" if reason else "Şüpheli"
    return {
        "name": (item.get("player") or {}).get("name"),
        "type": "suspension" if suspended else "injury",
        "reason": reason,
        "return_note": return_note(item.get("expectedEndDate")),
    }


def fb_side(db, match: models.Match, data: dict) -> dict | None:
    home = db.get(models.Team, match.home_team_id)
    return (data.get("home") if home and home.name == FB else data.get("away")) or None


def _replace(db, team_id: int, match_id: int | None, items: list[dict]) -> tuple[int, list[str]]:
    """match_id kapsamındaki api kayıtlarını items ile değiştirir; (eklenen, eşleşmeyen)."""
    players = {norm(p.name): p for p in db.query(models.Player).filter_by(team_id=team_id)}
    scope = db.query(models.Absence).filter(models.Absence.match_id.is_(None) if match_id is None
                                            else models.Absence.match_id == match_id)
    manual = {a.player_id for a in scope.filter(models.Absence.source == "manual")}
    scope.filter(models.Absence.source == "api").delete(synchronize_session=False)
    added, unmatched = 0, []
    for it in items:
        player = players.get(norm(it["name"]))
        if not player:
            unmatched.append(it["name"])
            continue
        if player.id in manual:
            continue
        db.add(models.Absence(player_id=player.id, match_id=match_id, type=it["type"],
                              reason=it["reason"], return_note=it["return_note"], source="api"))
        added += 1
    return added, unmatched


def apply_lineups(api_id: int, data: dict | None, general: bool = True) -> None:
    """Kadro verisinden (REST cevabının data alanı ya da WS snapshot'ı) eksikleri günceller.
    general=True: genel sakatlık raporu da bu listeye göre güncellenir (en yeni veri)."""
    if not isinstance(data, dict) or "home" not in data:
        return
    with SessionLocal() as db, db.begin():
        match = db.query(models.Match).filter_by(api_id=api_id).first()
        fb = db.query(models.Team).filter_by(name=FB).first()
        if not match or not fb:
            return
        side = fb_side(db, match, data)
        if side is None:
            return
        items = [parse_missing(m) for m in side.get("missingPlayers") or [] if (m.get("player") or {}).get("name")]
        added, unmatched = _replace(db, fb.id, match.id, items)
        if general:
            _replace(db, fb.id, None, items)
    print(f"Eksikler (maç {api_id}): {added} otomatik kayıt"
          + (f"; kadroda bulunamayan: {unmatched}" if unmatched else ""), flush=True)
