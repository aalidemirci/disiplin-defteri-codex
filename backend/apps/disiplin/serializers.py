"""`disiplin` DRF serializer'ları — doğrulama burada, yazma serviste.

OYS `ogrenci_isleri/serializers/` paketinin disiplin yüzeyinden UYARLANDI:
alan adları model alanlarını izler (FE api.ts eşlemesi F4'te bu yüzeye göre
güncellenir); rol/yetki alanları ve `performed_by` türevleri yok.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.disiplin.models import (
    CouncilMeeting,
    CouncilMeetingAttendee,
    DisciplineAppeal,
    DisciplineAttachment,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineDeadlineExtension,
    DisciplineDecision,
    DisciplineDecisionType,
    DisciplineEvent,
    DisciplineMeeting,
    DisciplineParticipant,
    DisciplinePrecaution,
    DisciplineWarning,
    GeneratedDocument,
    HonorBoard,
    HonorBoardMember,
    HonorCertificate,
    HonorCertificateEvent,
    HonorGeneralAssemblyMember,
)


class DecisionTypeSerializer(serializers.ModelSerializer[DisciplineDecisionType]):
    class Meta:
        model = DisciplineDecisionType
        fields = ["id", "code", "name", "description", "is_active", "sort_order"]


class EventSerializer(serializers.ModelSerializer[DisciplineEvent]):
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    committee_decision_type_name = serializers.CharField(
        source="committee_decision_type.name", read_only=True, default=None
    )

    class Meta:
        model = DisciplineEvent
        fields = [
            "id",
            "stage",
            "stage_display",
            "event_date",
            "recorded_at",
            "notes",
            "assigned_guidance_name",
            "guidance_outcome",
            "principal_decisions",
            "committee_decision_type",
            "committee_decision_type_name",
            "committee_decision_text",
            "is_override",
            "override_reason",
        ]


class AttachmentSerializer(serializers.ModelSerializer[DisciplineAttachment]):
    file_type_display = serializers.CharField(source="get_file_type_display", read_only=True)

    class Meta:
        model = DisciplineAttachment
        fields = [
            "id",
            "event",
            "original_filename",
            "file_type",
            "file_type_display",
            "file_size_bytes",
            "mime_type",
            "sha256",
            "uploaded_at",
        ]


class ParticipantSerializer(serializers.ModelSerializer[DisciplineParticipant]):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    person_type_display = serializers.CharField(source="get_person_type_display", read_only=True)

    class Meta:
        model = DisciplineParticipant
        fields = [
            "id",
            "role",
            "role_display",
            "person_type",
            "person_type_display",
            "student",
            "user",
            "external_name",
            "external_title",
            "name_snapshot",
            "notes",
        ]


class WarningSerializer(serializers.ModelSerializer[DisciplineWarning]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = DisciplineWarning
        fields = ["id", "student", "student_name", "warning_date", "summary"]


class AppealSerializer(serializers.ModelSerializer[DisciplineAppeal]):
    result_display = serializers.CharField(source="get_result_display", read_only=True)
    appeal_authority_display = serializers.CharField(
        source="get_appeal_authority_display", read_only=True
    )

    class Meta:
        model = DisciplineAppeal
        fields = [
            "id",
            "decision",
            "filed_on",
            "filed_by_role",
            "filed_by_name",
            "within_deadline",
            "appeal_authority",
            "appeal_authority_display",
            "forward_deadline",
            "forwarded_on",
            "result",
            "result_display",
            "resulted_on",
            "result_notes",
        ]
        read_only_fields = [
            "decision",
            "within_deadline",
            "appeal_authority",
            "forward_deadline",
            "forwarded_on",
            "result",
            "resulted_on",
            "result_notes",
        ]


class DecisionSerializer(serializers.ModelSerializer[DisciplineDecision]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    # OYS paritesi (F4 FE): kesinleşme durumu (Form-16/17 kilidi UI ipucu, md. 169/3-4)
    # + sicildeki doğum tarihi (EK-1 anlatı formu prefill — karara değil sicile yazılır).
    is_final = serializers.SerializerMethodField()
    student_birth_date = serializers.DateField(source="student.birth_date", read_only=True)
    penalty_type_display = serializers.CharField(source="get_penalty_type_display", read_only=True)
    approval_status_display = serializers.CharField(
        source="get_approval_status_display", read_only=True
    )
    approval_authority_display = serializers.CharField(
        source="get_approval_authority_display", read_only=True
    )
    appeals = AppealSerializer(many=True, read_only=True)

    def get_is_final(self, obj: DisciplineDecision) -> bool:
        from apps.disiplin import selectors

        final, _reason = selectors.decision_is_final(obj)
        return final

    class Meta:
        model = DisciplineDecision
        fields = [
            "id",
            "student",
            "student_name",
            "is_final",
            "student_birth_date",
            "event",
            "meeting",
            "penalty_type",
            "penalty_type_display",
            "statute_ref",
            "penalty_detail",
            "decision_no",
            "decision_date",
            "suspension_days",
            "enforcement_start_date",
            "behavior_point_deduction",
            "approval_authority",
            "approval_authority_display",
            "approval_status",
            "approval_status_display",
            "approved_at",
            "return_reason",
            "returned_at",
            "notified_at",
            "notification_method",
            "appeal_deadline",
            "e_school_processed_on",
            "is_enforced",
            "notes",
            "deleted_at",
            "appeals",
            # EK-1 anlatı + öğrenci-bağlam alanları
            "accused_statement_summary",
            "witness_statement_summary",
            "other_evidence",
            "mitigating_aggravating",
            "committee_opinion",
            "psychosocial_summary",
            "boarding_status",
            "academic_standing",
            "health_status",
            "family_economic_status",
            "lives_with_family",
            "parents_alive",
            "parents_biological",
            "studies_near_family",
            "upbringing_environment",
            "family_residence_area",
            "incident_place",
            "incident_date",
            "prior_penalties_summary",
        ]
        read_only_fields = [
            "behavior_point_deduction",
            "approval_authority",
            "approval_status",
            "approved_at",
            "return_reason",
            "returned_at",
            "notified_at",
            "notification_method",
            "appeal_deadline",
            "e_school_processed_on",
            "is_enforced",
            "deleted_at",
        ]


class ExtensionSerializer(serializers.ModelSerializer[DisciplineDeadlineExtension]):
    class Meta:
        model = DisciplineDeadlineExtension
        fields = [
            "id",
            "requested_days",
            "reason",
            "decided_on",
            "approved_by_principal",
            "approved_on",
            "original_deadline",
            "new_deadline",
            "notes",
        ]
        read_only_fields = [
            "approved_by_principal",
            "approved_on",
            "original_deadline",
            "new_deadline",
        ]


class PrecautionSerializer(serializers.ModelSerializer[DisciplinePrecaution]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = DisciplinePrecaution
        fields = [
            "id",
            "student",
            "student_name",
            "event",
            "start_date",
            "requested_days",
            "end_date",
            "process_start_deadline",
            "mne_notified",
            "extension_count",
            "status",
            "status_display",
            "lifted_on",
            "reason",
            "notes",
        ]
        read_only_fields = [
            "end_date",
            "process_start_deadline",
            "extension_count",
            "status",
            "lifted_on",
        ]


class MeetingSerializer(serializers.ModelSerializer[DisciplineMeeting]):
    attendee_names = serializers.SerializerMethodField()

    class Meta:
        model = DisciplineMeeting
        fields = ["id", "event", "meeting_date", "attendees", "attendee_names", "notes"]
        read_only_fields = ["attendees"]

    def get_attendee_names(self, obj: DisciplineMeeting) -> list[str]:
        return [a.member_name or str(a.pk) for a in obj.attendees.all()]


class CaseStudentSerializer(serializers.Serializer[Any]):
    """Dosyadaki öğrenci özeti (through tablodan düzleştirilmiş)."""

    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    class_label = serializers.CharField(read_only=True)
    student_number = serializers.CharField(read_only=True)


class CaseListSerializer(serializers.ModelSerializer[DisciplineCase]):
    current_stage_display = serializers.CharField(
        source="get_current_stage_display", read_only=True
    )
    students = serializers.SerializerMethodField()

    class Meta:
        model = DisciplineCase
        fields = [
            "id",
            "case_no",
            "petition_date",
            "petitioner_name",
            "petitioner_role",
            "summary",
            "current_stage",
            "current_stage_display",
            "closed_at",
            "students",
        ]

    def get_students(self, obj: DisciplineCase) -> list[dict[str, Any]]:
        return [CaseStudentSerializer(link.student).data for link in obj.case_students.all()]


class CaseDetailSerializer(CaseListSerializer):
    events = EventSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    close_eligible = serializers.SerializerMethodField()
    close_eligible_on = serializers.SerializerMethodField()
    close_eligible_reason = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = [
            *CaseListSerializer.Meta.fields,
            "petitioner_user",
            "petitioner_student",
            "events",
            "attachments",
            "close_eligible",
            "close_eligible_on",
            "close_eligible_reason",
        ]

    def get_close_eligible(self, obj: DisciplineCase) -> bool:
        from apps.disiplin import selectors

        eligible, _on = selectors.close_eligible(obj)
        return eligible

    def get_close_eligible_on(self, obj: DisciplineCase) -> str | None:
        from apps.disiplin import selectors

        _eligible, on = selectors.close_eligible(obj)
        return on.isoformat() if on else None

    def get_close_eligible_reason(self, obj: DisciplineCase) -> str:
        from apps.disiplin import selectors

        _eligible, _on, reason = selectors.close_eligibility_details(obj)
        return reason


class CaseCreateSerializer(serializers.Serializer[dict[str, Any]]):
    """Dosya açma isteği (create_case servisine geçirilir)."""

    petition_date = serializers.DateField()
    petitioner_name = serializers.CharField(max_length=200, allow_blank=True, default="")
    petitioner_role = serializers.CharField(max_length=20)
    summary = serializers.CharField()
    student_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    petitioner_user_id = serializers.IntegerField(required=False, allow_null=True)
    petitioner_student_id = serializers.IntegerField(required=False, allow_null=True)


class EventCreateSerializer(serializers.Serializer[dict[str, Any]]):
    """Aşama olayı isteği (add_event servisine geçirilir)."""

    stage = serializers.CharField(max_length=20)
    event_date = serializers.DateField()
    override = serializers.BooleanField(default=False)
    override_reason = serializers.CharField(required=False, allow_blank=True, default="")
    assigned_guidance_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=200
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    guidance_outcome = serializers.CharField(required=False, allow_blank=True, default="")
    principal_decisions = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )
    committee_decision_type = serializers.IntegerField(required=False, allow_null=True)
    committee_decision_text = serializers.CharField(required=False, allow_blank=True, default="")


class CommitteeMemberSerializer(serializers.ModelSerializer[DisciplineCommitteeMember]):
    member_type_display = serializers.CharField(source="get_member_type_display", read_only=True)

    class Meta:
        model = DisciplineCommitteeMember
        fields = [
            "id",
            "member_type",
            "member_type_display",
            "is_substitute",
            "order",
            "title",
            "member_user",
            "member_student",
            "member_name",
        ]


class CommitteeSerializer(serializers.ModelSerializer[DisciplineCommittee]):
    chair_name = serializers.CharField(source="chair.full_name", read_only=True)
    members = CommitteeMemberSerializer(many=True, read_only=True)

    class Meta:
        model = DisciplineCommittee
        fields = ["id", "school_year", "chair", "chair_name", "notes", "members"]


class HonorBoardMemberSerializer(serializers.ModelSerializer[HonorBoardMember]):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HonorBoardMember
        fields = [
            "id",
            "member_student",
            "assembly_member",
            "grade_level",
            "is_second_chair",
            "is_substitute",
            "order",
            "title",
            "member_name",
            "effective_from",
            "effective_until",
            "end_reason",
            "is_active",
        ]


class HonorBoardSerializer(serializers.ModelSerializer[HonorBoard]):
    chair_name = serializers.CharField(source="chair.full_name", read_only=True)
    substitute_chair_name = serializers.CharField(
        source="substitute_chair.full_name",
        read_only=True,
        default="",
    )
    members = HonorBoardMemberSerializer(many=True, read_only=True)

    class Meta:
        model = HonorBoard
        fields = [
            "id",
            "school_year",
            "chair",
            "chair_name",
            "substitute_chair",
            "substitute_chair_name",
            "notes",
            "members",
        ]


class HonorGeneralAssemblyMemberSerializer(serializers.ModelSerializer[HonorGeneralAssemblyMember]):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HonorGeneralAssemblyMember
        fields = [
            "id",
            "school_year",
            "member_student",
            "member_name",
            "class_level",
            "class_section",
            "effective_from",
            "effective_until",
            "end_reason",
            "replaced_member",
            "is_active",
        ]


class HonorCertificateEventSerializer(serializers.ModelSerializer[HonorCertificateEvent]):
    term_name = serializers.CharField(source="school_term.name", read_only=True, default=None)

    class Meta:
        model = HonorCertificateEvent
        fields = [
            "id",
            "event_type",
            "event_date",
            "school_term",
            "term_name",
            "meeting",
            "explanation",
        ]


class HonorCertificateSerializer(serializers.ModelSerializer[HonorCertificate]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    proposer_role_display = serializers.CharField(
        source="get_proposer_role_display", read_only=True
    )
    events = HonorCertificateEventSerializer(many=True, read_only=True)
    term_name = serializers.CharField(source="school_term.name", read_only=True, default=None)

    class Meta:
        model = HonorCertificate
        fields = [
            "id",
            "student",
            "student_name",
            "school_year",
            "school_term",
            "term_name",
            "status",
            "status_display",
            "proposer_role",
            "proposer_role_display",
            "proposer_name",
            "criteria",
            "justification",
            "recommended_at",
            "awarded_at",
            "principal_decided_at",
            "principal_decision_reason",
            "rejection_reason",
            "rejected_at",
            "events",
        ]
        read_only_fields = [
            "status",
            "recommended_at",
            "awarded_at",
            "principal_decided_at",
            "principal_decision_reason",
            "rejection_reason",
            "rejected_at",
        ]


class CouncilAttendeeSerializer(serializers.ModelSerializer[CouncilMeetingAttendee]):
    class Meta:
        model = CouncilMeetingAttendee
        fields = [
            "id",
            "attendee_role",
            "person_name",
            "title",
            "is_chair",
            "dissent_note",
            "order",
            "member_user",
            "member_student",
        ]


class CouncilMeetingSerializer(serializers.ModelSerializer[CouncilMeeting]):
    council_type_display = serializers.CharField(source="get_council_type_display", read_only=True)
    meeting_no_display = serializers.CharField(read_only=True)
    attendees = CouncilAttendeeSerializer(many=True, read_only=True)
    discipline_case_no = serializers.CharField(
        source="discipline_case.case_no", read_only=True, default=None
    )
    term_name = serializers.CharField(source="school_term.name", read_only=True, default=None)
    honor_meeting_kind_display = serializers.CharField(
        source="get_honor_meeting_kind_display",
        read_only=True,
    )

    class Meta:
        model = CouncilMeeting
        fields = [
            "id",
            "school_year",
            "school_term",
            "term_name",
            "council_type",
            "council_type_display",
            "meeting_no",
            "meeting_no_display",
            "meeting_date",
            "honor_meeting_kind",
            "honor_meeting_kind_display",
            "agenda",
            "decision_text",
            "decision_basis",
            "notes",
            "minutes_type",
            "discipline_case",
            "discipline_case_no",
            "attendees",
        ]
        read_only_fields = ["meeting_no", "council_type", "minutes_type", "discipline_case"]


class DecisionNarrativeSerializer(serializers.Serializer[dict[str, Any]]):
    """EK-1 anlatı/bağlam güncelleme isteği — OYS DecisionNarrativeSerializer paritesi.

    `enforcement_start_date` post-hoc set/temizlenebilir (md. 164/2 — OYS Tur 102);
    `student_birth_date` karara değil öğrenci SİCİLİNE yazılır (OYS Tur 220).
    """

    accused_statement_summary = serializers.CharField(required=False, allow_blank=True)
    witness_statement_summary = serializers.CharField(required=False, allow_blank=True)
    other_evidence = serializers.CharField(required=False, allow_blank=True)
    mitigating_aggravating = serializers.CharField(required=False, allow_blank=True)
    committee_opinion = serializers.CharField(required=False, allow_blank=True)
    psychosocial_summary = serializers.CharField(required=False, allow_blank=True)
    boarding_status = serializers.CharField(required=False, allow_blank=True, max_length=120)
    academic_standing = serializers.CharField(required=False, allow_blank=True, max_length=200)
    health_status = serializers.CharField(required=False, allow_blank=True)
    family_economic_status = serializers.CharField(required=False, allow_blank=True, max_length=200)
    lives_with_family = serializers.CharField(required=False, allow_blank=True, max_length=120)
    parents_alive = serializers.CharField(required=False, allow_blank=True, max_length=120)
    parents_biological = serializers.CharField(required=False, allow_blank=True, max_length=120)
    studies_near_family = serializers.CharField(required=False, allow_blank=True, max_length=120)
    upbringing_environment = serializers.CharField(required=False, allow_blank=True)
    family_residence_area = serializers.CharField(required=False, allow_blank=True)
    incident_place = serializers.CharField(required=False, allow_blank=True, max_length=200)
    incident_date = serializers.DateField(required=False, allow_null=True)
    prior_penalties_summary = serializers.CharField(required=False, allow_blank=True)
    enforcement_start_date = serializers.DateField(required=False, allow_null=True)
    student_birth_date = serializers.DateField(required=False, allow_null=True)


class CouncilCaseOptionSerializer(serializers.ModelSerializer[DisciplineCase]):
    """Dosya görüşme tutanağına bağlanabilecek dosya seçeneği (OYS case-options paritesi)."""

    students = serializers.SerializerMethodField()

    class Meta:
        model = DisciplineCase
        fields = ["id", "case_no", "students"]

    def get_students(self, obj: DisciplineCase) -> list[str]:
        return [link.student.full_name for link in obj.case_students.all()]


class GeneratedSubDocumentSerializer(serializers.ModelSerializer[GeneratedDocument]):
    """Alt/destekleyici evrak (okuma) — ana evrak altında listelenir (tek seviye)."""

    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )
    has_stored_pdf = serializers.SerializerMethodField()

    def get_has_stored_pdf(self, obj: GeneratedDocument) -> bool:
        return obj.stored_pdf_size > 0

    class Meta:
        model = GeneratedDocument
        fields = [
            "id",
            "student",
            "document_type",
            "document_type_display",
            "title",
            "document_no",
            "source_label",
            "source_name",
            "generated_on",
            "notes",
            "page_count",
            "has_stored_pdf",
            "stored_pdf_size",
            "stored_filename",
            "parent_document",
            "sort_order",
            "created_at",
        ]
        read_only_fields = fields


class GeneratedDocumentSerializer(serializers.ModelSerializer[GeneratedDocument]):
    """Evrak kütüğü metadatası; PDF içeriğini açığa çıkarmadan kopya varlığını bildirir."""

    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )
    has_stored_pdf = serializers.SerializerMethodField()
    sub_documents = GeneratedSubDocumentSerializer(many=True, read_only=True)

    def get_has_stored_pdf(self, obj: GeneratedDocument) -> bool:
        return obj.stored_pdf_size > 0

    class Meta:
        model = GeneratedDocument
        fields = [
            "id",
            "student",
            "document_type",
            "document_type_display",
            "title",
            "document_no",
            "source_label",
            "source_name",
            "generated_on",
            "notes",
            "page_count",
            "has_stored_pdf",
            "stored_pdf_size",
            "stored_filename",
            "parent_document",
            "sort_order",
            "deleted_at",
            "created_at",
            "sub_documents",
        ]
        read_only_fields = fields
