import json


def load(name):
    with open(f"detail_{name}.json", encoding="utf-8") as f:
        return json.load(f)["data"]


# --- Olaylar ---
inc = load("incidents")["incidents"]
print("OLAYLAR:", len(inc))
for i in inc[:25]:
    print({k: i.get(k) for k in ("incidentType", "incidentClass", "time", "addedTime", "isHome", "homeScore", "awayScore", "text")},
          "| oyuncu:", (i.get("player") or {}).get("name"))
print("Bir olayın tüm anahtarları:", list(inc[0].keys()))

# --- İstatistik ---
st = load("statistics")["statistics"]
print("\nİSTATİSTİK dönemleri:", [s["period"] for s in st])
for g in st[0]["groups"][:2]:
    print(" grup:", g["groupName"])
    for it in g["statisticsItems"][:6]:
        print("   ", {k: it.get(k) for k in ("name", "home", "away", "key")})

# --- Diziliş ---
ln = load("lineups")
print("\nDİZİLİŞ anahtarları:", list(ln.keys()))
for side in ("home", "away"):
    s = ln[side]
    print(side, "diziliş:", s.get("formation"), "| oyuncu sayısı:", len(s["players"]))
    p = s["players"][0]
    print("  ilk kayıt anahtarları:", list(p.keys()))
    print("  ", {k: v for k, v in p.items() if k != "player"}, "|", p["player"]["name"])

# --- Şut haritası ---
sm = load("shotmap")["shotmap"]
print("\nŞUT:", len(sm))
print("Bir şutun anahtarları:", list(sm[0].keys()))
print({k: v for k, v in sm[0].items() if k != "player"}, "|", sm[0]["player"]["name"])