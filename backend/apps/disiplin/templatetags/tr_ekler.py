"""Türkçe ad çekimi süzgeçleri — resmî yazıda ad sonrası TAMLAYAN (ilgi) eki.

Saha denetimi 14.11.2026: şablonlarda ek sabit yazılıydı ("Güler Şığın'nın", "Deniz
Aydın'in", "Iğdırlı'in"). Ek, adın SON sözcüğünün son ünlüsüne (büyük ünlü uyumu +
düzlük/yuvarlaklık) ve son harfine (ünlüyle bitiyorsa "n" kaynaştırması) göre üretilir:

    Aydın'ın · Şığın'ın · Çelik'in · Öztürk'ün · Uçar'ın · Gül'ün
    Kaya'nın · Iğdırlı'nın · Arı'nın · Ünlü'nün · Ekinci'nin · Koru'nun

Türkçe ı/İ/i/I ayrımı elle yapılır (CLAUDE.md §7.2): çıplak `.lower()` "I" → "i" ve
"İ" → "i̇" üretir; burada "I" → "ı", "İ" → "i". Ad BÜYÜK harfle yazılmışsa (sicil
adları böyledir) ek de büyük harfle gelir ("ŞIĞIN'IN", "ÇELİK'İN").

Ad alanına yazılmış ad DIŞI son bölüm ekten önce ayrılır (gözden geçirme 14.11.2026):
sondaki parantezli bölüm ekin ARKASINA alınır ("Ayşe Kaya (anne)" → "Ayşe Kaya'nın
(anne)"), sondaki virgül vb. noktalama atılır ("Demir," → "Demir'in"; kısaltma noktası
korunur: "Ali K." → "Ali K.'nin"). Asıl adın sonu harf değilse (rakam, simge) ek
ÜRETİLMEZ: `tr_tamlayan` eksiz kalıba ("… adlı kişinin") döner, adda hiç harf yoksa boş
döner — şablon kendi yedek kalıbını basar, cümle bozulmaz.

YALNIZ değiştirilebilir (bilinçli istisna) şablonlarda kullanılır; AYNEN şablonlara
`{% load %}` eklenmez. Süzgeç eşleştirme için değil BASIM içindir: adın harflerini
değiştirmez, yalnız kesme işareti ile eki ekler.
"""

from __future__ import annotations

import re

from django import template

register = template.Library()

_BACK_UNROUNDED = "aı"
_FRONT_UNROUNDED = "ei"
_BACK_ROUNDED = "ou"
_FRONT_ROUNDED = "öü"
_VOWELS = _BACK_UNROUNDED + _FRONT_UNROUNDED + _BACK_ROUNDED + _FRONT_ROUNDED

# Türkçe küçük harf: I → ı, İ → i (gerisi str.lower); düzeltme işaretli ünlüler yalın
# karşılığıyla değerlendirilir (â → a, î → i, û → u).
_TR_LOWER_MAP = str.maketrans(
    {"I": "ı", "İ": "i", "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u"}
)
# Türkçe büyük harf: i → İ, ı → I (gerisi str.upper).
_TR_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})

# Son ünlüsü KALIN olduğu hâlde eki İNCE alan alıntı sözcükler (ince "l" ya da ince
# okunan "-at" ile bitenler): "Kemal'in", "Hilal'in", "Şefkat'in", "Resul'ün". Kapalı
# küme — TDK yazımında ince ek aldığından emin olunan adlar ve ad olarak kullanılan
# sözcükler. Bilerek DIŞARIDA bırakılanlar: "Meral", "Seval", "Vedat", "Nihat", "Ferhat",
# "Hayat" (kalın: "Meral'ın", "Nihat'ın"); emin olunmayan ad eklenmez.
_FRONT_EXCEPTIONS: dict[str, str] = {
    # -al (ince l)
    "kemal": "i",
    "cemal": "i",
    "celal": "i",
    "bilal": "i",
    "hilal": "i",
    "nihal": "i",
    "gülnihal": "i",
    "zuhal": "i",
    "zülal": "i",
    "şevval": "i",
    "ikbal": "i",
    "iclal": "i",
    "feryal": "i",
    "hayal": "i",
    "visal": "i",
    "istiklal": "i",
    "ihtilal": "i",
    # -at (ince okunan)
    "şefkat": "i",
    "sadakat": "i",
    "dikkat": "i",
    "saat": "i",
    "kanaat": "i",
    "hakikat": "i",
    # -ul (ince l, yuvarlak)
    "resul": "ü",
}

# Adın sonundaki parantezli bölüm (kapanmamış parantez dahil): "(anne)", "(veli".
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)?\s*$")
# Asıl adın sonundan atılan noktalama (nokta HARİÇ — kısaltma noktası korunur).
_TRAILING_NOISE = " ,;:!?-–—/"


def _split_name(name: str) -> tuple[str, str]:
    """(asıl ad, sondaki parantezli bölüm) — ek asıl ada göre üretilir."""
    core = (name or "").strip()
    tails: list[str] = []
    while True:
        match = _TRAILING_PAREN.search(core) if "(" in core else None
        if match is None:
            break
        tails.insert(0, match.group().strip())
        core = core[: match.start()]
    return core.rstrip(_TRAILING_NOISE), " ".join(tails)


def _tr_lower(value: str) -> str:
    return value.translate(_TR_LOWER_MAP).lower()


def _tr_upper(value: str) -> str:
    return value.translate(_TR_UPPER_MAP).upper()


def tamlayan_eki(name: str) -> str:
    """Adın alacağı tamlayan ekini kesme işaretiyle döndürür ("'ın", "'nün" …).

    Ek ASIL ada göre üretilir (sondaki parantezli bölüm ve noktalama ayrılır). Boş ad
    ya da sonu harf olmayan ad (rakam, simge) → "" (ek üretilmez). Ünlüsü olmayan
    sözcükte (kısaltma) harf adı okunuşu esas alınır ("…'nin"); kısaltma noktası eki
    engellemez ("Ali K." → "'nin").
    """
    core, _tail = _split_name(name)
    words = core.split()
    if not words:
        return ""
    raw = words[-1]
    word = _tr_lower(raw).rstrip(".")
    if not word or not word[-1].isalpha():
        return ""
    letters_only = "".join(ch for ch in raw if ch.isalpha())
    is_upper = len(letters_only) > 1 and letters_only == _tr_upper(letters_only)

    last_vowel = next((ch for ch in reversed(word) if ch in _VOWELS), "")
    if word in _FRONT_EXCEPTIONS:
        vowel = _FRONT_EXCEPTIONS[word]
    elif not last_vowel:
        suffix = "nin"
        return "'" + (_tr_upper(suffix) if is_upper else suffix)
    elif last_vowel in _BACK_UNROUNDED:
        vowel = "ı"
    elif last_vowel in _FRONT_UNROUNDED:
        vowel = "i"
    elif last_vowel in _BACK_ROUNDED:
        vowel = "u"
    else:
        vowel = "ü"
    buffer = "n" if word and word[-1] in _VOWELS else ""
    suffix = f"{buffer}{vowel}n"
    return "'" + (_tr_upper(suffix) if is_upper else suffix)


@register.filter(name="tr_tamlayan_eki")
def tr_tamlayan_eki(value: object) -> str:
    """`<strong>{{ ad }}</strong>{{ ad|tr_tamlayan_eki }}` → yalnız ek ("'ın")."""
    return tamlayan_eki(str(value or ""))


@register.filter(name="tr_tamlayan")
def tr_tamlayan(value: object) -> str:
    """`{{ ad|tr_tamlayan }}` → "Güler Şığın'ın"; boş ad boş döner.

    Parantezli son bölüm ekin arkasına alınır ("Ayşe Kaya'nın (anne)"). Ek üretilemiyorsa
    (asıl adın sonu harf değil) eksiz kalıp basılır ("Ali Kaya 2 adlı kişinin"); adda hiç
    harf yoksa "" döner — şablon `|default:'…'` ile kendi yedek kalıbını basar.
    """
    core, tail = _split_name(str(value or ""))
    if not any(ch.isalpha() for ch in core):
        return ""
    suffix = tamlayan_eki(core)
    head = f"{core}{suffix}" if suffix else f"{core} adlı kişinin"
    return f"{head} {tail}" if tail else head
