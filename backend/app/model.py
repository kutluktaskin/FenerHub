"""İstatistik modeli (Poisson): skor tahmin oyununda "Taraftarlar vs Model" rakibi.

Her takımın beklenen gol sayısı:
    lig ortalaması x takımın hücum gücü x rakibin savunma zaafı x saha etkisi
- hücum gücü  = maç başına attığı gol / lig ortalaması
- savunma zaafı = maç başına yediği gol / lig ortalaması
- saha etkisi: ev sahibi x1.10, deplasman x0.90
Veri: puan durumundaki attığı/yediği goller (api_cache "standings"). Takım tabloda yoksa güç 1.
İki takımın golleri bağımsız Poisson kabul edilir; 0-8 gol arası her skorun olasılığı hesaplanır.
"""
import math

HOME_ADV, AWAY_ADV = 1.10, 0.90
MAX_GOALS = 8
SHRINK = 3          # az maç oynamış takımın gücü ortalamaya çekilir (3 maçlık "sanal ortalama")


def _rates(rows):
    """{takım: (hücum, savunma)} ve lig ortalaması (takım başı maç başı gol)."""
    played = sum(r["played"] for r in rows)
    goals = sum(r["goals_for"] for r in rows)
    avg = goals / played if played else 1.3
    out = {}
    for r in rows:
        n = r["played"] + SHRINK
        att = (r["goals_for"] + SHRINK * avg) / n / avg
        dfn = (r["goals_against"] + SHRINK * avg) / n / avg
        out[r["team"]] = (att, dfn)
    return out, avg


def expected_goals(rows, home: str, away: str):
    rates, avg = _rates(rows or [])
    ha, hd = rates.get(home, (1.0, 1.0))
    aa, ad = rates.get(away, (1.0, 1.0))
    return avg * ha * ad * HOME_ADV, avg * aa * hd * AWAY_ADV


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(rows, home: str, away: str) -> dict:
    """{'home': 2, 'away': 1, 'p_home': .48, 'p_draw': .26, 'p_away': .26, 'xg_home', 'xg_away'}"""
    lh, la = expected_goals(rows, home, away)
    best, p_home, p_draw, p_away = (0, 0, -1.0), 0.0, 0.0, 0.0
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            p = poisson(h, lh) * poisson(a, la)
            if p > best[2]:
                best = (h, a, p)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return {
        "home": best[0], "away": best[1],
        "p_home": round(p_home / total, 3), "p_draw": round(p_draw / total, 3), "p_away": round(p_away / total, 3),
        "xg_home": round(lh, 2), "xg_away": round(la, 2),
    }
