# Kullanıcı kararı 14.11.2026 — S11a: ders yılı başına KALICI dosya numarası sayacı.
#
# Dosya numarası ("{ders yılı adı}-NNNN") eskiden mevcut dosyaların en büyüğünden
# türetiliyordu; md. 157/7 imhası hard-delete olduğundan imha edilen SON dosyanın
# numarası bir sonraki dosyaya yeniden veriliyordu. Sayaç yalnız ileri gider.
#
# Veri göçü: her ders yılı (soft-delete edilmişler dahil) için sayaç = o yılın adını
# önek alan mevcut dosyalardaki (soft-delete edilmiş dosyalar DAHİL) en büyük NNNN;
# dosya yoksa 0. Daha önce imha edilmiş ve numarası zaten yeniden verilmiş dosyalar
# geri getirilemez — göç yalnız bundan sonrasını güvenceye alır.
# Yalnız düz alanlar okunur (`case_no`, `name`): parola kuruluysa açılışta (migrate
# anında) şifreleme anahtarı henüz yüklü değildir; şifreli alana dokunulmaz.
# Geri alma: sayaç tablosu düşer; dosyalar ve numaraları olduğu gibi kalır. DİKKAT —
# ters göçte sayaç BİLGİSİ kaybolur: yeniden ileri göçte sayaç yine mevcut dosyalardaki
# en büyük numaradan kurulur, yani S11a'dan sonra imha edilmiş SON dosyaların numaraları
# (tabloda izi kalmadığından) yeniden verilebilir. Normal kullanımda ters göç koşmaz
# (açılışta yalnız `migrate --no-input`); risk yalnız elle sürüm düşürüp yükseltmededir.

import re

import django.db.models.deletion
from django.db import migrations, models


def _fill_counters(apps, schema_editor):
    year_model = apps.get_model("okul", "SchoolYear")
    case_model = apps.get_model("disiplin", "DisciplineCase")
    counter_model = apps.get_model("disiplin", "CaseNumberCounter")

    # Tarihsel modelde soft-delete yöneticisi yoktur: `objects` silinmişleri de görür.
    case_numbers = list(case_model.objects.values_list("case_no", flat=True))
    for year_id, name in year_model.objects.values_list("pk", "name"):
        pattern = re.compile(rf"^{re.escape(name)}-(\d{{4}})$")
        last_seq = 0
        for case_no in case_numbers:
            match = pattern.match(case_no or "")
            if match:
                last_seq = max(last_seq, int(match.group(1)))
        counter_model.objects.update_or_create(
            school_year_id=year_id, defaults={"last_seq": last_seq}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0013_appeal_previous_suspension_days"),
        ("okul", "0006_student_status_graduated"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseNumberCounter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "last_seq",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Bu ders yılında verilmiş en büyük dosya sıra numarası; imhada azalmaz.",
                        verbose_name="verilen son sıra no",
                    ),
                ),
                (
                    "school_year",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="case_number_counter",
                        to="okul.schoolyear",
                        verbose_name="ders yılı",
                    ),
                ),
            ],
            options={
                "verbose_name": "dosya numarası sayacı",
                "verbose_name_plural": "dosya numarası sayaçları",
            },
        ),
        migrations.RunPython(_fill_counters, migrations.RunPython.noop),
    ]
