# Kullanıcı kararı 20.11.2026 — kurul kararı aşaması kendiliğinden ilerler.
#
# Eski sürümde "Kurul kararı" (COMMITTEE_DONE) aşama olayı elle, dosya düzeyinde ikinci bir
# karar tipi + metniyle girilirdi. Girilmeyen dosyada kararlar kesinleşmiş olsa da aşama
# "Müdür değerlendirmesi / sevk"te (DECIDED) kalıyor, "Dosyayı kapat" düğmesi görünmüyordu.
# Yeni sürümde bütün öğrencilerin kararı girilince olay kendiliğinden yazılır
# (`services.cases.advance_to_committee_done`); bu veri göçü aynı kuralı TAKILI KALMIŞ eski
# dosyalara bir kez uygular:
#   açık (closed_at boş), silinmemiş, aşaması DECIDED ve hakkında işlem yapılan HER
#   öğrencinin canlı (silinmemiş) kararı olan dosyaya COMMITTEE_DONE olayı eklenir; olay
#   tarihi en geç kararın tarihidir (son müdür kararı olayından önce olamaz).
#
# Göç yalnız DÜZ alanları okur / yazar (aşama, tarih, öğrenci, silinme damgası, olay notu);
# şifreli alana dokunmaz — parola kurulu kurulumda açılıştaki `migrate --no-input` içinde
# anahtar olmadan güvenle çalışır. Geri alma: eklenen olaylar silinmez, aşama geri alınmaz
# (no-op) — kayıt doğru aşamayı gösterir; gerekirse uygulamadaki "aşamayı geri al" kullanılır.

from django.db import migrations
from django.utils import timezone

# services.cases.AUTO_COMMITTEE_DONE_NOTE ile AYNI metin (göç uygulama kodunu içe aktarmaz).
_NOTE = (
    "Hakkında işlem yapılan bütün öğrencilerin kurul kararı girildi; aşama kendiliğinden "
    "ilerledi."
)


def forward(apps, schema_editor):  # type: ignore[no-untyped-def]
    Case = apps.get_model("disiplin", "DisciplineCase")
    CaseStudent = apps.get_model("disiplin", "DisciplineCaseStudent")
    Decision = apps.get_model("disiplin", "DisciplineDecision")
    Event = apps.get_model("disiplin", "DisciplineEvent")
    today = timezone.localdate()

    candidates = Case.objects.filter(
        current_stage="DECIDED", closed_at__isnull=True, deleted_at__isnull=True
    )
    for case in candidates:
        accused = set(
            CaseStudent.objects.filter(case_id=case.pk).values_list("student_id", flat=True)
        )
        rows = list(
            Decision.objects.filter(case_id=case.pk, deleted_at__isnull=True).values_list(
                "student_id", "decision_date"
            )
        )
        decided = {student_id for student_id, _on in rows}
        if not accused or not accused <= decided:
            continue
        event_date = max(on for _sid, on in rows)
        previous = (
            Event.objects.filter(case_id=case.pk, stage="DECIDED", deleted_at__isnull=True)
            .order_by("-recorded_at", "-id")
            .first()
        )
        if previous is not None and event_date < previous.event_date <= today:
            event_date = previous.event_date
        Event.objects.create(
            case_id=case.pk,
            stage="COMMITTEE_DONE",
            event_date=event_date,
            notes=_NOTE,
        )
        Case.objects.filter(pk=case.pk).update(current_stage="COMMITTEE_DONE")


class Migration(migrations.Migration):

    dependencies = [
        ("disiplin", "0019_decision_first_penalty"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
