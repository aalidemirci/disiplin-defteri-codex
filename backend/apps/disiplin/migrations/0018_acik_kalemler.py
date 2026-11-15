# Kullanıcı kararları 15.11.2026 — S7 / S8 açık kalemleri (K5, K8, K10).
#
# - `DisciplineMeeting.absent_chair_name`, `CouncilMeeting.absent_chair_name` (K5): vekâletli
#   toplantı KAYDEDİLİRKEN o günkü kurul başkanının adı (düz metin anlık kopya).
# - `DisciplineMeeting.quorum_full` (K8): toplantı kaydedilirken kurulun üye tam sayısı;
#   yeter sayı (md. 191/1) doluysa bundan, boşsa kurulun güncel üye sayısından hesaplanır.
# - `DisciplineDecision.first_decision_date` + `first_meeting` (K10): md. 197 iadesinden
#   sonra karar başka toplantıya ilk kez taşınırken ilk görüşmenin tarihi ve toplantısı.
#
# Yalnız şema göçüdür (veri göçü YOK): mevcut kayıtlar sütun varsayılanıyla (boş / NULL)
# kalır ve boş alan her yerde "eski davranış" demektir — hiçbir kayıt kendiliğinden
# DEĞİŞTİRİLMEZ, geriye dönük ad / sayı / tarih UYDURULMAZ. Yeni alanlar şifreli alan
# DEĞİLDİR ve göç hiçbir satırı okumaz/yazmaz: parola kurulu kurulumda anahtar olmadan,
# açılıştaki `migrate --no-input` içinde güvenle çalışır.
# Geri alma: beş sütun düşer; toplantı ve karar kayıtları olduğu gibi kalır (yalnız bu
# anlık kopyalar kaybolur).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0017_meeting_chair_absence"),
    ]

    operations = [
        migrations.AddField(
            model_name="councilmeeting",
            name="absent_chair_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Vekâlet kaydedilirken o günkü kurul başkanının adı (md. 188).",
                max_length=200,
                verbose_name="katılmayan başkanın adı",
            ),
        ),
        migrations.AddField(
            model_name="disciplinedecision",
            name="first_decision_date",
            field=models.DateField(
                blank=True,
                help_text="md. 197: kurula iade edilen kararın, yeniden görüşülmeden önceki tarihi.",
                null=True,
                verbose_name="ilk görüşme (karar) tarihi",
            ),
        ),
        migrations.AddField(
            model_name="disciplinedecision",
            name="first_meeting",
            field=models.ForeignKey(
                blank=True,
                help_text="md. 197: kararın iade edilmeden önce bağlı olduğu kurul toplantısı (varsa).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="first_decisions",
                to="disiplin.disciplinemeeting",
                verbose_name="ilk görüşmenin toplantısı",
            ),
        ),
        migrations.AddField(
            model_name="disciplinemeeting",
            name="absent_chair_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Vekâletli toplantı kaydedilirken o günkü kurul başkanının adı (md. 188).",
                max_length=200,
                verbose_name="katılmayan başkanın adı",
            ),
        ),
        migrations.AddField(
            model_name="disciplinemeeting",
            name="quorum_full",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Toplantı kaydedilirken kurulun üye tam sayısı (başkan + asıl üyeler, md. 191/1).",
                null=True,
                verbose_name="toplantı anındaki üye tam sayısı",
            ),
        ),
    ]
