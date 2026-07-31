"""`okul` DRF serializer'ları — doğrulama + normalize burada, yazma serviste.

Elle giriş, içe aktarmayla AYNI normalize edicilerden geçer (`apps.okul.normalize`):
TCKN checksum, telefon biçimi, şube harfi ASCII katlaması — iki giriş yolu tek
davranış. Hatalar Türkçedir (`{code, message, fields}` sözleşmesi).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.okul import normalize
from apps.okul.models import (
    ClassResponsibility,
    Holiday,
    Personnel,
    SchoolConfig,
    SchoolTerm,
    SchoolYear,
    Student,
)


class SchoolConfigSerializer(serializers.ModelSerializer[SchoolConfig]):
    class Meta:
        model = SchoolConfig
        fields = ["school_name", "province", "district", "principal_name", "setup_completed"]
        read_only_fields = ["setup_completed"]


class SchoolYearSerializer(serializers.ModelSerializer[SchoolYear]):
    class Meta:
        model = SchoolYear
        fields = ["id", "name", "start_date", "end_date", "is_active"]
        read_only_fields = ["is_active"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": "Bitiş tarihi başlangıçtan sonra olmalıdır."}
            )
        return attrs


class SchoolTermSerializer(serializers.ModelSerializer[SchoolTerm]):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = SchoolTerm
        fields = ["id", "school_year", "sequence", "name", "start_date", "end_date"]
        read_only_fields = fields


class SchoolTermConfigurationSerializer(serializers.Serializer[dict[str, Any]]):
    first_term_end = serializers.DateField()
    second_term_start = serializers.DateField()


class HolidaySerializer(serializers.ModelSerializer[Holiday]):
    class Meta:
        model = Holiday
        fields = ["id", "name", "start_date", "end_date", "kind", "is_estimated"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "Bitiş tarihi başlangıçtan önce olamaz."}
            )
        return attrs


class PersonnelSerializer(serializers.ModelSerializer[Personnel]):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Personnel
        fields = ["id", "first_name", "last_name", "title", "branch", "full_name"]


class ClassResponsibilitySerializer(serializers.ModelSerializer[ClassResponsibility]):
    school_year_name = serializers.CharField(source="school_year.name", read_only=True)
    class_label = serializers.CharField(read_only=True)
    class_teacher_detail = PersonnelSerializer(source="class_teacher", read_only=True)
    assistant_principal_detail = PersonnelSerializer(source="assistant_principal", read_only=True)
    guidance_teacher_detail = PersonnelSerializer(source="guidance_teacher", read_only=True)

    class Meta:
        model = ClassResponsibility
        validators: list[Any] = []
        fields = [
            "id",
            "school_year",
            "school_year_name",
            "class_level",
            "class_section",
            "class_label",
            "class_teacher",
            "class_teacher_detail",
            "assistant_principal",
            "assistant_principal_detail",
            "guidance_teacher",
            "guidance_teacher_detail",
        ]

    def validate_class_level(self, value: int) -> int:
        if not (9 <= value <= 12):
            raise serializers.ValidationError("Sınıf 9-12 aralığında olmalıdır.")
        return value

    def validate_class_section(self, value: str) -> str:
        normalized = normalize._ascii_upper(value.strip())
        if not normalized:
            raise serializers.ValidationError("Şube zorunludur.")
        return normalized

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance if isinstance(self.instance, ClassResponsibility) else None
        year = attrs.get("school_year", getattr(instance, "school_year", None))
        level = attrs.get("class_level", getattr(instance, "class_level", None))
        section = attrs.get("class_section", getattr(instance, "class_section", ""))
        if year is not None and level is not None and section:
            duplicate = ClassResponsibility.objects.filter(
                school_year=year,
                class_level=level,
                class_section=section,
            )
            if instance is not None:
                duplicate = duplicate.exclude(pk=instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError(
                    {"class_section": "Bu ders yılı ve şube için eşleştirme zaten var."}
                )
        return attrs


class StudentSerializer(serializers.ModelSerializer[Student]):
    full_name = serializers.CharField(read_only=True)
    class_label = serializers.CharField(read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "tckn",
            "first_name",
            "last_name",
            "full_name",
            "student_number",
            "class_level",
            "class_section",
            "class_label",
            "birth_date",
            "gender",
            "status",
            "guardian_name",
            "guardian_kinship",
            "guardian_phone",
            "guardian_phone2",
            "guardian_address",
        ]

    def validate_tckn(self, value: str) -> str:
        if not value.strip():
            return ""
        normalized = normalize.normalize_tckn(value)
        if normalized is None:
            raise serializers.ValidationError("Geçersiz TCKN (11 hane + doğrulama).")
        return normalized

    def validate_class_level(self, value: int | None) -> int | None:
        if value is not None and not (9 <= value <= 12):
            raise serializers.ValidationError("Sınıf 9-12 aralığında olmalıdır.")
        return value

    def validate_class_section(self, value: str) -> str:
        # İçe aktarmayla aynı katlama: Türkçe harf → ASCII büyük ('ş' → 'S').
        if not value.strip():
            return ""
        return normalize._ascii_upper(value.strip())

    def _validate_phone(self, value: str, label: str) -> str:
        if not value.strip():
            return ""
        normalized = normalize.normalize_phone(value)
        if normalized is None:
            raise serializers.ValidationError(f"{label} geçersiz (05XXXXXXXXX bekleniyor).")
        return normalized

    def validate_guardian_phone(self, value: str) -> str:
        return self._validate_phone(value, "Veli telefonu")

    def validate_guardian_phone2(self, value: str) -> str:
        return self._validate_phone(value, "İkinci veli telefonu")


class ImportRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """İçe aktarma girdisi: xlsx dosyası VEYA pano metni (tam olarak biri)."""

    file = serializers.FileField(required=False)
    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        has_file = attrs.get("file") is not None
        has_text = bool(str(attrs.get("text", "")).strip())
        if has_file == has_text:  # ikisi birden veya hiçbiri
            raise serializers.ValidationError(
                "Dosya (file) veya yapıştırılan metin (text) alanlarından tam olarak biri gerekli."
            )
        return attrs


class HolidaySeedRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Tatil seed isteği — yıl verilmezse aktif ders yılı kullanılır."""

    school_year = serializers.IntegerField(required=False, allow_null=True)
