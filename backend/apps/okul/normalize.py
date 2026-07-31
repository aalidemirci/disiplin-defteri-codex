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


def normalize_class_section(value: object) -> tuple[int, str] | None:
    """'10/A', '10-A', '10 A' → (10, 'A'); 9-12 dışı veya ayrıştırılamazsa None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    level_m = re.search(r"\d{1,2}", s)
    section_m = re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", s)
    if level_m is None or section_m is None:
        return None
    level = int(level_m.group())
    if level < 9 or level > 12:
        return None
    section = _ascii_upper(section_m.group())
    return level, section


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
