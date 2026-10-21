"""Küfür filtresi: Türkçe varyasyonlar yakalanır, masum kelimeler korunur."""
import pytest

from app.profanity import mask


@pytest.mark.parametrize("text,expected", [
    ("SİKTİR git", "*** git"),            # Türkçe büyük harf
    ("s.i.k.t.i.r", "***"),               # araya noktalama
    ("s1ktir", "***"),                    # harf yerine rakam
    ("siiiiiktir lan", "*** lan"),        # harf tekrarı
    ("serefsiz hakem", "*** hakem"),      # aksansız
    ("Şerefsizler", "***"),               # ekli
    ("yarrrak", "***"),
    ("amk ya", "*** ya"),
    ("Sikke ve göt.", "Sikke ve ***."),   # noktalama korunur
])
def test_masks_variants(text, expected):
    assert mask(text) == expected


@pytest.mark.parametrize("text", [
    "Haydi Fener!", "topu götür", "eski sikke", "Amin", "Kadıköy", "ama", "Sıkıştırdık rakibi",
    "Fenerbahçe 3-0 kazandı", "Amca maça geldi", "Göztepe maçı",
])
def test_keeps_innocent_words(text):
    assert mask(text) == text


def test_whitespace_normalized():
    assert mask("  çok   güzel \n gol ") == "çok güzel gol"


@pytest.mark.parametrize("text", ["Sıktı ama olmadı", "sıkıldık artık", "SIKIŞTIRDIK", "sıkı savunma"])
def test_dotless_i_words_are_safe(text):
    assert mask(text) == text


def test_dotted_spelling_roots():
    assert mask("amcık") == "***" and mask("amcik") == "***" and mask("SIKTIR") == "***"
