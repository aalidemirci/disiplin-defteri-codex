"""`okul` app yapılandırması — okul künyesi, öğrenci/personel sicili (iskelet)."""

from django.apps import AppConfig


class OkulConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.okul"
    verbose_name = "Okul (Sicil)"
