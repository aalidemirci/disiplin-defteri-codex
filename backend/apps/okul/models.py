"""`okul` modelleri — kurum künyesi, ders yılı, tatil takvimi, kişi sicilleri, içe aktarma.

OYS'nin `core` modelleri baz alınarak TEK KULLANICILI masaüstü programa göre
düzleştirildi (tasarım §4.2):

- `Student`: OYS'deki Student + StudentEnrollment + StudentNameHistory +
  Parent + StudentParentLink beşlisinin DÜZLEŞTİRMESİ — sınıf/şube/no ve
  sorumlu veli bilgileri satır içi alanlardır (Form-15/17 veli tebliğleri
  `guardian_*` alanlarından beslenir). Tarihsel kayıt tutulmaz; yıl devrinde
  yeni e-Okul listesi yeniden import edilir (tasarım §4.6).
- `Personnel`: OYS `User`'ının login'siz ikamesi (ad/soyad/unvan/branş).
- `SchoolYear`/`Holiday`: `core.SchoolYear`/`CalendarEvent` ikamesi; tatil
  tablosu ders yılına bağlanmaz (iş günü hesabı tarih kapsamasıyla çalışır —
  OYS `is_working_day` davranış paritesi).
- Koşullu UniqueConstraint'ler SQLite partial index ile çalışır (3.8+);
  regresyon testleri `tests/test_models.py`.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from shared.crypto import EncryptedCharField, EncryptedTextField
from shared.models import BaseModel


class SchoolConfig(BaseModel):
    """Kurum bilgisi — TEK satır (singleton, pk=1).

    Kurulum sihirbazı doldurur; resmî evrak antedi (okul adı/ilçe/müdür) buradan
    çözülür. `setup_completed` sihirbaz kapısıdır: False iken uygulama kurulum
    ekranına yönlendirir.

    `app_password_hash` (F5-D5, tasarım §6): adı tarihsel — içeriği **parolanın
    özeti DEĞİLDİR**. Veri anahtarının (DEK) tek yönlü parmak izini tutar
    (`shared.crypto.key_fingerprint`). İki işi vardır:

    1. **Eşleşme denetimi.** Parola/tuz/sarmal `guvenlik.json`'dadır (veri
       dizini, tasarım §6); DB ise yedeklenip taşınabilir. Yanlış ikili
       (başka bir kurulumun `guvenlik.json`'u + bu DB) yan yana gelirse kilit
       açma REDDEDİLİR — yoksa alanlar sessizce çözülemez metne dönerdi.
    2. **Geçişin çatlaksız bitiş damgası.** Alan şifreleme geçişiyle AYNI
       veritabanı işleminde yazılır; elektrik kesilirse ikisi birden geri alınır
       ve yarım geçiş güvenle tespit edilip tamamlanabilir.

    Parola özetinin bilinçli olarak DB'de tutulmama sebebi: yedek dosyaları okul
    dışına (USB) çıkar; içlerinde parola doğrulayıcısı bulunması çevrimdışı kaba
    kuvvet denemesine hedef olurdu.
    """

    SINGLETON_PK = 1

    school_name = models.CharField("okul adı", max_length=255, blank=True, default="")
    province = models.CharField("il", max_length=64, blank=True, default="")
    district = models.CharField("ilçe", max_length=64, blank=True, default="")
    principal_name = models.CharField("müdür adı", max_length=128, blank=True, default="")
    setup_completed = models.BooleanField("kurulum tamamlandı", default=False)
    app_password_hash = models.CharField(
        "uygulama parolası özeti", max_length=255, blank=True, default=""
    )

    class Meta:
        verbose_name = "kurum yapılandırması"
        verbose_name_plural = "kurum yapılandırması"

    def __str__(self) -> str:
        return self.school_name or "Kurulmamış okul"

    @classmethod
    def load(cls) -> SchoolConfig:
        """Singleton satırı döndürür; yoksa KAYDEDİLMEMİŞ varsayılan (okuma yazmaz)."""
        instance: SchoolConfig | None = cls.objects.filter(pk=cls.SINGLETON_PK).first()
        return instance if instance is not None else cls(pk=None)


class SchoolYear(BaseModel):
    """Ders yılı (örn. '2026-2027'). Tek-aktif kuralı hem serviste hem DB kısıtında."""

    name = models.CharField("ad", max_length=32)
    start_date = models.DateField("başlangıç")
    end_date = models.DateField("bitiş")
    is_active = models.BooleanField("aktif", default=False)

    class Meta:
        verbose_name = "ders yılı"
        verbose_name_plural = "ders yılları"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_schoolyear_name_alive",
            ),
            # Savunma hattı: aktif yıl değişimi serviste "önce eskisini kapat"
            # sırasıyla yapılır; kısıt yarış/hata durumunda ikinci aktifi keser.
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True, deleted_at__isnull=True),
                name="uq_schoolyear_single_active",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SchoolTerm(BaseModel):
    """Ders yılının iki dönemi.

    Yarıyıl tatili iki dönem arasında boşluk olarak kalır. Bu model `Holiday`
    yerine kullanılır; yarıyıl tatili disiplin sürelerindeki iş günü hesabını
    durdurmaz.
    """

    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.CASCADE,
        related_name="terms",
        verbose_name="ders yılı",
    )
    sequence = models.PositiveSmallIntegerField("dönem", choices=((1, "1. dönem"), (2, "2. dönem")))
    start_date = models.DateField("başlangıç")
    end_date = models.DateField("bitiş")

    class Meta:
        verbose_name = "ders dönemi"
        verbose_name_plural = "ders dönemleri"
        ordering = ["school_year", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "sequence"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_schoolterm_year_sequence_alive",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__in=(1, 2)),
                name="ck_schoolterm_sequence",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ck_schoolterm_date_order",
            ),
        ]
        indexes = [
            models.Index(fields=["school_year", "start_date"], name="schoolterm_year_start_idx"),
        ]

    @property
    def name(self) -> str:
        return f"{self.sequence}. dönem"

    def __str__(self) -> str:
        return f"{self.school_year.name} · {self.name}"


class HolidayKind(models.TextChoices):
    """Tatil türü — seed/görüntüleme gruplaması için."""

    OFFICIAL = "OFFICIAL", "Resmî tatil"
    RELIGIOUS = "RELIGIOUS", "Dini bayram"
    OTHER = "OTHER", "İdari/diğer"


class Holiday(BaseModel):
    """İş günü hesabına giren tatil aralığı (tasarım §4.2 + §7).

    YALNIZ resmî/idari tatiller girilir; ara tatil / yarıyıl tatili GİRİLMEZ —
    memur çalışır, yasal disiplin süreleri işler (OYS ADR-0026 kavram ayrımının
    bu projedeki karşılığı; sihirbaz UI'ında açık uyarı vardır).

    `is_estimated`: hicri takvime bağlı dini bayramlar Diyanet ilanından önce
    TAHMİNİDİR — kullanıcı takvim ekranından düzeltebilir (tasarım §7).
    """

    name = models.CharField("ad", max_length=128)
    start_date = models.DateField("başlangıç", db_index=True)
    end_date = models.DateField("bitiş")
    kind = models.CharField(
        "tür", max_length=16, choices=HolidayKind.choices, default=HolidayKind.OFFICIAL
    )
    is_estimated = models.BooleanField("tahmini", default=False)

    class Meta:
        verbose_name = "tatil"
        verbose_name_plural = "tatiller"
        ordering = ["start_date"]
        constraints = [
            # Seed idempotency dayanağı: aynı (ad, başlangıç) canlı satır tekil.
            models.UniqueConstraint(
                fields=["name", "start_date"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_holiday_name_start_alive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date})"


class Personnel(BaseModel):
    """Okul personeli — login'siz sicil kaydı (OYS `User` ikamesi).

    Kurul üyelikleri / roller (Müdür, Disiplin Kurulu Başkanı vb.) F2'de ayrı
    tablolarda tanımlanır; burada yalnız kimlik + unvan/branş tutulur.
    """

    first_name = models.CharField("ad", max_length=100)
    last_name = models.CharField("soyad", max_length=100)
    title = models.CharField("unvan", max_length=64, blank=True, default="")
    branch = models.CharField("branş", max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "personel"
        verbose_name_plural = "personel"
        ordering = ["first_name", "last_name"]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        """OYS `User.get_full_name` paritesi — evrak şablonları (AYNEN kopya) bu adı çağırır."""
        return self.full_name

    @property
    def username(self) -> str:
        """OYS şablonlarındaki `|default:...username` fallback'i için parite (ad döner)."""
        return self.full_name


class ClassResponsibility(BaseModel):
    """Ders yılı ve şube bazında sorumlu personel eşleştirmesi.

    OYS'deki sınıf/şube organizasyonunun masaüstü uygulamadaki küçük, bağımsız
    karşılığıdır. Öğrenci sicilindeki ``class_level`` + ``class_section`` ile
    eşleşir; ayrı bir sınıf tablosu gerektirmez.
    """

    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name="class_responsibilities",
        verbose_name="ders yılı",
    )
    class_level = models.PositiveSmallIntegerField("sınıf")
    class_section = models.CharField("şube", max_length=8)
    class_teacher = models.ForeignKey(
        Personnel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_teacher_responsibilities",
        verbose_name="sınıf öğretmeni",
    )
    assistant_principal = models.ForeignKey(
        Personnel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_principal_responsibilities",
        verbose_name="ilgili müdür yardımcısı",
    )
    guidance_teacher = models.ForeignKey(
        Personnel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guidance_teacher_responsibilities",
        verbose_name="ilgili rehber öğretmen",
    )

    class Meta:
        verbose_name = "sınıf sorumluluğu"
        verbose_name_plural = "sınıf sorumlulukları"
        ordering = ["school_year", "class_level", "class_section"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "class_level", "class_section"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_class_responsibility_alive",
            )
        ]
        indexes = [
            models.Index(
                fields=["school_year", "class_level", "class_section"],
                name="okul_class_resp_lookup_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.school_year.name} — {self.class_label}"

    @property
    def class_label(self) -> str:
        return f"{self.class_level}/{self.class_section}"


class GenderType(models.TextChoices):
    MALE = "E", "Erkek"
    FEMALE = "K", "Kız"


class GuardianKinship(models.TextChoices):
    MOTHER = "ANNE", "Anne"
    FATHER = "BABA", "Baba"
    OTHER = "DIGER", "Diğer"


class StudentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Aktif"
    LEFT = "LEFT", "Ayrıldı"


class Student(BaseModel):
    """Öğrenci — düzleştirilmiş sicil satırı (tasarım §4.2).

    Evrak motoru sözleşmesi: `full_name`, `tckn`, `birth_date`, `class_label`,
    `student_number` — OYS `documents.py::_student_context` anahtarları bu
    property/alanlardan DEĞİŞMEDEN üretilir (şablon sadakati kritiği).

    ŞİFRELEME KAPSAMI (F5-D5, tasarım §10.2 "TCKN'ler, telefonlar, guardian
    bilgileri"): `tckn` + `guardian_*` alanları `EncryptedCharField`/
    `EncryptedTextField`'dır — uygulama parolası KONULDUĞUNDA şifrelenir,
    parolasız kipte düz kalır. Ad/soyad/okul no/sınıf KAPSAM DIŞIDIR; gerekçe:

    * Arama ve listeleme bu alanlar üzerinden yürür (`selectors.student_list`
      ad ve okul numarasında eşleşir, şube süzgeci DB tarafında filtreler).
      Şifreli alanda DB filtresi çalışmaz; kapsamı ada genişletmek her arama
      için tüm sicili belleğe çekmeyi ve `class_section` süzgecini yeniden
      yazmayı gerektirirdi.
    * Korumanın ağırlık merkezi kimlik numarası ve iletişim/adres bilgisidir
      (KVKK'da somut zarar potansiyeli en yüksek alanlar). Ad-soyad zaten sınıf
      listelerinde, evrak çıktılarında ve okul panolarında dolaşan veridir.
    * Dürüstlük: ad-soyad şifrelenmediği için arayüz metni "kişisel veri
      alanlarını şifreler" der, "veritabanını şifreler" DEMEZ (tasarım §6).
    """

    tckn = EncryptedCharField("TCKN", max_length=11, blank=True, default="")
    first_name = models.CharField("ad", max_length=100)
    last_name = models.CharField("soyad", max_length=100)
    student_number = models.CharField("okul no", max_length=16, blank=True, default="")
    class_level = models.PositiveSmallIntegerField("sınıf", null=True, blank=True)
    class_section = models.CharField("şube", max_length=8, blank=True, default="")
    birth_date = models.DateField("doğum tarihi", null=True, blank=True)
    gender = models.CharField(
        "cinsiyet", max_length=1, choices=GenderType.choices, blank=True, default=""
    )
    status = models.CharField(
        "durum", max_length=16, choices=StudentStatus.choices, default=StudentStatus.ACTIVE
    )
    # Sorumlu veli — satır içi (Form-15/17 veli tebliğleri buradan beslenir).
    guardian_name = EncryptedCharField("veli adı", max_length=200, blank=True, default="")
    # Yakınlık (ANNE/BABA/DİĞER) ŞİFRELENMEZ: kişiyi tanımlamaz, üç değerli bir
    # seçim listesidir (şifrelense de üç token'dan hangisi olduğu sayımla çözülür)
    # ve `choices` doğrulaması/DB süzgeci düz kalmalıdır.
    guardian_kinship = models.CharField(
        "veli yakınlığı", max_length=8, choices=GuardianKinship.choices, blank=True, default=""
    )
    guardian_phone = EncryptedCharField("veli telefonu", max_length=16, blank=True, default="")
    guardian_phone2 = EncryptedCharField(
        "ikinci veli telefonu", max_length=16, blank=True, default=""
    )
    guardian_address = EncryptedTextField("veli adresi", blank=True, default="")

    class Meta:
        verbose_name = "öğrenci"
        verbose_name_plural = "öğrenciler"
        ordering = ["class_level", "class_section", "student_number"]
        indexes = [
            models.Index(fields=["class_level", "class_section"], name="okul_student_class_idx"),
        ]
        constraints = [
            # TCKN'li canlı kayıt tekil; TCKN'siz elle eklenen kayıtlar kısıt dışı.
            models.UniqueConstraint(
                fields=["tckn"],
                condition=models.Q(deleted_at__isnull=True) & ~models.Q(tckn=""),
                name="uq_student_tckn_alive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.class_label or 'sınıfsız'})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def class_label(self) -> str:
        """'10/A' — evrak şablonlarının beklediği sınıf etiketi; sınıfsız → ''."""
        if self.class_level is None or not self.class_section:
            return ""
        return f"{self.class_level}/{self.class_section}"


class ImportSourceType(models.TextChoices):
    """İçe aktarma kaynak türü (xlsx ve pano yapıştırma AYNI türdedir)."""

    STUDENTS = "STUDENTS", "Öğrenci-Veli"
    PERSONNEL = "PERSONNEL", "Personel"


class ImportStatus(models.TextChoices):
    RUNNING = "RUNNING", "Çalışıyor"
    COMPLETED = "COMPLETED", "Tamamlandı"
    FAILED = "FAILED", "Başarısız"
    PREVIEWED = "PREVIEWED", "Önizlendi"


class ImportRun(BaseModel):
    """Her toplu içe aktarma için bir kayıt (geçmiş izi + idempotency uyarısı).

    OYS'den fark (tasarım §4.7/5): aynı dosyanın yeniden COMMIT'i ENGELLENMEZ —
    `already_imported` yalnız UYARIDIR (güncelleme meşru). Kısıt bozulmasın diye
    yeniden commit MEVCUT COMPLETED satırı günceller (yeni satır açmaz).
    """

    source_type = models.CharField(
        "kaynak türü", max_length=16, choices=ImportSourceType.choices, db_index=True
    )
    file_name = models.CharField("dosya adı", max_length=255, blank=True, default="")
    file_hash = models.CharField("içerik özeti (SHA256)", max_length=64, db_index=True)
    status = models.CharField(
        "durum", max_length=16, choices=ImportStatus.choices, default=ImportStatus.RUNNING
    )
    started_at = models.DateTimeField("başlangıç", default=timezone.now)
    finished_at = models.DateTimeField("bitiş", null=True, blank=True)
    report = models.JSONField("rapor", default=dict, blank=True)

    class Meta:
        verbose_name = "içe aktarma koşusu"
        verbose_name_plural = "içe aktarma koşuları"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source_type", "file_hash"], name="okul_importrun_hash_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "file_hash"],
                condition=models.Q(deleted_at__isnull=True, status="COMPLETED"),
                name="uq_importrun_completed_per_hash",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_source_type_display()} — {self.file_name or self.file_hash[:12]}"
