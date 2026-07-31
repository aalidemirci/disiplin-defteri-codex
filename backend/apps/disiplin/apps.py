"""`disiplin` app yapılandırması — disiplin soruşturma/kurul süreci (iskelet)."""

from django.apps import AppConfig


class DisiplinConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.disiplin"
    verbose_name = "Disiplin"
