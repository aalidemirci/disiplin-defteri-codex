"""okulapp.org örnekleri için ÖRNEK OKUL — tamamı uydurma veri (CLAUDE.md §11 KVKK).

"Örnek Anadolu Lisesi" (Örnek ilçesi) programın kendi servisleriyle kurulur: kurulum,
2026-2027 ders yılı ve dönemleri, resmî/dini tatiller, personel ve öğrenciler, iki kurul
(Ödül ve Disiplin Kurulu + Onur Genel Kurulu / Onur Kurulu), farklı aşamalarda disiplin
dosyaları, onur belgesi teklifleri ve iki kurul toplantısı.

Kişi adları gerçek kişiyle karışmasın diye bilinçli olarak yapay seçildi: personel görev
adıyla ("Müdür YARDIMCISI", "Matematik ÖĞRETMENİ"), öğrenciler ÖRNEK / DENEME / SINAMA /
TASLAK / MİSAL soyadlarıyla. T.C. kimlik numarası girilmez. Tarihler sabittir; program
"bugün"ü kabın saatinden okur, bu yüzden süre sayaçları çekim gününe göre görünür.

Bu modül yalnız `ornek_sunucu.py` içinden, Django kurulduktan sonra çağrılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

OKUL = {
    "school_name": "Örnek Anadolu Lisesi",
    "province": "Örnek",
    "district": "Örnek",
    "principal_name": "Adı SOYADI",
}

# (ad, soyad, sınıf, şube, numara) — numaralar örnektir.
OGRENCILER: list[tuple[str, str, int, str, int]] = [
    ("Ali", "ÖRNEK", 9, "A", 101),
    ("Ayşe", "DENEME", 9, "B", 112),
    ("Mehmet", "SINAMA", 10, "A", 205),
    ("Zeynep", "TASLAK", 10, "B", 218),
    ("Emre", "MİSAL", 10, "C", 231),
    ("Elif", "ÖRNEK", 11, "A", 304),
    ("Can", "DENEME", 11, "B", 317),
    ("Deniz", "SINAMA", 11, "C", 322),
    ("Selin", "TASLAK", 12, "A", 409),
    ("Burak", "MİSAL", 12, "B", 415),
    ("Ece", "ÖRNEK", 9, "C", 127),
    ("Kerem", "DENEME", 12, "C", 428),
]

# (ad, soyad, ünvan, branş)
PERSONEL: list[tuple[str, str, str, str]] = [
    ("Müdür", "YARDIMCISI", "Müdür Yardımcısı", "Coğrafya"),
    ("Matematik", "ÖĞRETMENİ", "Öğretmen", "Matematik"),
    ("Fizik", "ÖĞRETMENİ", "Öğretmen", "Fizik"),
    ("Edebiyat", "ÖĞRETMENİ", "Öğretmen", "Türk Dili ve Edebiyatı"),
    ("Rehber", "ÖĞRETMEN", "Rehber Öğretmen", "Rehberlik"),
    ("Tarih", "ÖĞRETMENİ", "Öğretmen", "Tarih"),
]


@dataclass
class OrnekOkul:
    """Ekran çekimi ve örnek evrak adımlarının ihtiyaç duyduğu kimlikler."""

    yil: Any = None
    ogrenci: dict[str, Any] = field(default_factory=dict)
    personel: dict[str, Any] = field(default_factory=dict)
    dosya: dict[str, Any] = field(default_factory=dict)
    karar: dict[str, Any] = field(default_factory=dict)
    toplanti: dict[str, Any] = field(default_factory=dict)


def kur() -> OrnekOkul:
    """Örnek okulu programın servisleriyle kurar ve kimlikleri döndürür."""
    from apps.okul.models import Personnel, Student
    from apps.okul.services import calendar, school_year, setup, terms

    sonuc = OrnekOkul()
    setup.update_school_config(fields=OKUL)
    yil = school_year.create_school_year(
        name="2026-2027", start_date=date(2026, 9, 7), end_date=date(2027, 6, 25), activate=True
    )
    terms.configure_terms(yil, first_end=date(2027, 1, 22), second_start=date(2027, 2, 8))
    calendar.seed_holidays(yil)
    setup.mark_setup_completed()
    sonuc.yil = yil

    for ad, soyad, unvan, brans in PERSONEL:
        kisi = Personnel.objects.create(first_name=ad, last_name=soyad, title=unvan, branch=brans)
        sonuc.personel[f"{ad} {soyad}"] = kisi
    for ad, soyad, seviye, sube, no in OGRENCILER:
        ogr = Student.objects.create(
            first_name=_buyuk(ad),
            last_name=soyad,
            class_level=seviye,
            class_section=sube,
            student_number=str(no),
        )
        sonuc.ogrenci[f"{ad} {soyad}"] = ogr

    _kurullar(sonuc)
    _disiplin_dosyalari(sonuc)
    _onur_sureci(sonuc)
    return sonuc


def _buyuk(metin: str) -> str:
    """Türkçe büyük harf (e-Okul listeleri gibi): i → İ, ı → I."""
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _kurullar(o: OrnekOkul) -> None:
    from apps.disiplin import services

    p, s = o.personel, o.ogrenci
    kurul = services.create_committee(school_year_id=o.yil.pk, chair_id=p["Müdür YARDIMCISI"].pk)
    services.add_committee_member(
        kurul, member_type="TEACHER", person_id=p["Matematik ÖĞRETMENİ"].pk
    )
    services.add_committee_member(kurul, member_type="TEACHER", person_id=p["Fizik ÖĞRETMENİ"].pk)
    services.add_committee_member(
        kurul,
        member_type="STUDENT",
        person_id=s["Elif ÖRNEK"].pk,
        title="Onur kurulu ikinci başkanı",
    )
    services.add_committee_member(
        kurul, member_type="PARENT", member_name="Veli ÜYE", title="Okul-aile birliği üyesi"
    )
    services.add_committee_member(
        kurul, member_type="TEACHER", person_id=p["Tarih ÖĞRETMENİ"].pk, is_substitute=True
    )

    onur = services.create_honor_board(school_year_id=o.yil.pk, chair_id=p["Edebiyat ÖĞRETMENİ"].pk)
    temsilciler = ["Ece ÖRNEK", "Zeynep TASLAK", "Elif ÖRNEK", "Kerem DENEME"]
    for ad in temsilciler:
        services.add_general_assembly_member(
            school_year_id=o.yil.pk, student_id=s[ad].pk, effective_from=o.yil.start_date
        )
    for ad in temsilciler:
        services.add_honor_board_member(
            onur, student_id=s[ad].pk, is_second_chair=(ad == "Elif ÖRNEK")
        )


def _disiplin_dosyalari(o: OrnekOkul) -> None:
    """Dört dosya: yeni dilekçe, rehberlikte, müdür uyarısıyla kapanan, kurulda karar."""
    from apps.disiplin import services
    from apps.disiplin.models import CaseStage, PrincipalDecision

    s, p = o.ogrenci, o.personel

    # 1) Yeni dilekçe — inceleme aşamasında.
    o.dosya["dilekce"] = services.create_case(
        petition_date=date(2026, 10, 1),
        petitioner_name="Fizik ÖĞRETMENİ",
        petitioner_role="OGRETMEN",
        petitioner_user_id=p["Fizik ÖĞRETMENİ"].pk,
        summary="Laboratuvar dersinde deney malzemesine izinsiz müdahale.",
        student_ids=[s["Emre MİSAL"].pk],
    )

    # 2) Rehberlik servisine yönlendirilen dosya (md. 192/1).
    rehberlik = services.create_case(
        petition_date=date(2026, 9, 24),
        petitioner_name="Edebiyat ÖĞRETMENİ",
        petitioner_role="OGRETMEN",
        petitioner_user_id=p["Edebiyat ÖĞRETMENİ"].pk,
        summary="Ders sırasında sınıf düzenini bozan davranışlar.",
        student_ids=[s["Can DENEME"].pk],
    )
    services.add_event(
        rehberlik,
        CaseStage.GUIDANCE_REFERRED,
        date(2026, 9, 25),
        assigned_guidance_name="Rehber ÖĞRETMEN",
    )
    o.dosya["rehberlik"] = rehberlik

    # 3) Müdür yazılı uyarısıyla kapanan dosya (md. 157/7).
    uyari = services.create_case(
        petition_date=date(2026, 9, 15),
        petitioner_name="Müdür YARDIMCISI",
        petitioner_role="IDARE",
        summary="Okula geç gelme ve derse geç girme.",
        student_ids=[s["Ayşe DENEME"].pk],
    )
    _rehberlikten_gecir(uyari, date(2026, 9, 16), date(2026, 9, 17))
    services.issue_warning(
        uyari,
        student_id=s["Ayşe DENEME"].pk,
        warning_date=date(2026, 9, 18),
        summary="Okula geç gelme davranışının tekrarlanmaması için uyarıldı.",
    )
    services.add_event(
        uyari,
        CaseStage.DECIDED,
        date(2026, 9, 18),
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    o.dosya["uyari"] = uyari

    # 4) Kurula sevkli dosya: kurul kararı onaylandı, tebliğ edildi (itiraz süresi işliyor);
    #    aynı dosyada ikinci öğrencinin kararı müdür onayı bekliyor.
    kurul = services.create_case(
        petition_date=date(2026, 9, 21),
        petitioner_name="Matematik ÖĞRETMENİ",
        petitioner_role="OGRETMEN",
        petitioner_user_id=p["Matematik ÖĞRETMENİ"].pk,
        summary="Teneffüste arkadaşına fiziksel müdahale ve sınıf eşyasına zarar.",
        student_ids=[s["Mehmet SINAMA"].pk, s["Burak MİSAL"].pk],
    )
    _rehberlikten_gecir(kurul, date(2026, 9, 21), date(2026, 9, 22))
    services.add_event(
        kurul,
        CaseStage.DECIDED,
        date(2026, 9, 22),
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    karar = services.record_decision(
        kurul,
        student_id=s["Mehmet SINAMA"].pk,
        penalty_type="REPRIMAND",
        decision_date=date(2026, 9, 29),
        penalty_detail=(
            "Öğrencinin savunması alınmış; olayın tanık ifadeleriyle sabit olduğu, "
            "öğrencinin daha önce disiplin cezası almadığı göz önünde bulundurulmuştur."
        ),
    )
    # Kurul toplantısı (md. 191): şikâyetçi Matematik öğretmeni kurula katılamaz (md. 191/2),
    # yerine yedek üye çağrılır; yeter sayı başkan dahil 5 kişiden en az 3.
    from apps.disiplin.selectors import get_active_committee
    from apps.disiplin.services.decisions import update_decision_narrative

    uyeler = {m.member_name: m.pk for m in get_active_committee().members.all()}
    services.record_meeting(
        kurul,
        meeting_date=date(2026, 9, 29),
        attendee_member_ids=[
            uyeler["Fizik ÖĞRETMENİ"],
            uyeler["Tarih ÖĞRETMENİ"],
            uyeler[s["Elif ÖRNEK"].full_name],
            uyeler["Veli ÜYE"],
        ],
        notes="Şikâyetçi üye yerine yedek üye katıldı (md. 191/2).",
    )
    update_decision_narrative(
        karar,
        fields={
            "incident_place": "Okul bahçesi",
            "incident_date": date(2026, 9, 18),
            "boarding_status": "Gündüzlü",
            "academic_standing": "Orta",
            "health_status": "Bilinen bir sağlık sorunu yok",
            "family_economic_status": "Orta",
            "lives_with_family": "Evet",
            "parents_alive": "Evet",
            "parents_biological": "Evet",
            "studies_near_family": "Evet",
            "upbringing_environment": "Şehir merkezi",
            "family_residence_area": "Okula yakın mahalle",
            "prior_penalties_summary": "Daha önce disiplin cezası almamıştır.",
            "accused_statement_summary": (
                "Öğrenci savunmasında arkadaşıyla tartıştığını, itişmenin anlık geliştiğini "
                "ve pişman olduğunu belirtti."
            ),
            "witness_statement_summary": (
                "İki tanık, tartışmanın sözlü başladığını ve kısa sürede itişmeye "
                "dönüştüğünü ifade etti."
            ),
            "mitigating_aggravating": "İlk kez disiplin olayına karışması ve pişmanlığı.",
            "committee_opinion": (
                "Davranışın md. 164 kapsamında kınama cezasını gerektirdiği oy birliğiyle "
                "kararlaştırıldı."
            ),
        },
    )
    services.set_decision_approval(karar, approval_status="APPROVED", approved_on=date(2026, 9, 30))
    services.notify_decision(karar, notified_on=date(2026, 10, 1), notification_method="Elden")
    o.karar["kinama"] = karar
    o.karar["onay_bekleyen"] = services.record_decision(
        kurul,
        student_id=s["Burak MİSAL"].pk,
        penalty_type="SHORT_TERM_SUSPENSION",
        suspension_days=2,
        decision_date=date(2026, 10, 2),
        penalty_detail=(
            "Olayın başlatıcısı olduğu, sınıf eşyasına verilen zararın tutanakla tespit "
            "edildiği göz önünde bulundurulmuştur."
        ),
    )
    o.dosya["kurul"] = kurul


def _rehberlikten_gecir(dosya: Any, sevk: date, donus: date) -> None:
    """md. 192/1: disiplin konusu önce rehberlik servisine intikal eder; rapor müdüre döner."""
    from apps.disiplin import services
    from apps.disiplin.models import CaseStage

    services.add_event(
        dosya, CaseStage.GUIDANCE_REFERRED, sevk, assigned_guidance_name="Rehber ÖĞRETMEN"
    )
    services.add_event(
        dosya,
        CaseStage.GUIDANCE_RETURNED,
        donus,
        guidance_outcome=(
            "Öğrenciyle ve velisiyle görüşüldü; kişilik ve sosyal durumuna ilişkin rapor "
            "okul müdürüne sunuldu."
        ),
    )


def _onur_sureci(o: OrnekOkul) -> None:
    """Teklifler → Onur Kurulu toplantısı (uygun görüş) → ÖDK toplantısı (kabul/bekleyen)."""
    from apps.disiplin import services
    from apps.okul.models import SchoolTerm

    s = o.ogrenci
    donem = SchoolTerm.objects.get(school_year=o.yil, sequence=1)
    teklifler = {}
    for ad, kriter, gerekce, teklif_eden in (
        (
            "Selin TASLAK",
            "SOCIAL_RESPONSIBILITY",
            "Okulun yaşlılar evi ziyareti projesinde gönüllü koordinatörlük yaptı.",
            "Rehber ÖĞRETMEN",
        ),
        (
            "Deniz SINAMA",
            "ACHIEVEMENT",
            "Bilim fuarındaki projesiyle il birinciliği aldı; ekibine liderlik etti.",
            "Fizik ÖĞRETMENİ",
        ),
        (
            "Ece ÖRNEK",
            "LANGUAGE",
            "Okul gazetesinde Türkçeyi doğru ve etkili kullanarak örnek oldu.",
            "Edebiyat ÖĞRETMENİ",
        ),
        (
            "Ali ÖRNEK",
            "ATTENDANCE",
            "Dönem boyunca devamsızlığı yok; arkadaşlarına örnek oldu.",
            "Matematik ÖĞRETMENİ",
        ),
        (
            "Zeynep TASLAK",
            "MANNERS",
            "Sınıf içi iletişimde ve görgü kurallarında örnek davranışlar sergiledi.",
            "Edebiyat ÖĞRETMENİ",
        ),
    ):
        teklifler[ad] = services.propose_honor_certificate(
            student_id=s[ad].pk,
            proposer_role="TEACHER",
            school_term_id=donem.pk,
            criteria=[kriter],
            justification=gerekce,
            proposer_name=teklif_eden,
        )

    # Onur Kurulu toplantısı (md. 183/b): dört teklif uygun görülür, biri görülmez.
    onur = services.create_council_meeting(
        school_year_id=o.yil.pk,
        council_type="HONOR",
        meeting_date=date(2026, 9, 28),
        attendees=services.prefill_attendees("HONOR"),
        agenda="Eylül ayı onur belgesi tekliflerinin görüşülmesi.",
        honor_certificate_ids=[teklifler[a].pk for a in teklifler if a != "Ali ÖRNEK"],
    )
    for madde in onur.agenda_items.all():
        if madde.honor_certificate_id == teklifler["Zeynep TASLAK"].pk:
            services.decide_agenda_item(
                madde,
                outcome="UNFAVORABLE",
                decision_text="Teklif somut bir faaliyetle desteklenmedi; dönem sonunda yeniden değerlendirilebilir.",
                decision_basis="MAJORITY",
                dissent_note="Kerem DENEME: davranışın sınıf içinde sürekli gözlendiği kanaatindeyim.",
            )
        else:
            services.decide_agenda_item(madde, outcome="FAVORABLE")
    o.toplanti["onur"] = onur

    # Ödül ve Disiplin Kurulu toplantısı (md. 161/1): iki kabul, biri karar bekliyor.
    odk = services.create_council_meeting(
        school_year_id=o.yil.pk,
        council_type="DISCIPLINE",
        meeting_date=date(2026, 10, 2),
        attendees=services.prefill_attendees("DISCIPLINE"),
        agenda="Onur Kurulundan gelen onur belgesi önerilerinin görüşülmesi.",
        honor_certificate_ids=[
            teklifler["Ece ÖRNEK"].pk,
            teklifler["Selin TASLAK"].pk,
            teklifler["Deniz SINAMA"].pk,
        ],
    )
    for madde in odk.agenda_items.all():
        if madde.honor_certificate_id != teklifler["Ece ÖRNEK"].pk:
            services.decide_agenda_item(madde, outcome="FAVORABLE")
    o.toplanti["odk"] = odk
    o.dosya["teklif_ali"] = teklifler["Ali ÖRNEK"]
