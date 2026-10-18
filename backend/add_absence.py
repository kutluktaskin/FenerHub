import argparse

from app.database import SessionLocal
from app import models


def find_player(db, name):
    rows = db.query(models.Player).filter(models.Player.name.ilike(f"%{name}%")).all()
    exact = [p for p in rows if p.name.lower() == name.lower()]
    if exact:
        return exact[0]
    if len(rows) == 1:
        return rows[0]
    if not rows:
        print(f"'{name}' adında oyuncu bulunamadı. Kadro adını tam yazdığından emin ol.")
    else:
        print("Birden fazla eşleşme var, tam adı yaz:", [p.name for p in rows])
    return None


def add_absence(db, player, type_, reason, note, match_id=None):
    exists = (
        db.query(models.Absence)
        .filter_by(player_id=player.id, match_id=match_id)
        .first()
    )
    if exists:
        exists.type, exists.reason, exists.return_note = type_, reason, note
        return "güncellendi"
    db.add(models.Absence(
        player_id=player.id, match_id=match_id,
        type=type_, reason=reason, return_note=note,
    ))
    return "eklendi"


def cmd_ekle(db, args):
    player = find_player(db, args.oyuncu)
    if not player:
        return
    print(f"{player.name}: genel rapor {add_absence(db, player, args.tur, args.sebep, args.donus)}")
    if args.maclar:
        matches = (
            db.query(models.Match)
            .filter(models.Match.status != "finished", models.Match.match_date.isnot(None))
            .order_by(models.Match.match_date)
            .limit(args.maclar)
            .all()
        )
        for m in matches:
            print(f"  maç {m.match_date}: {add_absence(db, player, args.tur, args.sebep, args.donus, m.id)}")
    db.commit()


def cmd_sil(db, args):
    player = find_player(db, args.oyuncu)
    if not player:
        return
    n = db.query(models.Absence).filter_by(player_id=player.id).delete()
    db.commit()
    print(f"{player.name}: {n} kayıt silindi")


def cmd_liste(db, args):
    rows = db.query(models.Absence).all()
    for a in rows:
        p = db.query(models.Player).get(a.player_id)
        print(f"{p.name:25} {a.type:11} maç_id={a.match_id}  {a.reason or ''}  {a.return_note or ''}")
    print(f"Toplam {len(rows)} kayıt")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("ekle")
    e.add_argument("oyuncu")
    e.add_argument("tur", choices=["injury", "suspension"])
    e.add_argument("sebep", nargs="?", default=None)
    e.add_argument("--donus", default=None, help="örn: '2 Hafta' veya 'Mart 2027'")
    e.add_argument("--maclar", type=int, default=0, help="önümüzdeki kaç maça eklensin")

    s = sub.add_parser("sil")
    s.add_argument("oyuncu")

    sub.add_parser("liste")

    args = ap.parse_args()
    db = SessionLocal()
    try:
        {"ekle": cmd_ekle, "sil": cmd_sil, "liste": cmd_liste}[args.cmd](db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()