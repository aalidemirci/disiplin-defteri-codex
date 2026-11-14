# Kullanıcı kararı 14.11.2026 — S11c: EK-1 "önceki cezalar" özeti için "özet güncel
# değil — yeniden derle" uyarısı.
#
# `prior_penalties_compiled`: özetin (`prior_penalties_summary`) DERLENDİĞİ andaki
# otomatik derlemenin karar NO'SUZ imzası (satır başına "gg.aa.yyyy — Ceza türü").
# Bayatlık "güncel imza ≠ bu iz" ile ölçülür; kullanıcının özet metnindeki serbest
# düzenleme izi değiştirmediği için bayat sayılmaz, önceki karara sonradan numara
# atanması da (iz numara taşımadığından) bayatlatmaz.
#
# Veri göçü (soft-delete edilmiş kararlar dahil): mevcut kayıtlarda derleme anındaki
# çıktı ayrıca saklanmamıştır; iz saklı ÖZETTEN geri kurulur:
#   - Bir satır ancak "gg.aa.yyyy — <ceza türü etiketi>[ (karar no …)]" kalıbına TAM
#     uyuyorsa (ya da göç anındaki dondurulmuş derlemenin bir satırıyla birebir aynıysa)
#     OTOMATİK DERLEME SATIRI sayılır. Tarihle başlayan ama ceza etiketiyle bitmeyen
#     satır ("12.03.2026 — veliyle görüşüldü") ya da yerinde düzeltilmiş otomatik satır
#     ("… — Kınama (3 gün)") kullanıcı metnidir.
#   - Otomatik satır varsa iz = o satırların imzası. Hiç düzenlenmemiş özet bugünkü
#     durumdan farklıysa haklı olarak bayat görünür; altına yalnız "genel durum"
#     eklenmiş özet bayat görünmez. Tarihi kararın tarihinden SONRA olan otomatik
#     satırlar ize ALINMAZ: eski derleme tarih süzgeci kullanmıyordu, yenisi yalnız
#     karar tarihine kadarki cezaları derler — bu satırlar ize girseydi hiç dokunulmamış
#     eski özet, tek bir ceza değişmeden "bayat" görünürdü.
#   - Özet doluysa ama otomatik satır yoksa (kullanıcı kendi cümlesiyle yazmış) derleme
#     anı bilinemez: elle düzenleme bayat SAYILMASIN diye iz, GÖÇ ANINDAKİ derlemeyle
#     doldurulur (bugün güncel kabul edilir; sonraki değişiklik uyarı üretir).
#   - Özet boşsa iz boş kalır (derlendiğinde önceki ceza yoktu).
# Bilinen sınır: kullanıcı otomatik satırların yalnız BİR KISMINI silmiş/yeniden yazmışsa
# iz kalan otomatik satırlardan kurulur ve göçten sonra bir kez yersiz uyarı çıkabilir
# (uyarı veri değiştirmez; yeniden derleme kullanıcı onayı ister).
# Göç anındaki derleme bu dosyada DONDURULMUŞ bir kopyadır (`_compile_frozen` —
# `selectors.compile_prior_penalties(signature=True)` 14.11.2026 hâli: yürürlükteki
# cezalar, karar tarihinden önce ya da aynı gün + daha önce kaydedilmiş); canlı iş
# kuralı kodu çağrılmaz.
# Göç kullanıcının özet metnine dokunmaz. Yeni alan şifreli alan DEĞİLDİR ve göç
# hiçbir şifreli alanı okumaz/yazmaz (`values_list` + `update`; okunan sütunlar düz
# metin/tarih/kod): parola kurulu kurulumda anahtar olmadan, açılıştaki
# `migrate --no-input` içinde güvenle çalışır (kilitli kip testi:
# `test_s11_gocleri_kilitli_kipte_sifreli_alana_dokunmadan_kosar`).
# Geri alma: sütun düşer; özet metinleri hiç değişmediğinden veri kaybı yoktur.

import re
from datetime import date

from django.db import migrations, models
from django.db.models import Q

#: Tarihle başlayan satır: "22.05.2026 — Kınama" / "… — Kınama (karar no 2025-2026/0003)".
#: Otomatik sayılması için ayrıca 2. grubun bir ceza etiketi olması gerekir.
_DATED_LINE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4}) — (.+?)(?: \(karar no .*\))?$")


def _compile_frozen(apps, student_id, case_id, on, created_at, pk):
    """Öğrencinin bu karardan ÖNCEKİ yürürlükteki cezalarının imzası (dondurulmuş kopya)."""
    decision_model = apps.get_model("disiplin", "DisciplineDecision")
    appeal_model = apps.get_model("disiplin", "DisciplineAppeal")
    overturned = appeal_model._base_manager.filter(
        result="OVERTURNED", deleted_at__isnull=True
    ).values_list("decision_id", flat=True)
    earlier = Q(decision_date__lt=on) | (
        Q(decision_date=on) & (Q(created_at__lt=created_at) | Q(created_at=created_at, pk__lt=pk))
    )
    prior = (
        decision_model._base_manager.filter(
            earlier,
            deleted_at__isnull=True,
            student_id=student_id,
            approval_status="APPROVED",
            penalty_removed_on__isnull=True,
        )
        .exclude(case_id=case_id)
        .exclude(penalty_type="NO_PENALTY")
        .exclude(pk__in=overturned)
        .order_by("decision_date", "created_at", "pk")
    )
    labels = dict(decision_model._meta.get_field("penalty_type").choices)
    return [
        f"{d_date:%d.%m.%Y} — {labels.get(penalty, penalty)}"
        for d_date, penalty in prior.values_list("decision_date", "penalty_type")
    ]


def _auto_lines(summary, decision_date, labels, frozen):
    """Özetteki otomatik derleme satırları: (bulundu mu, ize girecek imza satırları)."""
    found = False
    kept = []
    for raw in summary.splitlines():
        match = _DATED_LINE.match(raw.strip())
        if match is None:
            continue
        day, month, year, label = match.groups()
        signature = f"{day}.{month}.{year} — {label}"
        if label not in labels and signature not in frozen:
            continue  # tarihle başlayan kullanıcı cümlesi / yerinde düzeltilmiş satır
        try:
            line_date = date(int(year), int(month), int(day))
        except ValueError:
            continue  # geçersiz tarih: otomatik derleme üretmiş olamaz
        found = True
        if line_date <= decision_date:
            kept.append(signature)
    return found, kept


def _fill_compiled(apps, schema_editor):
    decision_model = apps.get_model("disiplin", "DisciplineDecision")
    labels = {str(label) for _value, label in decision_model._meta.get_field("penalty_type").choices}
    # `_base_manager`: soft-delete süzgeci ne olursa olsun bütün satırlar dolar.
    manager = decision_model._base_manager
    rows = list(
        manager.exclude(prior_penalties_summary="").values_list(
            "pk", "prior_penalties_summary", "student_id", "case_id", "decision_date", "created_at"
        )
    )
    for pk, summary, student_id, case_id, decision_date, created_at in rows:
        frozen = _compile_frozen(apps, student_id, case_id, decision_date, created_at, pk)
        found, kept = _auto_lines(summary, decision_date, labels, frozen)
        compiled = "\n".join(kept if found else frozen)
        if compiled:
            manager.filter(pk=pk).update(prior_penalties_compiled=compiled)


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0015_decision_board_penalty_first_return"),
    ]

    operations = [
        migrations.AddField(
            model_name="disciplinedecision",
            name="prior_penalties_compiled",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Özetin son derlendiği andaki otomatik derleme; 'özet güncel değil' uyarısı güncel derlemeyle bunun farkından doğar. Evraka basılmaz.",
                verbose_name="önceki cezalar — derleme izi",
            ),
        ),
        migrations.RunPython(_fill_compiled, migrations.RunPython.noop),
    ]
