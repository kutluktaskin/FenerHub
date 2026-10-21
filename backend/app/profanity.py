"""Forum küfür filtresi.

Metin karşılaştırma için normalleştirilir ve eşleşen kelime orijinal metindeki yerinde "***"
ile değiştirilir. Yakalanan varyasyonlar:
  - Türkçe büyük/küçük harf ve aksanlar (ş->s, ğ->g, ü->u, ö->o, ç->c). Küçük "ı" ayrı harf
    sayılır ki "sıkıştırdık", "sıktı" gibi kelimeler sansürlenmesin; büyük "I" (İngilizce
    klavye) "i" sayılır. Doğru yazımında "ı" olan kökler iki yazımla da listededir.
  - harf yerine rakam/işaret: 0->o, 1->i, 3->e, 4->a, 5->s, 7->t, @->a, $->s
  - harf arasına konan noktalama: s.i.k, s-i-k, s_i_k
  - harf tekrarı: siiiiktir
Yanlış sansürü önlemek için belirsiz kökler sadece tam kelime olarak eşleşir ("göt" sansürlenir,
"götür" sansürlenmez; "sik" sansürlenir, "sikke" sansürlenmez).
"""
import re

FOLD = str.maketrans({"ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
JOINERS = set(".-_*+|/\\'")          # harf arasındaysa yok sayılır (s.i.k)


def _norm_char(c: str) -> str:
    low = {"I": "i", "İ": "i"}.get(c, c.lower())       # büyük I: İngilizce klavyede "i"
    return low.translate(FOLD).translate(LEET)


def normalize(word: str) -> str:
    """Kök listesi de aynı kurallardan geçer (ör. 'yarrak' -> 'yarak')."""
    out = []
    for c in word:
        n = _norm_char(c)
        if n.isalpha() and (not out or out[-1] != n):
            out.append(n)
    return "".join(out)


def _forms(words) -> set:
    """Her kök: Türkçe yazımı ve "ı" yerine "i" yazılmış hâli (amcık / amcik)."""
    return {normalize(w) for w in words} | {normalize(w.replace("ı", "i")) for w in words}


# Kelimenin başı bu köklerden biriyse (ekleriyle birlikte) sansürlenir
PREFIX = sorted(_forms((
    "siktir", "sikerim", "sikeyim", "sikeyin", "sikik", "sikim", "sikiyim", "sikti",
    "orospu", "orosbu", "yarrak", "yarak", "amına", "amcık", "pezevenk", "kahpe", "ibne",
    "gavat", "şerefsiz", "götveren", "götlek", "götün", "piçlik", "puşt", "kaltak", "yavşak",
)))
# Sadece tam kelime olarak sansürlenir (başka kelimelerin içinde/başında masum anlamları var)
EXACT = _forms(("amk", "aq", "sik", "göt", "piç", "oç", "mk"))


def _tokens(text: str):
    """(normalleştirilmiş kelime, orijinal başlangıç, orijinal bitiş) üretir."""
    word, start, end = [], None, None
    for i, c in enumerate(text):
        n = _norm_char(c)
        if n.isalpha():
            if start is None:
                start = i
            if not word or word[-1] != n:
                word.append(n)
            end = i
        elif c in JOINERS and word:
            continue                     # kelime devam edebilir (s.i.k); harf gelmezse kelime biter
        else:
            if word:
                yield "".join(word), start, end
            word, start, end = [], None, None
    if word:
        yield "".join(word), start, end


def is_bad(token: str) -> bool:
    return token in EXACT or any(token.startswith(p) for p in PREFIX)


def mask(text: str) -> str:
    """Küfürleri "***" ile değiştirir; boşlukları sadeleştirir."""
    text = re.sub(r"\s+", " ", text or "").strip()
    spans = [(s, e) for tok, s, e in _tokens(text) if is_bad(tok)]
    for s, e in reversed(spans):
        text = text[:s] + "***" + text[e + 1:]
    return text
