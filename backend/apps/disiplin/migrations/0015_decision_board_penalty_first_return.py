# Kullanıcı kararı 14.11.2026 — S11b: md. 197'de okul kurulunun verdiği özgün ceza
# ve ilk iade tarihi saklanır.
#
# - `board_penalty_type` / `board_suspension_days`: ceza üst kurulca (onayda) ya da
#   itirazla değiştiyse okul kurulunun VERDİĞİ ceza. Mevcut kayıtlarda BOŞ bırakılır:
#   göçten önce değişmiş bir kararın özgün cezası kayıtta yoktur, uydurulmaz. Belgeler
#   alan boşken eski tahmine (onay mercii / itiraz kaydı) geri döner.
# - `first_returned_at`: kurula İADE tarihi. İlçeye sevk eskiden `returned_at`'i sevk
#   tarihiyle eziyordu. Veri göçü: iade edilmiş ve henüz sevk EDİLMEMİŞ kararlarda
#   (`returned_at` dolu, `referred_to_district` yanlış — soft-delete edilmişler dahil)
#   `first_returned_at = returned_at`; sevk edilmişlerde iade tarihi bilinemez → boş.
# Yeni alanların hiçbiri şifreli alan değildir (tarih / kısa kod / sayı); göç şifreli
# alan okumaz/yazmaz, parola kurulu kurulumda anahtar olmadan da güvenle çalışır.
# Geri alma: üç sütun düşer; `returned_at` hiç değişmediğinden veri kaybı yoktur.

from django.db import migrations, models
from django.db.models import F


def _fill_first_returned_at(apps, schema_editor):
    decision_model = apps.get_model("disiplin", "DisciplineDecision")
    # Tarihsel modelde soft-delete yöneticisi yoktur: silinmiş kararlar da dolar.
    decision_model.objects.filter(returned_at__isnull=False, referred_to_district=False).update(
        first_returned_at=F("returned_at")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0014_case_number_counter"),
    ]

    operations = [
        migrations.AddField(
            model_name="disciplinedecision",
            name="board_penalty_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("REPRIMAND", "Kınama"),
                    ("SHORT_TERM_SUSPENSION", "Okuldan kısa süreli uzaklaştırma"),
                    ("SCHOOL_CHANGE", "Okul değiştirme"),
                    ("EXPULSION", "Örgün eğitim dışına çıkarma"),
                    ("NO_PENALTY", "Ceza verilmesine yer olmadığı"),
                ],
                default="",
                help_text="Ceza üst kurulca/itirazla değiştiyse okul kurulunun verdiği özgün ceza.",
                max_length=24,
                verbose_name="okul kurulunun verdiği ceza",
            ),
        ),
        migrations.AddField(
            model_name="disciplinedecision",
            name="board_suspension_days",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Özgün ceza kısa süreli uzaklaştırmaysa kurulun verdiği gün sayısı.",
                null=True,
                verbose_name="okul kurulunun verdiği uzaklaştırma süresi (gün)",
            ),
        ),
        migrations.AddField(
            model_name="disciplinedecision",
            name="first_returned_at",
            field=models.DateField(
                blank=True,
                help_text="md. 197: kararın kurula iade edildiği tarih; ilçeye sevkte korunur.",
                null=True,
                verbose_name="kurula iade tarihi",
            ),
        ),
        migrations.AlterField(
            model_name="disciplinedecision",
            name="returned_at",
            field=models.DateField(
                blank=True,
                help_text="md. 197: SON adımın (kurula iade veya ilçe kuruluna gönderme) tarihi; iade tarihi ayrıca `first_returned_at`'te korunur.",
                null=True,
                verbose_name="iade / sevk tarihi",
            ),
        ),
        migrations.RunPython(_fill_first_returned_at, migrations.RunPython.noop),
    ]
