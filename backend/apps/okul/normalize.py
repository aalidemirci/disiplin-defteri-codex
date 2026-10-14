"""Öğrenci-veli içe aktarımı için saf (DB'siz) normalize ediciler.

OYS `apps/core/normalize.py` dosyasından AYNEN alındı (tasarım §4.4).

e-Okul / "Veli İletişim Bilgileri" ihracındaki ham hücreleri sistemin beklediği
biçime çevirir. Saf fonksiyonlardır — kolay test edilir (bkz. tests/test_normalize).
DB eşleştirme ve yazma `services.py`'dadır.

Gözlemlenen veri sorunları (görev brief'i §1):
  - TCKN bazen Excel'de '12345678901.0' gibi float metin gelir; bazen 12 hane (fake).
  - Telefon int gelir (5550000101) → baştaki 0 düşmüş, geri eklenir.
  - Sınıf '10/A' biçiminde; '10-A' da kabul edilir.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

# Türkçe karakter → ASCII (cinsiyet/eşleme karşılaştırmaları için).
_TR_UPPER_MAP = str.maketrans(
    {
        "ş": "S",
        "Ş": "S",
        "ı": "I",
        "İ": "I",
        "ğ": "G",
        "Ğ": "G",
        "ü": "U",
        "Ü": "U",
        "ö": "O",
        "Ö": "O",
        "ç": "C",
        "Ç": "C",
    }
)

_DIGITS_RE = re.compile(r"\d+")


def _ascii_upper(value: str) -> str:
    """Türkçe karakterleri ASCII'ye indirip büyük harfe çevirir (eşleme için)."""
    return value.translate(_TR_UPPER_MAP).upper()


# Türkçe büyük harf için yalnız i/ı özel: çıplak str.upper() "i" → "I" yapar (doğrusu "İ").
_TR_I_MAP = str.maketrans({"i": "İ", "ı": "I"})


def section_upper(value: str) -> str:
    """Şube adını TÜRKÇE büyük harfe çevirir ("ç" → "Ç", "i" → "İ").

    ASCII'ye KATLANMAZ (M6): "10/Ç" ile "10/C" ayrı şubelerdir ve şube adı resmî
    evraka basılır. İçe aktarma, elle giriş ve süzgeç aynı dönüşümü kullanır.
    """
    return value.strip().translate(_TR_I_MAP).upper()


def normalize_tckn(value: object) -> str | None:
    """Ham TCKN değerini doğrular ve 11 haneli dizgiye çevirir; geçersizse None.

    - Excel float metni temizlenir ('12345678901.0' → '12345678901').
    - 11 hane ve TCKN checksum algoritması sağlanmalı.
    """
    if value is None:
        return None
    s = str(value).strip().replace(" ", "")
    if not s:
        return None
    # Excel tamsayıyı float metnine çevirebilir ('12345678901.0'); ondalık kısmı at.
    for sep in (".", ","):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    if not s.isdigit():
        return None
    if len(s) != 11:
        return None
    if not _valid_tckn_checksum(s):
        return None
    return s


def _valid_tckn_checksum(tckn: str) -> bool:
    """T.C. Kimlik No checksum doğrulaması.

    Kural:
      - İlk hane 0 olamaz.
      - 10. hane = ((1,3,5,7,9. haneler toplamı)*7 - (2,4,6,8. haneler toplamı)) mod 10
      - 11. hane = (ilk 10 hanenin toplamı) mod 10
    """
    d = [int(c) for c in tckn]
    if d[0] == 0:
        return False
    odd_sum = d[0] + d[2] + d[4] + d[6] + d[8]
    even_sum = d[1] + d[3] + d[5] + d[7]
    tenth = (odd_sum * 7 - even_sum) % 10
    eleventh = sum(d[:10]) % 10
    return tenth == d[9] and eleventh == d[10]


def normalize_phone(value: object) -> str | None:
    """Ham telefonu '0XXXXXXXXXX' (11 hane) biçimine çevirir; geçersizse None.

    - int gelebilir (5550000101) → baştaki 0 düşmüş, geri eklenir.
    - '+90', boşluk, '-', '/', parantez temizlenir.
    - 10 hane → başına '0'; 11 hane ve '0' ile başlıyorsa olduğu gibi.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Excel float metni ('5550000101.0') → tam kısım.
    if s.endswith(".0"):
        s = s[:-2]
    # +90 / 90 ülke kodu, ayraçlar.
    s = s.replace("+90", "").replace(" ", "").replace("-", "").replace("/", "")
    s = s.replace("(", "").replace(")", "")
    digits = "".join(_DIGITS_RE.findall(s))
    if not digits:
        return None
    # 12 hane '90...' → ülke kodunu at.
    if len(digits) == 12 and digits.startswith("90"):
        digits = digits[2:]
    if len(digits) == 10:
        return "0" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return digits
    return None


# e-Okul uzun etiketindeki ("9. Sınıf / A Şubesi") sözcükler şube DEĞİLDİR; ilk
# harf öbeği şube sayıldığında evraka "9/SINIF" basılıyordu. Belirsiz etiket
# TAHMİN EDİLMEZ — None → satır görünür biçimde atlanır; sessiz kırpma farklı
# şubeleri tek şubede birleştirip evraka yanlış sınıf ve rehber öğretmen basar:
#   - seviyeden ÖNCE program kodu ya da yazılı program adı ("AMP 10/A",
#     "Anadolu Meslek Programı 10. Sınıf / A Şubesi");
#   - seviyeden sonra kodla başlayan çok parçalı ad ("10/AMP-A", "10 AMP A");
#   - kodsuz bileşik ad ("10/ÇG-A", "10/BT-A") ya da ardından sözcük gelen çok
#     harfli ad ("11 ÇOCUK GELİŞİMİ A"; "12/A Çocuk Gelişimi" ise A);
#   - şube alanına sığmayan ad (> 8 karakter, Student.class_section).
#   - rakamlı bileşik ad ya da ikinci seviye ("11/A-1", "12 10/A"), bitişik
#     Sınıf/Şube sözcüğü ("9.SınıfA"), ikinci şube adayı ("10/A, 10/B").
# Seviyeden sonra gelen tek ad şubedir ("10/MEM" → MEM, "11/A1" → A1); program
# kodu sonda gelirse ek sayılır ("10/A-ATP", "10/A (AMP)" → A); yıl atılır
# ("10/A-2026" → A). Karşılaştırma ASCII-katlanmış hâlle yapılır (yalnız eşleme
# için, §7.2). Altıncı doğrulama turunda 2.478 gerçekçi etiketle sınandı.
_CLASS_LABEL_WORDS = frozenset({"SINIF", "SINIFI", "SUBE", "SUBESI", "SNF", "SINF"})
_PROGRAM_CODES = frozenset({"AMP", "ATP", "MEM", "MESEM"})
_SECTION_TOKEN_RE = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+(?:[-/.][0-9A-Za-zÇĞİÖŞÜçğıöşü]+)*")
_SECTION_MAX_LENGTH = 8
_SINGLE_SECTION_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]\d*")
# Şube parçası harfle başlar, en çok 2 rakamla biter ("A", "A1", "MEM"); "A2025", "1A" değil.
_SECTION_PART_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+\d{0,2}")
_LEVEL_RE = re.compile(r"(?<!\d)\d{1,2}(?!\d)")
# Şube harfi olmayan etikette betimleyici sözcük şube sayılmaz ("10. Sınıf (Kız)",
# "9 Hazırlık", "10. Sınıf Listesi"): çok harfli şube en çok 3 harf (FEN, SAY, TM,
# MEM) ya da program kodu (MESEM) olabilir.
_SECTION_MAX_LETTERS = 3
_NOT_SECTION_WORDS = frozenset({"KIZ", "ERKEK"})


class _Ambiguous(Exception):
    """Etiket belirsiz: şube tahmin edilmez (normalize_class_section → None)."""


def _section_tokens(text: str) -> list[list[str]]:
    """Harf içeren öbekler, parçalarına ayrılmış. Öbekte harfli parçayla birlikte 1-2
    haneli sayı varsa ("A-1", "10/A" ikinci seviye) öbek "#" ile işaretlenir."""
    tokens: list[list[str]] = []
    for token in _SECTION_TOKEN_RE.findall(text):
        parts: list[str] = []
        short_num = False
        for part in re.split(r"[-/.]", token):
            if not part:
                continue
            if part.isdigit():
                short_num = short_num or len(part) <= 2
                continue  # yıl vb. ("A-2026") atılır
            folded = _ascii_upper(part)
            if folded in _CLASS_LABEL_WORDS:
                continue
            if "SINIF" in folded or "SUBE" in folded:
                raise _Ambiguous  # "SınıfA", "AŞubesi": bitişik yazım
            parts.append(part)
        if parts:
            tokens.append(parts + (["#"] if short_num else []))
    return tokens


def _is_program_code(token: str) -> bool:
    return _ascii_upper(token) in _PROGRAM_CODES


def _section_from_tokens(before: list[list[str]], after: list[list[str]]) -> str | None:
    if any("#" in token for token in before) or (after and "#" in after[0]):
        return None  # "A-1/10", "11/A-1", "12 10/A": rakam şubenin ya da ikinci seviyenin parçası
    after = [[p for p in t if p != "#"] for t in after]
    before_parts = [part for token in before for part in token]
    if len(before_parts) > 1 or any(_is_program_code(part) for part in before_parts):
        return None
    if not after:
        if not before_parts or not _SINGLE_SECTION_RE.fullmatch(before_parts[0]):
            return None  # "Lise 10", "Hazırlık 9": şube değil
        section = before_parts[0]
    else:
        parts = after[0]
        if len(after) > 1 and (
            _is_program_code(parts[0]) or not _SINGLE_SECTION_RE.fullmatch(parts[0])
        ):
            return None
        if any(_SINGLE_SECTION_RE.fullmatch(p) for t in after[1:] for p in t):
            return None  # "10/A B", "10/A, 10/B", "10 Ş.A": ikinci şube adayı
        if _is_program_code(parts[0]) and len(parts) > 1:
            return None
        if any(not _is_program_code(part) for part in parts[1:]):
            return None
        section = parts[0]
    if (
        section is None
        or len(section) > _SECTION_MAX_LENGTH
        or not _SECTION_PART_RE.fullmatch(section)
        or _ascii_upper(section) in _NOT_SECTION_WORDS
    ):
        return None
    letters = sum(ch.isalpha() for ch in section)
    if letters > _SECTION_MAX_LETTERS and not _is_program_code(section):
        return None
    return section


def normalize_class_section(value: object) -> tuple[int, str] | None:
    """'10/A', '10-A', '10 ç', '9. Sınıf / A Şubesi' → (10, 'A') / (10, 'Ç') / (9, 'A');
    9-12 dışı, belirsiz (program önekli, bileşik, rakamlı) veya ayrıştırılamazsa None."""
    if value is None:
        return None
    s = unicodedata.normalize("NFC", str(value)).strip()
    if not s:
        return None
    level_m = _LEVEL_RE.search(s)
    if level_m is None:
        return None
    try:
        section = _section_from_tokens(
            _section_tokens(s[: level_m.start()]), _section_tokens(s[level_m.end() :])
        )
    except _Ambiguous:
        return None
    if section is None:
        return None
    level = int(level_m.group())
    if level < 9 or level > 12:
        return None
    return level, section_upper(section)


def split_full_name(value: object) -> tuple[str, str]:
    """'EMRE CAN YILMAZ' → ('EMRE CAN', 'YILMAZ'); tek kelime → (kelime, '').

    Son kelime soyad kabul edilir. Title Case uygulanmaz — ham bırakılır
    (CLAUDE.md §2: görüntü biçimi sistemin başka katmanında uygulanır).
    """
    if value is None:
        return "", ""
    parts = str(value).split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


# Metin tarih biçimleri (TR görüntü + ISO); Excel hücresi datetime/date da gelebilir.
_DATE_PATTERNS = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d")

#: allow_future=True iken kabul edilen en ileri tarih (bugün + ~2 yıl).
_FUTURE_LIMIT_DAYS = 730


def normalize_excel_date(value: object, *, allow_future: bool = False) -> date | None:
    """Excel hücresini (datetime/date veya 'GG.AA.YYYY'/'GG/AA/YYYY'/'YYYY-AA-GG'
    metni) tarihe çevirir; çözülemeyen/mantıksız değer → None.

    - Yıl < 1900 → None (bozuk veri).
    - ``allow_future=False`` (varsayılan): gelecek tarih → None — doğum tarihi
      gelecekte olamaz.
    - ``allow_future=True``: bugün + 2 yıla kadar kabul — işe başlama tarihi
      meşru olarak gelecekte olabilir (`User.is_personnel_active` o tarihe kadar
      girişi zaten kapatır); daha ilerisi yazım hatası sayılır (ADR-0034).
    """
    parsed: date | None = None
    if isinstance(value, datetime):  # datetime, date'in alt sınıfı — önce bakılmalı
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif value is not None:
        s = str(value).strip()
        if s:
            # Excel bazen '12.03.2010 00:00:00' metni verir → zaman kuyruğunu at.
            s = s.split(" ", 1)[0]
            for pattern in _DATE_PATTERNS:
                try:
                    parsed = datetime.strptime(s, pattern).date()
                    break
                except ValueError:
                    continue
    if parsed is None or parsed.year < 1900:
        return None
    today = date.today()
    limit = today + timedelta(days=_FUTURE_LIMIT_DAYS) if allow_future else today
    if parsed > limit:
        return None
    return parsed


def normalize_gender(value: object) -> str:
    """'E/ERKEK/MALE' → 'E', 'K/KIZ/FEMALE' → 'K' (GenderType kodları); boş → ''.

    Çözülemeyen değerler için boş dize döner (model alanı blank kabul eder).
    """
    if value is None:
        return ""
    s = _ascii_upper(str(value).strip())
    if not s:
        return ""
    if s in {"E", "ERKEK", "MALE", "M", "B", "BAY"}:
        return "E"
    if s in {"K", "KIZ", "FEMALE", "F", "BAYAN"}:
        return "K"
    return ""
