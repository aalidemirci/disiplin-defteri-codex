"""`okul` API uçları — İNCE view'lar (View → Service → Model; ORM selectors'ta).

Authsuz tek kullanıcılı program: izin sınıfı yok (settings AllowAny). Hata
gövdesi `shared.exceptions.dd_exception_handler` ile `{code, message, fields}`
sözleşmesine çevrilir; parser hataları ValidationError olarak yükseltilir.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import Any

from django.http import FileResponse
from rest_framework import generics, serializers
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.okul import selectors
from apps.okul.excel_veli import ParserError
from apps.okul.models import ClassResponsibility, Holiday, Personnel, SchoolYear, Student
from apps.okul.serializers import (
    ClassResponsibilitySerializer,
    HolidaySeedRequestSerializer,
    HolidaySerializer,
    ImportRequestSerializer,
    PersonnelSerializer,
    SchoolConfigSerializer,
    SchoolTermConfigurationSerializer,
    SchoolTermSerializer,
    SchoolYearSerializer,
    StudentSerializer,
)
from apps.okul.services import app_password as app_password_service
from apps.okul.services import calendar as calendar_service
from apps.okul.services import class_responsibilities as class_responsibility_service
from apps.okul.services import encrypted_backup as encrypted_backup_service
from apps.okul.services import imports as import_service
from apps.okul.services import persons as persons_service
from apps.okul.services import school_year as school_year_service
from apps.okul.services import setup as setup_service
from apps.okul.services import templates as template_service
from apps.okul.services import terms as term_service
from apps.okul.services import updates as update_service
from apps.okul.services import year_rollover as rollover_service

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Sicil boşken (kurulum öncesi) seçicilerin çalışabilmesi için varsayılan seviyeler.
DEFAULT_GRADE_LEVELS = (9, 10, 11, 12)

# Boolean query parametresi için kabul edilen "açık" değerler.
TRUE_VALUES = frozenset({"true", "1"})


@contextmanager
def _service_errors() -> Iterator[None]:
    """Servis `ValueError`'larını sözleşmeli 400'e çevirir (Türkçe mesaj korunur).

    `apps/disiplin/views.py::_service_errors` ile aynı desen; okul tarafında
    yükseltilen tek hata tipi ValueError olduğundan liste kısadır.
    """
    try:
        yield
    except ValueError as exc:
        raise serializers.ValidationError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Kurulum sihirbazı
# ---------------------------------------------------------------------------
class SetupStatusView(APIView):
    def get(self, request: Request) -> Response:
        return Response(selectors.setup_status())


class GradeLevelsView(APIView):
    """`GET /api/v1/grade-levels/` — UI seçicileri için seçilebilir öğrenim seviyeleri.

    Onur kurulu üyeleri sınıf seviyelerini temsil eder (md. 183/b), bu yüzden
    liste okulun gerçeğini yansıtmalı: sicilde FİİLEN kayıtlı seviyeler döner
    (sicil boşken, kurulum öncesi, formlar çalışsın diye 9-12 varsayılanı).

    Program 9-12 DEĞİŞMEZİ üzerine kuruludur: `normalize.normalize_class_section`
    içe aktarmada, `StudentSerializer.validate_class_level` elle girişte bu
    aralığın dışını reddeder — dolayısıyla sicil bu aralığın dışına çıkamaz ve
    bu uç asla serializer'ın reddedeceği bir seviye önermez. `prep_enabled`
    OYS yanıt şekliyle uyum için durur ve daima False'tur (Hazırlık desteği
    yalnız her iki yazma kapısı da gevşetilirse anlam kazanır).
    Kişisel veri içermez.
    """

    def get(self, request: Request) -> Response:
        levels = selectors.distinct_class_levels() or list(DEFAULT_GRADE_LEVELS)
        return Response(
            {
                "levels": [{"value": lvl, "label": str(lvl)} for lvl in levels],
                "prep_enabled": False,
            }
        )


class UpdateStatusView(APIView):
    """GitHub'daki son kararlı sürümü çalışan sürümle karşılaştırır."""

    def get(self, request: Request) -> Response:
        force = str(request.query_params.get("force", "")).lower() in TRUE_VALUES
        try:
            return Response(update_service.update_status(force=force))
        except update_service.UpdateError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class UpdateInstallerView(APIView):
    """Doğrulanmış Windows kurucusunu uygulama indirmesi olarak döndürür."""

    def get(self, request: Request) -> FileResponse:
        try:
            installer = update_service.download_latest_installer(force=True)
        except update_service.UpdateError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        # `resolve_app_paths` burada kasıtlı olarak yeniden çözülür: dönen dosyanın
        # uygulamanın güncelleme önbelleği içinde kaldığını savunma-derinliğiyle doğrula.
        update_dir = update_service.update_directory().resolve()
        if update_dir not in installer.resolve().parents:
            raise serializers.ValidationError("Güncelleme dosyası güvenli önbellek dışında.")
        return FileResponse(
            installer.open("rb"),
            as_attachment=True,
            filename=installer.name,
            content_type="application/vnd.microsoft.portable-executable",
        )


class SchoolConfigView(APIView):
    def get(self, request: Request) -> Response:
        return Response(SchoolConfigSerializer(setup_service.get_school_config()).data)

    def put(self, request: Request) -> Response:
        serializer = SchoolConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = setup_service.update_school_config(fields=dict(serializer.validated_data))
        return Response(SchoolConfigSerializer(config).data)


class SetupCompleteView(APIView):
    def post(self, request: Request) -> Response:
        config = setup_service.mark_setup_completed()
        return Response({"setup_completed": config.setup_completed})


# ---------------------------------------------------------------------------
# Ders yılları
# ---------------------------------------------------------------------------
class SchoolYearListCreateView(generics.ListCreateAPIView[SchoolYear]):
    serializer_class = SchoolYearSerializer

    def get_queryset(self) -> Any:
        return selectors.school_years()

    def perform_create(self, serializer: serializers.BaseSerializer[SchoolYear]) -> None:
        serializer.instance = school_year_service.create_school_year(
            **dict(serializer.validated_data)
        )


class SchoolTermView(APIView):
    def get(self, request: Request, pk: int) -> Response:
        year = get_object_or_404(selectors.school_years(), pk=pk)
        return Response(SchoolTermSerializer(year.terms.all(), many=True).data)

    def put(self, request: Request, pk: int) -> Response:
        year = get_object_or_404(selectors.school_years(), pk=pk)
        serializer = SchoolTermConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with _service_errors():
            terms = term_service.configure_terms(
                year,
                first_end=serializer.validated_data["first_term_end"],
                second_start=serializer.validated_data["second_term_start"],
            )
        return Response(SchoolTermSerializer(terms, many=True).data)


class SchoolYearActivateView(APIView):
    def post(self, request: Request, pk: int) -> Response:
        year = get_object_or_404(selectors.school_years(), pk=pk)
        school_year_service.activate_school_year(year)
        return Response(SchoolYearSerializer(year).data)


# ---------------------------------------------------------------------------
# Tatiller
# ---------------------------------------------------------------------------
class HolidayListCreateView(generics.ListCreateAPIView[Holiday]):
    serializer_class = HolidaySerializer

    def get_queryset(self) -> Any:
        return selectors.holidays()

    def perform_create(self, serializer: serializers.BaseSerializer[Holiday]) -> None:
        serializer.instance = calendar_service.create_holiday(**dict(serializer.validated_data))


class HolidayDetailView(generics.DestroyAPIView[Holiday]):
    serializer_class = HolidaySerializer

    def get_queryset(self) -> Any:
        return selectors.holidays()

    def perform_destroy(self, instance: Holiday) -> None:
        calendar_service.delete_holiday(instance)


class HolidaySeedView(APIView):
    def post(self, request: Request) -> Response:
        serializer = HolidaySeedRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year_id = serializer.validated_data.get("school_year")
        if year_id is not None:
            year = get_object_or_404(selectors.school_years(), pk=year_id)
        else:
            active = selectors.active_school_year()
            if active is None:
                raise serializers.ValidationError(
                    "Aktif ders yılı yok; önce bir ders yılı oluşturup aktifleştirin."
                )
            year = active
        created, skipped = calendar_service.seed_holidays(year)
        return Response({"created": created, "skipped": skipped})


# ---------------------------------------------------------------------------
# Öğrenciler / Personel
# ---------------------------------------------------------------------------
class StudentListCreateView(generics.ListCreateAPIView[Student]):
    serializer_class = StudentSerializer

    def get_queryset(self) -> Any:
        params = self.request.query_params
        raw_level = params.get("class_level", "").strip()
        class_level: int | None = None
        if raw_level:
            # isdigit() Unicode basamaklarda ('²') True dönüp int()'te patlar;
            # sayısal olmayan değer de sessizce yutulmamalı — sözleşmeli 400.
            try:
                class_level = int(raw_level)
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"class_level": "Sınıf filtresi sayısal olmalıdır."}
                ) from exc
        return selectors.student_list(
            class_level=class_level,
            class_section=params.get("class_section", ""),
            search=params.get("search", ""),
            # Süzgeç OPT-IN: sicil ekranı ayrılmış öğrenciyi de görmeli; yalnız
            # seçiciler (autocomplete) `only_active=true` gönderir.
            only_active=params.get("only_active", "").strip().lower() in TRUE_VALUES,
        )

    def perform_create(self, serializer: serializers.BaseSerializer[Student]) -> None:
        serializer.instance = persons_service.create_student(**dict(serializer.validated_data))


class StudentDetailView(generics.RetrieveUpdateDestroyAPIView[Student]):
    serializer_class = StudentSerializer

    def get_queryset(self) -> Any:
        return selectors.students_all()

    def perform_update(self, serializer: serializers.BaseSerializer[Student]) -> None:
        assert serializer.instance is not None
        serializer.instance = persons_service.update_student(
            serializer.instance, **dict(serializer.validated_data)
        )

    def perform_destroy(self, instance: Student) -> None:
        persons_service.delete_student(instance)


class PersonnelListCreateView(generics.ListCreateAPIView[Personnel]):
    serializer_class = PersonnelSerializer

    def get_queryset(self) -> Any:
        return selectors.personnel_list(search=self.request.query_params.get("search", ""))

    def perform_create(self, serializer: serializers.BaseSerializer[Personnel]) -> None:
        serializer.instance = persons_service.create_personnel(**dict(serializer.validated_data))


class PersonnelDetailView(generics.RetrieveUpdateDestroyAPIView[Personnel]):
    serializer_class = PersonnelSerializer

    def get_queryset(self) -> Any:
        return selectors.personnel_list()

    def perform_update(self, serializer: serializers.BaseSerializer[Personnel]) -> None:
        assert serializer.instance is not None
        serializer.instance = persons_service.update_personnel(
            serializer.instance, **dict(serializer.validated_data)
        )

    def perform_destroy(self, instance: Personnel) -> None:
        persons_service.delete_personnel(instance)


class ClassResponsibilityListCreateView(generics.ListCreateAPIView[ClassResponsibility]):
    serializer_class = ClassResponsibilitySerializer

    def get_queryset(self) -> Any:
        raw_year = self.request.query_params.get("school_year", "").strip()
        school_year_id: int | None = None
        if raw_year:
            try:
                school_year_id = int(raw_year)
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"school_year": "Ders yılı kimliği sayısal olmalıdır."}
                ) from exc
        return selectors.class_responsibilities(school_year_id=school_year_id)

    def perform_create(self, serializer: serializers.BaseSerializer[ClassResponsibility]) -> None:
        serializer.instance = class_responsibility_service.create_class_responsibility(
            **dict(serializer.validated_data)
        )


class ClassResponsibilityDetailView(generics.RetrieveUpdateDestroyAPIView[ClassResponsibility]):
    serializer_class = ClassResponsibilitySerializer

    def get_queryset(self) -> Any:
        return selectors.class_responsibilities_all()

    def perform_update(self, serializer: serializers.BaseSerializer[ClassResponsibility]) -> None:
        assert serializer.instance is not None
        serializer.instance = class_responsibility_service.update_class_responsibility(
            serializer.instance, **dict(serializer.validated_data)
        )

    def perform_destroy(self, instance: ClassResponsibility) -> None:
        class_responsibility_service.delete_class_responsibility(instance)


# ---------------------------------------------------------------------------
# İçe aktarma (dosya VEYA pano metni — aynı boru hattı)
# ---------------------------------------------------------------------------
class _BaseImportView(APIView):
    """Ortak istek çözümü; alt sınıf servis fonksiyonlarını belirler."""

    file_handler: str = ""  # import_service fonksiyon adı (dosya yolu)
    text_handler: str = ""  # import_service fonksiyon adı (metin yolu)

    def post(self, request: Request) -> Response:
        serializer = ImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data.get("file")
        try:
            if uploaded is not None:
                handler = getattr(import_service, self.file_handler)
                report = handler(file_bytes=uploaded.read(), file_name=uploaded.name or "")
            else:
                handler = getattr(import_service, self.text_handler)
                report = handler(text=serializer.validated_data["text"])
        except ParserError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return Response(report.to_dict())


class StudentImportPreviewView(_BaseImportView):
    file_handler = "preview_students_file"
    text_handler = "preview_students_text"


class StudentImportCommitView(_BaseImportView):
    file_handler = "commit_students_file"
    text_handler = "commit_students_text"


class PersonnelImportPreviewView(_BaseImportView):
    file_handler = "preview_personnel_file"
    text_handler = "preview_personnel_text"


class PersonnelImportCommitView(_BaseImportView):
    file_handler = "commit_personnel_file"
    text_handler = "commit_personnel_text"


# ---------------------------------------------------------------------------
# Şablon indirme
# ---------------------------------------------------------------------------
class StudentTemplateView(APIView):
    def get(self, request: Request) -> FileResponse:
        return FileResponse(
            BytesIO(template_service.student_template_xlsx()),
            as_attachment=True,
            filename="sablon-ogrenci.xlsx",
            content_type=XLSX_CONTENT_TYPE,
        )


class PersonnelTemplateView(APIView):
    def get(self, request: Request) -> FileResponse:
        return FileResponse(
            BytesIO(template_service.personnel_template_xlsx()),
            as_attachment=True,
            filename="sablon-personel.xlsx",
            content_type=XLSX_CONTENT_TYPE,
        )


# ---------------------------------------------------------------------------
# Yıl devri sihirbazı (tasarım §4.6)
# ---------------------------------------------------------------------------
# İstek serializer'ları BİLİNÇLİ OLARAK burada: `serializers.py` yalnız kalıcı
# kaynak temsillerini (SchoolYear/Holiday/Student…) tutar; bunlar yalnız bu üç
# ucun gövde doğrulamasıdır. Yanıtta yeniden kullanılan tek temsil
# `SchoolYearSerializer`'dır.
class RolloverYearRequestSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=32)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    first_term_end = serializers.DateField(required=False)
    second_term_start = serializers.DateField(required=False)
    # Tatil seed'i varsayılan AÇIK; kullanıcı yeni yılın takvimini elle
    # kuracaksa kapatabilir (dini bayram tahminleri de o zaman yazılmaz).
    seed_holidays = serializers.BooleanField(default=True)


class PromoteStudentsRequestSerializer(serializers.Serializer[dict[str, Any]]):
    # `apply=False` ÖNİZLEMEDİR (hiçbir şey yazılmaz) — import boru hattıyla
    # aynı iki adımlı sözleşme; varsayılan güvenli taraftır.
    apply = serializers.BooleanField(default=False)
    graduate_final_level = serializers.BooleanField(default=True)


class YearRolloverStatusView(APIView):
    """`GET /api/v1/year-rollover/status/` — sihirbaz açılış özeti.

    Disiplin tarafındaki uyarılar (kapanmamış dosyalar, yeni yılda kurul tanımlı
    mı) BU UÇTA DEĞİLDİR: `apps.okul` `apps.disiplin`e bağlanmaz (bağımlılık yönü
    tek yönlü). Sihirbaz ekranı o iki bilgiyi mevcut disiplin uçlarından okur.
    """

    def get(self, request: Request) -> Response:
        status = rollover_service.rollover_status()
        return Response(
            {
                "active_school_year": (
                    SchoolYearSerializer(status.active_school_year).data
                    if status.active_school_year is not None
                    else None
                ),
                "suggested_year": status.suggestion.to_dict(),
                "active_student_count": status.active_student_count,
                "students_without_level": status.students_without_level,
                "level_counts": [m.to_dict() for m in status.level_counts],
            }
        )


class YearRolloverSchoolYearView(APIView):
    """`POST /api/v1/year-rollover/school-year/` — yeni yılı açar ve AKTİF yapar."""

    def post(self, request: Request) -> Response:
        req = RolloverYearRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            result = rollover_service.create_next_school_year(**dict(req.validated_data))
        return Response(
            {
                "school_year": SchoolYearSerializer(result.school_year).data,
                "previous_school_year_name": result.previous_school_year_name,
                "holidays_created": result.holidays_created,
                "holidays_skipped": result.holidays_skipped,
            },
            status=201,
        )


class YearRolloverPromoteStudentsView(APIView):
    """`POST /api/v1/year-rollover/promote-students/` — toplu sınıf yükseltme.

    `apply=false` önizlemedir. Uygulama GERİ ALINAMAZ (eski sınıf saklanmaz);
    UI onay diyaloğu bunu açıkça söyler.
    """

    def post(self, request: Request) -> Response:
        req = PromoteStudentsRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            report = rollover_service.promote_students(**dict(req.validated_data))
        return Response(report.to_dict())


# ---------------------------------------------------------------------------
# Uygulama parolası / kilit (tasarım §6, F5-D5)
# ---------------------------------------------------------------------------
# Bu uçlar `apps.okul.lock_middleware.AppLockMiddleware` tarafından KİLİT
# KAPISINDAN MUAFTIR (`/api/v1/security/` ön eki) — kilidi açmanın tek yolu
# bunlardır. Parolalar YALNIZ istek gövdesinde taşınır; hiçbir yanıtta,
# günlükte veya hata mesajında yankılanmaz.
class AppPasswordRequestSerializer(serializers.Serializer[dict[str, Any]]):
    password = serializers.CharField(trim_whitespace=False)


class AppPasswordChangeSerializer(serializers.Serializer[dict[str, Any]]):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)


class AppPasswordRecoverSerializer(serializers.Serializer[dict[str, Any]]):
    recovery_key = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)


class SecurityStatusView(APIView):
    """`GET /api/v1/security/status/` — parola kurulu mu, kilitli mi, geçiş yarım mı."""

    def get(self, request: Request) -> Response:
        return Response(app_password_service.status())


class SecurityEnableView(APIView):
    """`POST /api/v1/security/enable/` — parolayı kurar, alanları şifreler.

    Yanıttaki `recovery_key` TEK SEFERLİKTİR: sunucu onu bir daha üretemez
    (yalnız sarmalı saklanır). Arayüz kullanıcıya yazdırtmadan diyaloğu kapatmaz.
    """

    def post(self, request: Request) -> Response:
        req = AppPasswordRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            kurtarma = app_password_service.enable(password=req.validated_data["password"])
        return Response({"recovery_key": kurtarma, **app_password_service.status()}, status=201)


class SecurityUnlockView(APIView):
    """`POST /api/v1/security/unlock/` — parolayla kilidi açar (yarım geçişi tamamlar)."""

    def post(self, request: Request) -> Response:
        req = AppPasswordRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            app_password_service.unlock(password=req.validated_data["password"])
        return Response(app_password_service.status())


class SecurityLockView(APIView):
    """`POST /api/v1/security/lock/` — anahtarı bellekten düşürür."""

    def post(self, request: Request) -> Response:
        app_password_service.lock()
        return Response(app_password_service.status())


class SecurityRecoverView(APIView):
    """`POST /api/v1/security/recover/` — kurtarma anahtarıyla açar + yeni parola."""

    def post(self, request: Request) -> Response:
        req = AppPasswordRecoverSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            app_password_service.unlock_with_recovery(
                recovery_key=req.validated_data["recovery_key"],
                new_password=req.validated_data["new_password"],
            )
        return Response(app_password_service.status())


class SecurityChangePasswordView(APIView):
    """`POST /api/v1/security/change-password/` — veri yeniden şifrelenmez, sarmal yenilenir."""

    def post(self, request: Request) -> Response:
        req = AppPasswordChangeSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            app_password_service.change_password(
                current_password=req.validated_data["current_password"],
                new_password=req.validated_data["new_password"],
            )
        return Response(app_password_service.status())


class SecurityDisableView(APIView):
    """`POST /api/v1/security/disable/` — parolayı kaldırır, alanları düz metne döndürür."""

    def post(self, request: Request) -> Response:
        req = AppPasswordRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            app_password_service.disable(password=req.validated_data["password"])
        return Response(app_password_service.status())


# ---------------------------------------------------------------------------
# Kullanıcı isteğiyle oluşturulan şifreli veritabanı yedeği
# ---------------------------------------------------------------------------
class EncryptedBackupDownloadView(APIView):
    def post(self, request: Request) -> FileResponse:
        with _service_errors():
            content, filename = encrypted_backup_service.create_encrypted_backup()
        return FileResponse(
            BytesIO(content),
            as_attachment=True,
            filename=filename,
            content_type="application/octet-stream",
        )
