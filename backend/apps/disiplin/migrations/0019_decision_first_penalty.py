# Kullanıcı kararı 16.11.2026 — md. 197: kurula iade yazısında ilk kararın sayısı ve cezası.
#
# `DisciplineDecision.first_decision_no`, `first_penalty_type`, `first_suspension_days`,
# `first_statute_ref`: müdürün kurula iade ettiği karar başka tarihli bir toplantıya İLK KEZ
# taşınırken (ikinci görüşme — `first_decision_date` ile aynı an) düzenleme öncesi sayı, ceza,
# gün ve madde atfı. Kurula iade yazısı bunları basar.
#
# Yalnız şema göçüdür (veri göçü YOK): mevcut kayıtlar boş kalır ve boş `first_penalty_type`
# "ilk karar izi yok" demektir — 0019'dan önce taşınmış kararda ilk sayı / ceza bilinemez,
# UYDURULMAZ (iade yazısı yürürlükteki kaydı basmayı sürdürür). Yeni alanlar şifreli alan
# DEĞİLDİR ve göç hiçbir satırı okumaz/yazmaz: parola kurulu kurulumda anahtar olmadan,
# açılıştaki `migrate --no-input` içinde güvenle çalışır.
# Geri alma: dört sütun düşer; karar kayıtları olduğu gibi kalır.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disiplin', '0018_acik_kalemler'),
    ]

    operations = [
        migrations.AddField(
            model_name='disciplinedecision',
            name='first_decision_no',
            field=models.CharField(blank=True, default='', help_text='md. 197: kurula iade edilen kararın, yeniden görüşülmeden önceki sayısı.', max_length=40, verbose_name='ilk kararın sayısı'),
        ),
        migrations.AddField(
            model_name='disciplinedecision',
            name='first_penalty_type',
            field=models.CharField(blank=True, choices=[('REPRIMAND', 'Kınama'), ('SHORT_TERM_SUSPENSION', 'Okuldan kısa süreli uzaklaştırma'), ('SCHOOL_CHANGE', 'Okul değiştirme'), ('EXPULSION', 'Örgün eğitim dışına çıkarma'), ('NO_PENALTY', 'Ceza verilmesine yer olmadığı')], default='', help_text='md. 197: kurula iade edilen kararın, yeniden görüşülmeden önceki cezası.', max_length=24, verbose_name='ilk kararın cezası'),
        ),
        migrations.AddField(
            model_name='disciplinedecision',
            name='first_statute_ref',
            field=models.CharField(blank=True, default='', help_text='md. 197: kurula iade edilen kararın, yeniden görüşülmeden önceki madde atfı.', max_length=64, verbose_name='ilk kararın madde atfı'),
        ),
        migrations.AddField(
            model_name='disciplinedecision',
            name='first_suspension_days',
            field=models.PositiveSmallIntegerField(blank=True, help_text='İlk karar kısa süreli uzaklaştırmaysa gün sayısı.', null=True, verbose_name='ilk kararın uzaklaştırma süresi (gün)'),
        ),
    ]
