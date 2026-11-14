# Kullanıcı kararı 14.11.2026 — S7: VEKÂLET KAYDI ("başkan katılmadı, yerine … başkanlık
# etti" — md. 188, 191/2).
#
# - `DisciplineMeeting.chair_absent` + `acting_chair`: dosya toplantısında başkanın
#   katılmadığı ve kurula başkanlık eden öğretmen üye.
# - `CouncilMeeting.chair_absent`: Ödül ve Disiplin Kurulu toplantısında (karar defteri)
#   aynı kayıt; başkanlık eden kişi `is_chair` işaretli katılımcı satırıdır.
#
# Yalnız şema göçüdür (veri göçü YOK): mevcut toplantılar sütun varsayılanıyla "başkan
# katıldı / vekil yok" kabul edilir. Göç hiçbir kaydı değiştirmez; eski toplantıların belge
# çıktısı da aynı kalır — TEK istisna göçten değil belge kuralından gelir: kurul başkanının
# şikâyetçi / zarar gören olduğu dosyada (md. 191/2) vekâlet kaydı yokken kurul evrakında
# başkan hanesi boş basılır ve ekranda uyarılır (`documents._signing_panel`,
# `documents._case_committee`, `services.committee.case_chair_warnings`). Yeni alanlar
# şifreli alan DEĞİLDİR ve göç hiçbir satırı okumaz/yazmaz: parola kurulu kurulumda anahtar
# olmadan, açılıştaki `migrate --no-input` içinde güvenle çalışır.
# Geri alma: üç sütun düşer; toplantı kayıtları ve katılımcıları olduğu gibi kalır (yalnız
# vekâlet bilgisi kaybolur).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0016_decision_prior_penalties_compiled"),
    ]

    operations = [
        migrations.AddField(
            model_name="councilmeeting",
            name="chair_absent",
            field=models.BooleanField(
                default=False,
                help_text="Kurul başkanı toplantıya katılmadı; öğretmen üye başkanlık etti (md. 188).",
                verbose_name="başkan katılmadı",
            ),
        ),
        migrations.AddField(
            model_name="disciplinemeeting",
            name="chair_absent",
            field=models.BooleanField(
                default=False,
                help_text="Kurul başkanı toplantıya katılmadı (md. 188, 191/2).",
                verbose_name="başkan katılmadı",
            ),
        ),
        migrations.AddField(
            model_name="disciplinemeeting",
            name="acting_chair",
            field=models.ForeignKey(
                blank=True,
                help_text="Başkanın yokluğunda kurula başkanlık eden öğretmen üye (md. 188).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="chaired_meetings",
                to="disiplin.disciplinecommitteemember",
                verbose_name="başkanlık eden üye",
            ),
        ),
    ]
