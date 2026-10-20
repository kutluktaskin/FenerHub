"""!!! BU SCRIPT VERİTABANINI SİLER !!!

Projenin ilk günlerindeki elle yazılmış verileri (eski index.html) yükler. Çalıştırınca
takım, oyuncu, maç, istatistik, sakatlık ve puan durumu tabloları TAMAMEN temizlenir.
Gerçek veri artık SportsAPI'den gelir (app/sync.py); bu script sadece boş bir yerel
SQLite'ı denemek için durur. Canlı veritabanında (DATABASE_URL) ASLA çalıştırmayın.

  python -m scripts.seed      # onay sorar
"""
import os
import sys

from app.database import SessionLocal, engine, Base, db_label
from app import models
from datetime import date, time

FB = "Fenerbahçe"

TEAM_ALIASES = {
    "Şahtar Donetsk": "Shakhtar Donetsk",
    "Atletico Madrid": "Atlético Madrid",
    "Amed": "Amed SK",
}

# (isim, mevki, maç, gol, asist)
PLAYERS = [
    ("Edin Džeko", "Santrafor", 12, 9, 3),
    ("Dušan Tadić", "Kanat", 12, 5, 7),
    ("Sebastian Szymański", "On Numara", 12, 4, 5),
    ("Youssef En-Nesyri", "Santrafor", 11, 5, 1),
    ("Fred", "Orta Saha", 9, 3, 3),
    ("İrfan Can Kahveci", "Sağ Kanat", 10, 2, 3),
    ("Alexander Djiku", "Stoper", 10, 0, 1),
    ("Jayden Oosterwolde", "Sol Bek", 9, 1, 0),
    ("Rodrigo Becão", None, 8, 1, 0),
    ("Cengiz Ünder", None, 5, 1, 0),
    ("Serdar Aziz", None, 2, 0, 0),
]

# (tarih, ev sahibi, deplasman, saat, turnuva)
FIXTURES = [
    ("2026-10-20", FB, "Alanyaspor", "19:45", "super_lig"),
    ("2026-10-26", FB, "Slavia Prag", "21:30", "uefa"),
    ("2026-10-31", "Galatasaray", FB, "19:00", "super_lig"),
    ("2026-11-04", FB, "Göztepe", "20:45", "super_lig"),
    ("2026-11-08", FB, "Liverpool", "16:00", "uefa"),
    ("2026-11-21", "Çorum", FB, "19:00", "super_lig"),
    ("2026-11-25", "Kocaelispor", FB, "23:00", "super_lig"),
    ("2026-11-29", "Şahtar Donetsk", FB, "19:00", "uefa"),
    ("2026-12-05", FB, "Erzurumspor", "19:00", "super_lig"),
    ("2026-12-09", "Başakşehir", FB, "23:00", "super_lig"),
    ("2026-12-13", "LASK Linz", FB, "19:00", "uefa"),
    ("2026-12-20", FB, "Trabzonspor", None, "super_lig"),
    ("2027-01-17", "Kasımpaşa", FB, None, "super_lig"),
    ("2027-01-20", FB, "Amed", "20:45", "super_lig"),
    ("2027-01-24", FB, "Villarreal", None, "uefa"),
    ("2027-01-27", FB, "Gençlerbirliği", "23:00", "super_lig"),
    ("2027-01-31", "Atletico Madrid", FB, None, "uefa"),
    ("2027-02-07", "Konyaspor", FB, None, "super_lig"),
    ("2027-02-14", FB, "Samsunspor", None, "super_lig"),
    ("2027-02-21", "Beşiktaş", FB, None, "super_lig"),
    ("2027-02-28", FB, "Gaziantep FK", None, "super_lig"),
    ("2027-03-07", "Eyüpspor", FB, None, "super_lig"),
    ("2027-03-14", FB, "Rizespor", None, "super_lig"),
    ("2027-03-21", "Alanyaspor", FB, None, "super_lig"),
    ("2027-04-04", FB, "Galatasaray", None, "super_lig"),
    ("2027-04-11", "Göztepe", FB, None, "super_lig"),
    ("2027-04-18", FB, "Çorum", None, "super_lig"),
    ("2027-04-25", FB, "Kocaelispor", None, "super_lig"),
    ("2027-05-02", "Erzurumspor", FB, None, "super_lig"),
    ("2027-05-09", FB, "Başakşehir", None, "super_lig"),
    ("2027-05-16", "Trabzonspor", FB, None, "super_lig"),
    ("2027-05-23", FB, "Kasımpaşa", None, "super_lig"),
    (None, "Amed", FB, None, "super_lig"),
]

# (sıra, takım, O, G, B, M, AV, P)
SUPER_LIG = [
    (1, "Galatasaray", 7, 5, 1, 1, 11, 16),
    (2, "Beşiktaş", 7, 4, 3, 0, 9, 15),
    (3, "Amed SK", 7, 4, 2, 1, 6, 14),
    (4, "Fenerbahçe", 7, 4, 1, 2, 10, 13),
    (5, "Trabzonspor", 7, 4, 1, 2, 5, 13),
    (6, "Kocaelispor", 7, 3, 3, 1, 4, 12),
    (7, "Göztepe", 7, 3, 2, 2, 2, 11),
    (8, "Başakşehir", 7, 3, 1, 3, 0, 10),
    (9, "Samsunspor", 7, 3, 1, 3, -1, 10),
    (10, "Kasımpaşa", 7, 2, 3, 2, -1, 9),
    (11, "Gaziantep FK", 7, 2, 2, 3, -2, 8),
    (12, "Konyaspor", 7, 2, 2, 3, -3, 8),
    (13, "Rizespor", 7, 2, 1, 4, -4, 7),
    (14, "Alanyaspor", 7, 1, 3, 3, -3, 6),
    (15, "Antalyaspor", 7, 1, 3, 3, -5, 6),
    (16, "Hatayspor", 7, 1, 2, 4, -6, 5),
    (17, "Adana Demirspor", 7, 1, 1, 5, -8, 4),
    (18, "Bodrum FK", 7, 1, 1, 5, -9, 4),
    (19, "Eyüpspor", 7, 0, 3, 4, -5, 3),
]

UEFA = [
    (1, "Barcelona", 2, 2, 0, 0, 6, 6),
    (2, "Arsenal", 2, 2, 0, 0, 4, 6),
    (3, "Liverpool", 2, 2, 0, 0, 4, 6),
    (4, "Bayern München", 2, 1, 1, 0, 5, 4),
    (5, "Real Madrid", 2, 1, 1, 0, 2, 4),
    (6, "Inter", 2, 1, 1, 0, 2, 4),
    (7, "Bayer Leverkusen", 2, 1, 1, 0, 1, 4),
    (8, "Borussia Dortmund", 2, 1, 0, 1, 3, 3),
    (9, "Manchester City", 2, 1, 0, 1, 2, 3),
    (10, "Paris Saint-Germain", 2, 1, 0, 1, 1, 3),
    (11, "Juventus", 2, 1, 0, 1, 0, 3),
    (12, "Atlético Madrid", 2, 1, 0, 1, -1, 3),
    (13, "Milan", 2, 1, 0, 1, -1, 3),
    (14, "Sporting CP", 2, 1, 0, 1, -2, 3),
    (15, "Villarreal", 2, 1, 0, 1, -2, 3),
    (16, "PSV Eindhoven", 2, 0, 2, 0, 0, 2),
    (17, "Monaco", 2, 0, 2, 0, 0, 2),
    (18, "Stuttgart", 2, 0, 1, 1, -1, 1),
    (19, "Bologna", 2, 0, 1, 1, -1, 1),
    (20, "Shakhtar Donetsk", 2, 0, 1, 1, -2, 1),
    (21, "Club Brugge", 2, 0, 1, 1, -2, 1),
    (22, "Celtic", 2, 0, 1, 1, -3, 1),
    (23, "Sparta Praha", 2, 0, 1, 1, -3, 1),
    (24, "Fenerbahçe", 1, 0, 1, 0, 0, 1),
    (25, "Slavia Prag", 2, 0, 1, 1, -2, 1),
    (26, "Young Boys", 2, 0, 1, 1, -3, 1),
    (27, "Red Bull Salzburg", 2, 0, 0, 2, -3, 0),
    (28, "LASK Linz", 2, 0, 0, 2, -4, 0),
    (29, "Sturm Graz", 2, 0, 0, 2, -4, 0),
    (30, "Brest", 2, 0, 0, 2, -5, 0),
    (31, "Girona", 2, 0, 0, 2, -5, 0),
    (32, "Red Star Belgrade", 2, 0, 0, 2, -5, 0),
    (33, "Slovan Bratislava", 2, 0, 0, 2, -6, 0),
    (34, "Galatasaray", 2, 0, 0, 2, -5, 0),
]


def confirm() -> bool:
    print("UYARI: Bu script şu veritabanındaki takım, oyuncu, maç, istatistik, sakatlık ve")
    print(f"puan durumu kayıtlarını SİLER: {db_label()}")
    if os.environ.get("DATABASE_URL"):
        print("DATABASE_URL tanımlı: hedef canlı veritabanı olabilir!")
    return input("Devam etmek için 'evet' yazın: ").strip().lower() == "evet"


def main():
    if not confirm():
        sys.exit("İptal edildi, hiçbir şey silinmedi.")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    for model in (models.Absence, models.PlayerStat, models.Standing,
                  models.Match, models.Player, models.Team):
        db.query(model).delete()
    db.commit()

    teams = {}

    def get_team(name):
        name = TEAM_ALIASES.get(name, name)
        if name not in teams:
            team = models.Team(name=name)
            db.add(team)
            db.flush()
            teams[name] = team
        return teams[name]

    fb = get_team(FB)
    players = {}
    for name, position, apps, goals, assists in PLAYERS:
        p = models.Player(name=name, position=position, team_id=fb.id)
        db.add(p)
        db.flush()
        players[name] = p
        db.add(models.PlayerStat(
            player_id=p.id, appearances=apps, goals=goals, assists=assists
        ))

    created = []
    for d, home, away, t, comp in FIXTURES:
        m = models.Match(
            competition=comp,
            match_date=date.fromisoformat(d) if d else None,
            kickoff_time=time.fromisoformat(t) if t else None,
            home_team_id=get_team(home).id,
            away_team_id=get_team(away).id,
            status="scheduled",
        )
        db.add(m)
        created.append(m)
    db.flush()

    alanya, slavia, derbi = created[0], created[1], created[2]
    alanya.home_score, alanya.away_score = 2, 1
    alanya.status, alanya.minute = "live", "89'"

    def absence(player, type_, reason=None, match=None, note=None):
        db.add(models.Absence(
            player_id=players[player].id,
            match_id=match.id if match else None,
            type=type_, reason=reason, return_note=note,
        ))

    absence("Jayden Oosterwolde", "injury", "Ön Çapraz Bağ", note="Mart 2027")
    absence("İrfan Can Kahveci", "injury", "Arka Adale", note="2 Hafta")
    absence("Alexander Djiku", "suspension", "4 Sarı Kart Sınırı")

    absence("Jayden Oosterwolde", "injury", "Diz Bağları", alanya)
    absence("İrfan Can Kahveci", "injury", "Arka Adale", alanya)
    absence("Alexander Djiku", "suspension", "4 Sarı Kart", alanya)

    absence("Jayden Oosterwolde", "injury", None, slavia)
    absence("Rodrigo Becão", "suspension", None, slavia)
    absence("Cengiz Ünder", "injury", None, slavia)

    absence("Jayden Oosterwolde", "injury", None, derbi)
    absence("Serdar Aziz", "injury", None, derbi)
    absence("Alexander Djiku", "returned", "Cezası Bitti", derbi)

    for comp, rows in (("super_lig", SUPER_LIG), ("uefa", UEFA)):
        for pos, team, o, g, b, m, av, p in rows:
            db.add(models.Standing(
                competition=comp, position=pos, team_id=get_team(team).id,
                played=o, won=g, drawn=b, lost=m,
                goal_difference=av, points=p,
            ))

    db.commit()
    db.close()
    print("Seed tamamlandı.")


if __name__ == "__main__":
    main()