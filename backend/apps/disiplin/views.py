"""`disiplin` API uçları — İNCE view'lar (View → Service → Model; ORM selectors'ta).

OYS `ogrenci_isleri/views/{discipline,council,honors}.py`'den temizlenerek
taşındı: permission sınıfları + `log_access`/`_client_ip` satırları SİLİNDİ
(authsuz tek kullanıcı); URL yüzeyi ve akış AYNEN (FE api.ts F4'te bu yüzeye
bağlanır). Evrak üretim uçları (documents/generate, honor documents) F3'te.

Servis hataları (`ValueError`, `InvalidTransitionError`, `FileValidationError`)
`{code: validation_error, message}` sözleşmesine çevrilir.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.disiplin import deadlines, file_storage, honor_documents, selectors, services
from apps.disiplin import documents as doc_engine
from apps.disiplin.models import (
    AttachmentType,
    DisciplineCase,
    DisciplineDecision,
    DisciplineDecisionType,
    DocumentType,
    HonorCertificate,
    HonorCertificateStatus,
)
from apps.disiplin.serializers import (
    AppealSerializer,
    AttachmentSerializer,
    CaseCreateSerializer,
    CaseDetailSerializer,
    CaseListSerializer,
    CommitteeSerializer,
    CouncilCaseOptionSerializer,
    CouncilMeetingSerializer,
    DecisionNarrativeSerializer,
    DecisionSerializer,
    DecisionTypeSerializer,
    EventCreateSerializer,
    EventSerializer,
    ExtensionSerializer,
    GeneratedDocumentSerializer,
    HonorBoardSerializer,
    HonorCertificateSerializer,
    HonorGeneralAssemblyMemberSerializer,
    MeetingSerializer,
    ParticipantSerializer,
    PrecautionSerializer,
    WarningSerializer,
)
from apps.disiplin.services import council as council_service
from apps.disiplin.services.decisions import update_decision_narrative
from apps.disiplin.state_machine import InvalidTransitionError
from apps.okul import selectors as okul_selectors


@contextmanager
def _service_errors() -> Iterator[None]:
    """Servis hatalarını sözleşmeli 400'e çevirir (Türkçe mesaj korunur)."""
    try:
        yield
    except (ValueError, InvalidTransitionError, file_storage.FileValidationError) as exc:
        raise drf_serializers.ValidationError(str(exc)) from exc
    except DjangoValidationError as exc:
        # Model full_clean/save hataları da sözleşmeli 400'dür (500 değil).
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
        raise drf_serializers.ValidationError(detail) from exc


def _parse_date(value: Any) -> date:
    """İstek gövdesindeki tarih alanını çözer; boş/eksikse sözleşmeli 400."""
    if value in (None, ""):
        raise drf_serializers.ValidationError("Tarih alanı zorunludur.")
    result: date = drf_serializers.DateField().to_internal_value(value)
    return result


def _to_int(raw: str | None) -> int | None:
    """URL/istek kimliğini güvenle int'e çevirir — çevrilemeyen her şey None.

    `str.isdigit()` üst-simge rakamları ('²') da kabul edip int()'te patlar;
    bu yüzden dönüşümün kendisi denenir (404 sözleşmesi korunur).
    """
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def _get_case_or_404(pk: str | None) -> DisciplineCase:
    case_id = _to_int(pk)
    case = selectors.get_case(case_id) if case_id is not None else None
    if case is None:
        raise NotFound("Disiplin dosyası bulunamadı.")
    return case


def _get_decision_or_404(case: DisciplineCase, did: str) -> DisciplineDecision:
    decision_id = _to_int(did)
    decision = selectors.get_decision(case, decision_id) if decision_id is not None else None
    if decision is None:
        raise NotFound("Karar bulunamadı.")
    return decision


class DisciplineDecisionTypeViewSet(viewsets.ModelViewSet[DisciplineDecisionType]):
    """Karar tipi lookup CRUD'u (ayarlar ekranı).

    DELETE kapalıdır (OYS paritesi): karar tipi geçmiş olay/kayıtlara PROTECT
    FK ile bağlıdır — pasifleştirme `is_active=false` PATCH'iyle yapılır.
    """

    serializer_class = DecisionTypeSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self) -> Any:
        # Liste varsayılanı yalnız aktifler (`?all=1` hepsini verir); detay ve
        # güncelleme HER ZAMAN tümünü görür — aksi hâlde pasifleştirme tek yönlü
        # kapan olur ve kayıt geri açılamaz (OYS paritesi).
        if self.action == "list":
            active_only = self.request.query_params.get("all", "") != "1"
            return selectors.decision_types(active_only=active_only)
        return selectors.decision_types(active_only=False)


class DisciplineCaseViewSet(viewsets.GenericViewSet[DisciplineCase]):
    """Disiplin dosyası yaşam döngüsü — OYS aksiyon yüzeyi (evrak uçları F3'te)."""

    serializer_class = CaseListSerializer

    def get_queryset(self) -> Any:
        params = self.request.query_params
        student_raw = params.get("student", "")
        if student_raw.isdigit():
            return selectors.cases_for_student(int(student_raw))
        return selectors.all_cases(stage=params.get("stage", ""), search=params.get("search", ""))

    def list(self, request: Request) -> Response:
        qs = self.get_queryset().prefetch_related("case_students__student")
        page = self.paginate_queryset(qs)
        serializer = CaseListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request: Request) -> Response:
        req = CaseCreateSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        with _service_errors():
            case = services.create_case(**dict(req.validated_data))
        return Response(CaseDetailSerializer(case).data, status=201)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(CaseDetailSerializer(_get_case_or_404(pk)).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        allowed: dict[str, Any] = {
            k: v
            for k, v in request.data.items()
            if k in ("summary", "petitioner_name", "petitioner_role")
        }
        if "petition_date" in request.data:
            allowed["petition_date"] = _parse_date(request.data.get("petition_date"))
        with _service_errors():
            services.update_case(case, **allowed)
        return Response(CaseDetailSerializer(case).data)

    # ------------------------------------------------------------- aşama/kapanış
    @action(detail=True, methods=["post"], url_path="events")
    def events(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        req = EventCreateSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = dict(req.validated_data)
        dtype_id = data.pop("committee_decision_type", None)
        dtype = selectors.get_decision_type(dtype_id) if dtype_id else None
        stage = data.pop("stage")
        event_date = data.pop("event_date")
        with _service_errors():
            event = services.add_event(
                case, stage, event_date, committee_decision_type=dtype, **data
            )
        return Response(EventSerializer(event).data, status=201)

    @action(detail=True, methods=["post"], url_path="revert-stage")
    def revert_stage(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        with _service_errors():
            services.revert_stage(
                case,
                target_stage=str(request.data.get("target_stage", "")),
                reason=str(request.data.get("reason", "")),
            )
        return Response(CaseDetailSerializer(case).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        with _service_errors():
            services.close_case(
                case,
                override=bool(request.data.get("override", False)),
                override_reason=str(request.data.get("override_reason", "")),
            )
        return Response(CaseDetailSerializer(case).data)

    @action(detail=True, methods=["get"], url_path="close-eligibility")
    def close_eligibility(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        eligible, eligible_on, reason = selectors.close_eligibility_details(case)
        return Response(
            {
                "eligible": eligible,
                "eligible_on": eligible_on.isoformat() if eligible_on else None,
                "reason": reason,
            }
        )

    # ------------------------------------------------------------------- ekler
    @action(detail=True, methods=["post"], url_path="attachments")
    def upload_attachment(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise drf_serializers.ValidationError("Dosya (file) alanı zorunludur.")
        event_id = _to_int(str(request.data.get("event", "") or ""))
        event = selectors.get_event_for_case(case, event_id) if event_id is not None else None
        file_type = str(request.data.get("file_type", AttachmentType.OTHER))
        if file_type not in set(AttachmentType.values):
            raise drf_serializers.ValidationError("Geçersiz ek türü (file_type).")
        with _service_errors():
            attachment, is_duplicate = services.add_attachment(
                case=case,
                file_bytes=uploaded.read(),
                original_filename=uploaded.name or "ek",
                file_type=file_type,
                event=event,
            )
        data = AttachmentSerializer(attachment).data
        data["is_duplicate"] = is_duplicate
        return Response(data, status=201)

    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<aid>[0-9]+)/download")
    def download_attachment(
        self, request: Request, pk: str | None = None, aid: str = ""
    ) -> FileResponse:
        case = _get_case_or_404(pk)
        attachment = selectors.get_attachment(case, int(aid))
        if attachment is None:
            raise NotFound("Ek bulunamadı.")
        path = file_storage.absolute_path(attachment.file_path)
        if not path.exists():
            raise NotFound("Ek dosyası diskte bulunamadı.")
        return FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.mime_type,
        )

    @action(detail=True, methods=["delete"], url_path=r"attachments/(?P<aid>[0-9]+)")
    def delete_attachment(self, request: Request, pk: str | None = None, aid: str = "") -> Response:
        case = _get_case_or_404(pk)
        attachment = selectors.get_attachment(case, int(aid))
        if attachment is None:
            raise NotFound("Ek bulunamadı.")
        services.delete_attachment(attachment)
        return Response(status=204)

    # ------------------------------------------------------- toplantı/katılımcı
    @action(detail=True, methods=["get", "post"], url_path="meeting")
    def meeting(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            return Response(MeetingSerializer(selectors.meetings_for_case(case), many=True).data)
        with _service_errors():
            meeting = services.record_meeting(
                case,
                meeting_date=_parse_date(request.data.get("meeting_date")),
                attendee_member_ids=[int(i) for i in request.data.get("attendee_member_ids", [])],
                notes=str(request.data.get("notes", "")),
            )
        return Response(MeetingSerializer(meeting).data, status=201)

    @action(detail=True, methods=["get", "post"], url_path="participants")
    def participants(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            return Response(
                ParticipantSerializer(selectors.participants_for_case(case), many=True).data
            )
        raw_person = str(request.data.get("person_id", "") or "")
        with _service_errors():
            participant = services.add_participant(
                case,
                role=str(request.data.get("role", "")),
                person_type=str(request.data.get("person_type", "")),
                person_id=int(raw_person) if raw_person.isdigit() else None,
                external_name=str(request.data.get("external_name", "")),
                external_title=str(request.data.get("external_title", "")),
                notes=str(request.data.get("notes", "")),
            )
        return Response(ParticipantSerializer(participant).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"participants/(?P<prt>[0-9]+)")
    def delete_participant(
        self, request: Request, pk: str | None = None, prt: str = ""
    ) -> Response:
        case = _get_case_or_404(pk)
        participant = selectors.get_participant(case, int(prt))
        if participant is None:
            raise NotFound("Katılımcı bulunamadı.")
        with _service_errors():
            services.remove_participant(participant)
        return Response(status=204)

    @action(detail=True, methods=["get", "post"], url_path="warnings")
    def warnings(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            return Response(WarningSerializer(selectors.warnings_for_case(case), many=True).data)
        with _service_errors():
            warning = services.issue_warning(
                case,
                student_id=int(request.data.get("student", 0)),
                warning_date=_parse_date(request.data.get("warning_date")),
                summary=str(request.data.get("summary", "")),
            )
        return Response(WarningSerializer(warning).data, status=201)

    @action(detail=True, methods=["get"], url_path="triage-suggestion")
    def triage_suggestion(self, request: Request, pk: str | None = None) -> Response:
        """Dosyadaki her suçlanan için md. 157/7/166 triaj önerisi (Dal A/B)."""
        case = _get_case_or_404(pk)
        out = []
        for sid in selectors.accused_student_ids(case):
            history = selectors.student_discipline_history(sid, exclude_case_id=case.pk)
            out.append(
                {
                    "student_id": history.student_id,
                    "warning_count": history.warning_count,
                    "penalty_count": history.penalty_count,
                    "should_route_to_committee": history.should_route_to_committee,
                }
            )
        return Response(out)

    # ----------------------------------------------------------------- kararlar
    @action(detail=True, methods=["get", "post"], url_path="decisions")
    def decisions(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            # OYS zarfı (F4 FE paritesi): kararlar + öğrenci başına davranış puanı (md. 170).
            points = {
                str(link.student_id): selectors.behavior_point_for_student(link.student_id)
                for link in case.case_students.all()
            }
            return Response(
                {
                    "decisions": DecisionSerializer(
                        selectors.decisions_for_case(case), many=True
                    ).data,
                    "behavior_points": points,
                }
            )
        req = DecisionSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = dict(req.validated_data)
        student = data.pop("student")
        with _service_errors():
            decision = services.record_decision(
                case,
                student_id=student.pk,
                penalty_type=data["penalty_type"],
                decision_date=data["decision_date"],
                suspension_days=data.get("suspension_days"),
                enforcement_start_date=data.get("enforcement_start_date"),
                statute_ref=data.get("statute_ref", ""),
                penalty_detail=data.get("penalty_detail", ""),
                decision_no=data.get("decision_no", ""),
                notes=data.get("notes", ""),
            )
        return Response(DecisionSerializer(decision).data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path=r"decisions/(?P<did>[0-9]+)")
    def decision_edit_delete(
        self, request: Request, pk: str | None = None, did: str = ""
    ) -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        if request.method == "DELETE":
            with _service_errors():
                services.delete_decision(decision)
            return Response(status=204)
        # Kısmi PATCH: verilmeyen alan MEVCUT değerini korur (yalnız-not
        # güncellemesi uzaklaştırma günlerini/uygulama tarihini silmemeli).
        raw_days = request.data.get("suspension_days", decision.suspension_days)
        suspension_days = _to_int(str(raw_days)) if raw_days is not None else None
        if "enforcement_start_date" in request.data:
            raw_esd = request.data.get("enforcement_start_date")
            enforcement_start = _parse_date(raw_esd) if raw_esd else None
        else:
            enforcement_start = decision.enforcement_start_date
        with _service_errors():
            services.update_decision(
                decision,
                penalty_type=str(request.data.get("penalty_type", decision.penalty_type)),
                decision_date=_parse_date(
                    request.data.get("decision_date", decision.decision_date)
                ),
                suspension_days=suspension_days,
                enforcement_start_date=enforcement_start,
                statute_ref=str(request.data.get("statute_ref", decision.statute_ref)),
                penalty_detail=str(request.data.get("penalty_detail", decision.penalty_detail)),
                decision_no=str(request.data.get("decision_no", decision.decision_no)),
                notes=str(request.data.get("notes", decision.notes)),
            )
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/restore")
    def decision_restore(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = selectors.get_any_decision(case, int(did))
        if decision is None:
            raise NotFound("Karar bulunamadı.")
        with _service_errors():
            services.restore_decision(decision)
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["get"], url_path="decisions/deleted")
    def decisions_deleted(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        return Response(DecisionSerializer(selectors.deleted_decisions(case), many=True).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/approve")
    def decision_approve(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        approved_on = request.data.get("approved_on")
        with _service_errors():
            services.set_decision_approval(
                decision,
                approval_status=str(request.data.get("approval_status", "")),
                approved_on=(_parse_date(approved_on) if approved_on else None),
            )
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/review")
    def decision_review(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        with _service_errors():
            services.record_principal_review(
                decision,
                action=str(request.data.get("action", "")),
                reason=str(request.data.get("reason", "")),
                decided_on=_parse_date(request.data.get("decided_on")),
            )
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/notify")
    def decision_notify(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        with _service_errors():
            services.notify_decision(
                decision,
                notified_on=_parse_date(request.data.get("notified_on")),
                notification_method=str(request.data.get("notification_method", "")),
            )
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/e-school")
    def decision_e_school(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        with _service_errors():
            services.confirm_e_school_entry(
                decision,
                processed_on=_parse_date(request.data.get("processed_on")),
            )
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["post"], url_path=r"decisions/(?P<did>[0-9]+)/narrative")
    def decision_narrative(
        self, request: Request, pk: str | None = None, did: str = ""
    ) -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        req = DecisionNarrativeSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = dict(req.validated_data)
        kwargs: dict[str, Any] = {}
        if "enforcement_start_date" in data:
            kwargs["enforcement_start_date"] = data.pop("enforcement_start_date")
        if "student_birth_date" in data:
            kwargs["student_birth_date"] = data.pop("student_birth_date")
        with _service_errors():
            update_decision_narrative(decision, fields=data, **kwargs)
        return Response(DecisionSerializer(decision).data)

    @action(detail=True, methods=["get", "post"], url_path=r"decisions/(?P<did>[0-9]+)/appeals")
    def decision_appeals(self, request: Request, pk: str | None = None, did: str = "") -> Response:
        case = _get_case_or_404(pk)
        decision = _get_decision_or_404(case, did)
        if request.method == "GET":
            return Response(
                AppealSerializer(selectors.appeals_for_decision(decision), many=True).data
            )
        with _service_errors():
            appeal = services.file_appeal(
                decision,
                filed_on=_parse_date(request.data.get("filed_on")),
                filed_by_role=str(request.data.get("filed_by_role", "")),
                filed_by_name=str(request.data.get("filed_by_name", "")),
            )
        return Response(AppealSerializer(appeal).data, status=201)

    @action(detail=True, methods=["post"], url_path=r"appeals/(?P<aid>[0-9]+)/forward")
    def appeal_forward(self, request: Request, pk: str | None = None, aid: str = "") -> Response:
        case = _get_case_or_404(pk)
        appeal = selectors.get_appeal_by_id(int(aid))
        if appeal is None or appeal.decision.case_id != case.pk:
            raise NotFound("İtiraz bulunamadı.")
        with _service_errors():
            services.forward_appeal(
                appeal,
                forwarded_on=_parse_date(request.data.get("forwarded_on")),
            )
        return Response(AppealSerializer(appeal).data)

    @action(detail=True, methods=["post"], url_path=r"appeals/(?P<aid>[0-9]+)/resolve")
    def appeal_resolve(self, request: Request, pk: str | None = None, aid: str = "") -> Response:
        case = _get_case_or_404(pk)
        appeal = selectors.get_appeal_by_id(int(aid))
        if appeal is None or appeal.decision.case_id != case.pk:
            raise NotFound("İtiraz bulunamadı.")
        with _service_errors():
            services.resolve_appeal(
                appeal,
                result=str(request.data.get("result", "")),
                resulted_on=_parse_date(request.data.get("resulted_on")),
                result_notes=str(request.data.get("result_notes", "")),
            )
        return Response(AppealSerializer(appeal).data)

    # ------------------------------------------------------- uzatma/tedbir
    @action(detail=True, methods=["get", "post"], url_path="extensions")
    def extensions(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            # OYS zarfı (F4 FE paritesi): uzatmalar + kurula geliş/karar son günü (md. 192/3).
            referred_on = selectors.committee_referred_on(case)
            deadline = selectors.committee_decision_deadline(case)
            return Response(
                {
                    "extensions": ExtensionSerializer(
                        selectors.extensions_for_case(case), many=True
                    ).data,
                    "committee_referred_on": referred_on.isoformat() if referred_on else None,
                    "committee_decision_deadline": deadline.isoformat() if deadline else None,
                }
            )
        with _service_errors():
            extension = services.create_extension(
                case,
                requested_days=int(request.data.get("requested_days", 0)),
                reason=str(request.data.get("reason", "")),
                decided_on=_parse_date(request.data.get("decided_on")),
                notes=str(request.data.get("notes", "")),
            )
        return Response(ExtensionSerializer(extension).data, status=201)

    @action(detail=True, methods=["post"], url_path=r"extensions/(?P<ext>[0-9]+)/approve")
    def extension_approve(self, request: Request, pk: str | None = None, ext: str = "") -> Response:
        case = _get_case_or_404(pk)
        extension = selectors.get_extension(case, int(ext))
        if extension is None:
            raise NotFound("Süre uzatması bulunamadı.")
        with _service_errors():
            services.approve_extension(
                extension,
                approved_on=_parse_date(request.data.get("approved_on")),
            )
        return Response(ExtensionSerializer(extension).data)

    @action(detail=True, methods=["get", "post"], url_path="precautions")
    def precautions(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        if request.method == "GET":
            return Response(
                PrecautionSerializer(selectors.precautions_for_case(case), many=True).data
            )
        with _service_errors():
            precaution = services.create_precaution(
                case,
                student_id=int(request.data.get("student", 0)),
                start_date=_parse_date(request.data.get("start_date")),
                requested_days=int(request.data.get("requested_days", 0)),
                reason=str(request.data.get("reason", "")),
                mne_notified=bool(request.data.get("mne_notified", False)),
                notes=str(request.data.get("notes", "")),
            )
        return Response(PrecautionSerializer(precaution).data, status=201)

    @action(detail=True, methods=["post"], url_path=r"precautions/(?P<prc>[0-9]+)/lift")
    def precaution_lift(self, request: Request, pk: str | None = None, prc: str = "") -> Response:
        case = _get_case_or_404(pk)
        precaution = selectors.get_precaution(case, int(prc))
        if precaution is None:
            raise NotFound("Tedbir bulunamadı.")
        with _service_errors():
            services.lift_precaution(
                precaution,
                lifted_on=_parse_date(request.data.get("lifted_on")),
                expired=bool(request.data.get("expired", False)),
            )
        return Response(PrecautionSerializer(precaution).data)

    @action(detail=True, methods=["post"], url_path=r"precautions/(?P<prc>[0-9]+)/extend")
    def precaution_extend(self, request: Request, pk: str | None = None, prc: str = "") -> Response:
        case = _get_case_or_404(pk)
        precaution = selectors.get_precaution(case, int(prc))
        if precaution is None:
            raise NotFound("Tedbir bulunamadı.")
        with _service_errors():
            services.extend_precaution(
                precaution,
                additional_days=int(request.data.get("additional_days", 0)),
                mne_notified=bool(request.data.get("mne_notified", False)),
            )
        return Response(PrecautionSerializer(precaution).data)

    # ------------------------------------------------------------------ evrak
    @action(detail=True, methods=["get", "post"], url_path="documents")
    def documents(self, request: Request, pk: str | None = None) -> Response:
        """GET: evrak zaman çizelgesi (ana + alt). POST: elle/harici evrak kütüğü kaydı."""
        case = _get_case_or_404(pk)
        if request.method == "GET":
            timeline = selectors.document_timeline(case)
            return Response(GeneratedDocumentSerializer(timeline, many=True).data)
        raw_student = str(request.data.get("student", "") or "")
        raw_parent = str(request.data.get("parent_document", "") or "")
        with _service_errors():
            record = services.log_generated_document(
                case,
                document_type=str(request.data.get("document_type", "OTHER")),
                title=str(request.data.get("title", "")),
                generated_on=_parse_date(request.data.get("generated_on")),
                document_no=str(request.data.get("document_no", "")),
                student_id=_to_int(raw_student) if raw_student else None,
                source_label=str(request.data.get("source_label", "")),
                source_name=str(request.data.get("source_name", "")),
                notes=str(request.data.get("notes", "")),
                page_count=_to_int(str(request.data.get("page_count", 1))) or 1,
                parent_document_id=_to_int(raw_parent) if raw_parent else None,
            )
        return Response(GeneratedDocumentSerializer(record).data, status=201)

    @action(detail=True, methods=["post"], url_path="documents/generate")
    def documents_generate(self, request: Request, pk: str | None = None) -> FileResponse:
        """Belge üretir (WeasyPrint PDF) ve izlenebilirse kütüğe kaydeder.

        Geçici alanlar (ifade/savunma gövdesi, davranış özeti, üst kurul karar
        bilgileri) DB'ye YAZILMAZ — yalnız PDF'e basılır (no-trace; KVKK).
        """
        case = _get_case_or_404(pk)
        data = request.data
        # Dizi pusulası bu uçtan üretilmez (OYS paritesi): fihrist KAPAKTIR, kütüğe
        # yazılmaz — ayrı GET documents/index-sheet ucu log=False üretir.
        if str(data.get("document_type", "")) == DocumentType.INDEX_SHEET:
            raise drf_serializers.ValidationError(
                "Dizi pusulası bu uçtan üretilmez; GET documents/index-sheet kullanın."
            )
        raw_student = str(data.get("student", "") or "")
        raw_participant = str(data.get("participant", "") or "")
        raw_stmt_date = data.get("statement_date")
        raw_board_date = data.get("board_decision_date")
        with _service_errors():
            pdf_bytes, record = doc_engine.generate_document(
                case,
                document_type=str(data.get("document_type", "")),
                generated_on=_parse_date(data.get("generated_on")),
                recipient=str(data.get("recipient", doc_engine.RECIPIENT_STUDENT)),
                student_id=_to_int(raw_student) if raw_student else None,
                participant_id=_to_int(raw_participant) if raw_participant else None,
                statement_date=_parse_date(raw_stmt_date) if raw_stmt_date else None,
                statement_time=str(data.get("statement_time", "")),
                statement_place=str(data.get("statement_place", "")),
                statement_subject=str(data.get("statement_subject", "")),
                statement_body=str(data.get("statement_body", "")),
                behavior_summary=str(data.get("behavior_summary", "")),
                notice_kind=str(data.get("notice_kind", "")),
                board_authority=str(data.get("board_authority", "")),
                board_decision_no=str(data.get("board_decision_no", "")),
                board_decision_date=_parse_date(raw_board_date) if raw_board_date else None,
                board_outcome=str(data.get("board_outcome", "")),
                result_summary=str(data.get("result_summary", "")),
                variant=str(data.get("variant", "")),
                document_no=str(data.get("document_no", "")),
                title=str(data.get("title", "")),
                source_label=str(data.get("source_label", "")),
                # OYS paritesi (KVKK): API'den üretilen resmî belge DAİMA kütüğe
                # yazılır — istemci kapatamaz (multipart "false" tuzağı da kalkar).
                log=True,
            )
        from io import BytesIO

        filename = f"{case.case_no}-{data.get('document_type', 'belge')}.pdf"
        response = FileResponse(
            BytesIO(pdf_bytes), filename=filename, content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        if record is not None:
            response["X-Document-Id"] = str(record.pk)
        return response

    @action(detail=True, methods=["get"], url_path="documents/index-sheet")
    def documents_index_sheet(self, request: Request, pk: str | None = None) -> FileResponse:
        """Dizi pusulası (fihrist kapağı) — kütüğe YAZILMADAN üretilir (OYS paritesi)."""
        from io import BytesIO

        case = _get_case_or_404(pk)
        with _service_errors():
            pdf_bytes, _record = doc_engine.generate_document(
                case,
                document_type=DocumentType.INDEX_SHEET,
                generated_on=timezone.localdate(),
                log=False,
            )
        filename = f"{case.case_no}-dizi-pusulasi.pdf"
        response = FileResponse(
            BytesIO(pdf_bytes), filename=filename, content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    @action(detail=True, methods=["patch"], url_path="documents/reorder")
    def documents_reorder(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        raw = request.data.get("document_ids")  # OYS gövde anahtarı (FE api.ts paritesi)
        if not isinstance(raw, list) or not raw:
            raise drf_serializers.ValidationError(
                "document_ids: istenen sırada belge id listesi zorunludur."
            )
        ordered_ids = [i for i in (_to_int(str(x)) for x in raw) if i is not None]
        if len(ordered_ids) != len(raw):
            raise drf_serializers.ValidationError("document_ids yalnız sayısal id içermelidir.")
        with _service_errors():
            services.reorder_documents(case, ordered_ids=ordered_ids)
        return Response(
            GeneratedDocumentSerializer(selectors.document_timeline(case), many=True).data
        )

    @action(detail=True, methods=["get"], url_path="documents/deleted")
    def documents_deleted(self, request: Request, pk: str | None = None) -> Response:
        case = _get_case_or_404(pk)
        return Response(
            GeneratedDocumentSerializer(selectors.deleted_documents(case), many=True).data
        )

    @action(detail=True, methods=["patch", "delete"], url_path=r"documents/(?P<doc>[0-9]+)")
    def document_edit_delete(
        self, request: Request, pk: str | None = None, doc: str = ""
    ) -> Response:
        case = _get_case_or_404(pk)
        doc_id = _to_int(doc)
        record = selectors.get_document(case, doc_id) if doc_id is not None else None
        if record is None:
            raise NotFound("Belge kaydı bulunamadı.")
        if request.method == "DELETE":
            with _service_errors():
                services.delete_document(record)
            return Response(status=204)
        kwargs: dict[str, Any] = {}
        for field in ("page_count", "title", "notes", "source_label", "source_name"):
            if field not in request.data:
                continue
            value = request.data.get(field)
            if field == "page_count":
                parsed = _to_int(str(value))
                if parsed is None or parsed < 1:
                    raise drf_serializers.ValidationError(
                        "page_count 1 veya daha büyük bir sayı olmalıdır."
                    )
                kwargs[field] = parsed
            else:
                if value is not None and not isinstance(value, str):
                    raise drf_serializers.ValidationError(f"{field} metin olmalıdır.")
                kwargs[field] = value
        with _service_errors():
            services.update_document(record, **kwargs)
        return Response(GeneratedDocumentSerializer(record).data)

    @action(detail=True, methods=["post"], url_path=r"documents/(?P<doc>[0-9]+)/restore")
    def document_restore(self, request: Request, pk: str | None = None, doc: str = "") -> Response:
        case = _get_case_or_404(pk)
        doc_id = _to_int(doc)
        record = selectors.get_any_document(case, doc_id) if doc_id is not None else None
        if record is None:
            raise NotFound("Belge kaydı bulunamadı.")
        with _service_errors():
            services.restore_document(record)
        return Response(GeneratedDocumentSerializer(record).data)

    @action(detail=True, methods=["get"], url_path=r"documents/(?P<doc>[0-9]+)/download")
    def document_download(
        self, request: Request, pk: str | None = None, doc: str = ""
    ) -> FileResponse:
        """Saklanan PDF kopyasını indirir; soft-delete edilmiş evraklar da erişilebilir."""
        from io import BytesIO

        case = _get_case_or_404(pk)
        doc_id = _to_int(doc)
        record = selectors.get_any_document(case, doc_id) if doc_id is not None else None
        if record is None:
            raise NotFound("Belge kaydı bulunamadı.")
        if record.stored_pdf_size < 1 or not record.stored_pdf_b64:
            raise NotFound("Bu belge için saklanmış PDF kopyası bulunmuyor.")
        try:
            pdf_bytes = base64.b64decode(record.stored_pdf_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise drf_serializers.ValidationError(
                "Saklanan PDF kopyası okunamadı; yedekten geri yükleme gerekebilir."
            ) from exc
        if len(pdf_bytes) != record.stored_pdf_size or not pdf_bytes.startswith(b"%PDF"):
            raise drf_serializers.ValidationError(
                "Saklanan PDF kopyasının bütünlük denetimi başarısız."
            )
        filename = record.stored_filename or f"{case.case_no}-belge-{record.pk}.pdf"
        response = FileResponse(
            BytesIO(pdf_bytes), filename=filename, content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Kurul tanımı (aktif yıl) — OYS DisciplineCommitteeView yüzeyi
# ---------------------------------------------------------------------------
class DisciplineCommitteeView(APIView):
    def get(self, request: Request) -> Response:
        committee = selectors.get_active_committee()
        if committee is None:
            return Response(status=204)  # aktif yıl için kurul tanımsız
        return Response(CommitteeSerializer(committee).data)

    def post(self, request: Request) -> Response:
        with _service_errors():
            committee = services.create_committee(
                school_year_id=int(request.data.get("school_year", 0)),
                chair_id=int(request.data.get("chair", 0)),
                notes=str(request.data.get("notes", "")),
            )
        return Response(CommitteeSerializer(committee).data, status=201)


class DisciplineCommitteeChairView(APIView):
    def post(self, request: Request) -> Response:
        committee = selectors.get_active_committee()
        if committee is None:
            raise NotFound("Aktif ders yılı için disiplin kurulu yok.")
        with _service_errors():
            services.set_committee_chair(committee, int(request.data.get("chair", 0)))
        return Response(CommitteeSerializer(committee).data)


class DisciplineCommitteeMemberAddView(APIView):
    def post(self, request: Request) -> Response:
        committee = selectors.get_active_committee()
        if committee is None:
            raise NotFound("Aktif ders yılı için disiplin kurulu yok.")
        raw_person = str(request.data.get("person_id", "") or "")
        with _service_errors():
            services.add_committee_member(
                committee,
                member_type=str(request.data.get("member_type", "")),
                person_id=int(raw_person) if raw_person.isdigit() else None,
                member_name=str(request.data.get("member_name", "")),
                is_substitute=bool(request.data.get("is_substitute", False)),
                order=int(request.data.get("order", 0)),
                title=str(request.data.get("title", "")),
            )
        # Kurul selector'dan prefetch'li geldi; argümansız refresh önbelleği
        # boşaltır, aksi hâlde yanıt yeni üyeyi taşımaz (FE listeyi bununla tazeler).
        committee.refresh_from_db()
        return Response(CommitteeSerializer(committee).data, status=201)


class DisciplineCommitteeMemberRemoveView(APIView):
    def delete(self, request: Request, member_id: int) -> Response:
        committee = selectors.get_active_committee()
        if committee is None:
            raise NotFound("Aktif ders yılı için disiplin kurulu yok.")
        member = selectors.get_committee_member(committee, member_id)
        if member is None:
            raise NotFound("Kurul üyesi bulunamadı.")
        services.remove_committee_member(member)
        return Response(status=204)


# ---------------------------------------------------------------------------
# Onur kurulu + onur belgeleri (honors-lite)
# ---------------------------------------------------------------------------
class HonorBoardView(APIView):
    def get(self, request: Request) -> Response:
        board = selectors.get_active_honor_board()
        if board is None:
            return Response(status=204)  # aktif yıl için onur kurulu tanımsız
        return Response(HonorBoardSerializer(board).data)

    def post(self, request: Request) -> Response:
        with _service_errors():
            board = services.create_honor_board(
                school_year_id=int(request.data.get("school_year", 0)),
                chair_id=int(request.data.get("chair", 0)),
                substitute_chair_id=_to_int(request.data.get("substitute_chair")),
                notes=str(request.data.get("notes", "")),
            )
        return Response(HonorBoardSerializer(board).data, status=201)


class HonorBoardChairView(APIView):
    def post(self, request: Request) -> Response:
        board = selectors.get_active_honor_board()
        if board is None:
            raise NotFound("Aktif ders yılı için onur kurulu yok.")
        with _service_errors():
            services.set_honor_board_chair(board, int(request.data.get("chair", 0)))
        return Response(HonorBoardSerializer(board).data)


class HonorBoardSubstituteChairView(APIView):
    def post(self, request: Request) -> Response:
        board = selectors.get_active_honor_board()
        if board is None:
            raise NotFound("Aktif ders yılı için onur kurulu yok.")
        with _service_errors():
            services.set_honor_board_substitute_chair(
                board,
                int(request.data.get("substitute_chair", 0)),
            )
        return Response(HonorBoardSerializer(board).data)


class HonorBoardMemberAddView(APIView):
    def post(self, request: Request) -> Response:
        board = selectors.get_active_honor_board()
        if board is None:
            raise NotFound("Aktif ders yılı için onur kurulu yok.")
        with _service_errors():
            services.add_honor_board_member(
                board,
                student_id=int(request.data.get("student", 0)),
                grade_level=request.data.get("grade_level"),
                is_second_chair=bool(request.data.get("is_second_chair", False)),
                is_substitute=bool(request.data.get("is_substitute", False)),
                order=int(request.data.get("order", 0)),
                title=str(request.data.get("title", "")),
                assembly_member_id=_to_int(request.data.get("assembly_member")),
            )
        # Bkz. DisciplineCommitteeMemberAddView: bayat prefetch önbelleği boşaltılır.
        board.refresh_from_db()
        return Response(HonorBoardSerializer(board).data, status=201)


class HonorBoardMemberRemoveView(APIView):
    def delete(self, request: Request, member_id: int) -> Response:
        board = selectors.get_active_honor_board()
        if board is None:
            raise NotFound("Aktif ders yılı için onur kurulu yok.")
        member = selectors.get_honor_board_member(board, member_id)
        if member is None:
            raise NotFound("Onur kurulu üyesi bulunamadı.")
        services.remove_honor_board_member(member)
        return Response(status=204)


class HonorGeneralAssemblyView(APIView):
    def get(self, request: Request) -> Response:
        raw_year = request.query_params.get("school_year")
        school_year_id = _to_int(raw_year)
        if school_year_id is None:
            active_year = okul_selectors.active_school_year()
            if active_year is None:
                return Response([])
            school_year_id = active_year.pk
        members = selectors.honor_general_assembly_members(school_year_id=school_year_id)
        return Response(HonorGeneralAssemblyMemberSerializer(members, many=True).data)

    def post(self, request: Request) -> Response:
        raw_year = request.data.get("school_year")
        school_year_id = _to_int(raw_year)
        if school_year_id is None:
            active_year = okul_selectors.active_school_year()
            if active_year is None:
                raise NotFound("Aktif ders yılı bulunamadı.")
            school_year_id = active_year.pk
        with _service_errors():
            member = services.add_general_assembly_member(
                school_year_id=school_year_id,
                student_id=int(request.data.get("student", 0)),
                effective_from=(
                    _parse_date(request.data.get("effective_from"))
                    if request.data.get("effective_from")
                    else None
                ),
                replaced_member_id=_to_int(request.data.get("replaced_member")),
            )
        return Response(HonorGeneralAssemblyMemberSerializer(member).data, status=201)


class HonorGeneralAssemblyMemberEndView(APIView):
    def post(self, request: Request, member_id: int) -> Response:
        member = selectors.get_honor_general_assembly_member(member_id)
        if member is None:
            raise NotFound("Onur Genel Kurulu üyesi bulunamadı.")
        with _service_errors():
            services.end_general_assembly_membership(
                member,
                effective_until=(
                    _parse_date(request.data.get("effective_until"))
                    if request.data.get("effective_until")
                    else None
                ),
                reason=str(request.data.get("reason", "")),
            )
        return Response(HonorGeneralAssemblyMemberSerializer(member).data)


class HonorComplianceView(APIView):
    def get(self, request: Request) -> Response:
        raw_year = request.query_params.get("school_year")
        school_year_id = _to_int(raw_year)
        if school_year_id is None:
            active_year = okul_selectors.active_school_year()
            if active_year is None:
                raise NotFound("Aktif ders yılı bulunamadı.")
            school_year_id = active_year.pk
        return Response(selectors.honor_compliance_status(school_year_id))


class HonorCertificateViewSet(viewsets.GenericViewSet[HonorCertificate]):
    serializer_class = HonorCertificateSerializer

    def get_queryset(self) -> Any:
        params = self.request.query_params
        year_raw = params.get("school_year", "")
        term_raw = params.get("school_term", "")
        student_raw = params.get("student", "")
        return selectors.honor_certificates(
            status=params.get("status", ""),
            school_year_id=int(year_raw) if year_raw.isdigit() else None,
            school_term_id=int(term_raw) if term_raw.isdigit() else None,
            student_id=int(student_raw) if student_raw.isdigit() else None,
        )

    def list(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(HonorCertificateSerializer(page, many=True).data)

    def create(self, request: Request) -> Response:
        school_term_id = _to_int(request.data.get("school_term"))
        with _service_errors():
            certificate = services.propose_honor_certificate(
                student_id=int(request.data.get("student", 0)),
                proposer_role=str(request.data.get("proposer_role", "")),
                school_year_id=request.data.get("school_year"),
                school_term_id=school_term_id,
                criteria=request.data.get("criteria"),
                justification=str(request.data.get("justification", "")),
                proposer_name=str(request.data.get("proposer_name", "")),
            )
        return Response(HonorCertificateSerializer(certificate).data, status=201)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        certificate_id = _to_int(pk)
        certificate = (
            selectors.get_honor_certificate(certificate_id) if certificate_id is not None else None
        )
        if certificate is None:
            raise NotFound("Onur belgesi bulunamadı.")
        return Response(HonorCertificateSerializer(certificate).data)

    def _get(self, pk: str | None) -> HonorCertificate:
        certificate_id = _to_int(pk)
        certificate = (
            selectors.get_honor_certificate(certificate_id) if certificate_id is not None else None
        )
        if certificate is None:
            raise NotFound("Onur belgesi bulunamadı.")
        return certificate

    @action(detail=True, methods=["post"], url_path="recommend")
    def recommend(self, request: Request, pk: str | None = None) -> Response:
        certificate = self._get(pk)
        with _service_errors():
            services.recommend_honor_certificate(
                certificate,
                recommended_on=_parse_date(request.data.get("recommended_on")),
                meeting_id=_to_int(request.data.get("meeting")),
            )
        return Response(HonorCertificateSerializer(certificate).data)

    @action(detail=True, methods=["post"], url_path="award")
    def award(self, request: Request, pk: str | None = None) -> Response:
        certificate = self._get(pk)
        with _service_errors():
            services.award_honor_certificate(
                certificate,
                awarded_on=_parse_date(request.data.get("awarded_on")),
                meeting_id=_to_int(request.data.get("meeting")),
            )
        return Response(HonorCertificateSerializer(certificate).data)

    @action(detail=True, methods=["post"], url_path="principal-approve")
    def principal_approve(self, request: Request, pk: str | None = None) -> Response:
        certificate = self._get(pk)
        with _service_errors():
            services.approve_honor_proposal_by_principal(
                certificate,
                decided_on=_parse_date(request.data.get("decided_on")),
                explanation=str(request.data.get("explanation", "")),
            )
        return Response(HonorCertificateSerializer(certificate).data)

    @action(detail=True, methods=["post"], url_path="principal-reject")
    def principal_reject(self, request: Request, pk: str | None = None) -> Response:
        certificate = self._get(pk)
        with _service_errors():
            services.reject_honor_proposal_by_principal(
                certificate,
                decided_on=_parse_date(request.data.get("decided_on")),
                reason=str(request.data.get("reason", "")),
            )
        return Response(HonorCertificateSerializer(certificate).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request: Request, pk: str | None = None) -> Response:
        certificate = self._get(pk)
        with _service_errors():
            services.reject_honor_certificate(
                certificate,
                reason=str(request.data.get("reason", "")),
                decided_on=_parse_date(request.data.get("decided_on")),
                meeting_id=_to_int(request.data.get("meeting")),
            )
        return Response(HonorCertificateSerializer(certificate).data)


# ---------------------------------------------------------------------------
# Karar defteri (CouncilMeeting)
# ---------------------------------------------------------------------------
class CouncilMeetingViewSet(viewsets.GenericViewSet[Any]):
    serializer_class = CouncilMeetingSerializer

    def get_queryset(self) -> Any:
        params = self.request.query_params
        year_raw = params.get("school_year", "")
        return selectors.list_council_meetings(
            council_type=params.get("council_type") or None,
            school_year_id=int(year_raw) if year_raw.isdigit() else None,
        )

    def list(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(CouncilMeetingSerializer(page, many=True).data)

    def create(self, request: Request) -> Response:
        raw_case = request.data.get("discipline_case")
        with _service_errors():
            meeting = council_service.create_council_meeting(
                school_year_id=int(request.data.get("school_year", 0)),
                council_type=str(request.data.get("council_type", "")),
                meeting_date=_parse_date(request.data.get("meeting_date")),
                attendees=list(request.data.get("attendees", [])),
                agenda=str(request.data.get("agenda", "")),
                decision_text=str(request.data.get("decision_text", "")),
                decision_basis=str(request.data.get("decision_basis", "UNANIMITY")),
                notes=str(request.data.get("notes", "")),
                minutes_type=str(request.data.get("minutes_type", "GENERAL")),
                discipline_case_id=int(raw_case) if raw_case else None,
                honor_meeting_kind=str(request.data.get("honor_meeting_kind", "BOARD")),
            )
        return Response(CouncilMeetingSerializer(meeting).data, status=201)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        meeting_id = _to_int(pk)
        meeting = selectors.get_council_meeting(meeting_id) if meeting_id is not None else None
        if meeting is None:
            raise NotFound("Tutanak bulunamadı.")
        return Response(CouncilMeetingSerializer(meeting).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        meeting_id = _to_int(pk)
        meeting = selectors.get_council_meeting(meeting_id) if meeting_id is not None else None
        if meeting is None:
            raise NotFound("Tutanak bulunamadı.")
        raw_date = request.data.get("meeting_date")
        with _service_errors():
            council_service.update_council_meeting(
                meeting,
                meeting_date=(_parse_date(raw_date) if raw_date else None),
                agenda=request.data.get("agenda"),
                decision_text=request.data.get("decision_text"),
                decision_basis=request.data.get("decision_basis"),
                notes=request.data.get("notes"),
                attendees=request.data.get("attendees"),
            )
        # Katılımcılar değiştirildiyse prefetch önbelleği bayatlar — tazele.
        refreshed = selectors.get_council_meeting(meeting.pk)
        return Response(CouncilMeetingSerializer(refreshed or meeting).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        meeting_id = _to_int(pk)
        meeting = selectors.get_council_meeting(meeting_id) if meeting_id is not None else None
        if meeting is None:
            raise NotFound("Tutanak bulunamadı.")
        council_service.delete_council_meeting(meeting)
        return Response(status=204)

    @action(detail=False, methods=["get"], url_path="prefill")
    def prefill(self, request: Request) -> Response:
        return Response(
            council_service.prefill_attendees(
                str(request.query_params.get("council_type", "")),
                honor_meeting_kind=str(request.query_params.get("honor_meeting_kind", "BOARD")),
            )
        )

    @action(detail=True, methods=["get"], url_path="minutes")
    def minutes(self, request: Request, pk: str | None = None) -> FileResponse:
        """Tutanağı PDF'e döker (md. 184/206) — içerik DB'de saklanmaz."""
        meeting_id = _to_int(pk)
        meeting = selectors.get_council_meeting(meeting_id) if meeting_id is not None else None
        if meeting is None:
            raise NotFound("Tutanak bulunamadı.")
        from io import BytesIO

        pdf_bytes = doc_engine.render_council_meeting_minutes(meeting)
        filename = f"kurul-toplanti-tutanagi-{meeting.meeting_no_display}.pdf"
        response = FileResponse(
            BytesIO(pdf_bytes), filename=filename, content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    @action(detail=False, methods=["get"], url_path="case-options")
    def case_options(self, request: Request) -> Response:
        """Dosya görüşme tutanağına bağlanabilecek dosyalar (OYS zarfı: {"cases": [...]})."""
        options = CouncilCaseOptionSerializer(selectors.committee_cases_for_minutes(), many=True)
        return Response({"cases": options.data})


# ---------------------------------------------------------------------------
# "Yaklaşan Süreler" paneli (tasarım §4.5)
# ---------------------------------------------------------------------------
class DeadlinesView(APIView):
    def get(self, request: Request) -> Response:
        items = deadlines.collect_deadline_items(timezone.localdate())
        return Response([item.to_dict() for item in items])


# ---------------------------------------------------------------------------
# Onur evrakları (3 PDF — md. 161, 183/b) — içerik DB'de saklanmaz, kütük tutulmaz
# ---------------------------------------------------------------------------
def _certificates_or_400(
    ids: Any,
    *,
    required_status: str | tuple[str, ...] = "",
    require_same_term: bool = False,
) -> list[Any]:
    """certificate_ids listesini çözer; md. 161 durum kapısı uygulanabilir.

    Resmî tutanak yalnız BEKLENEN durumdaki belgeyi taşır (OYS paritesi):
    uygun görüş tutanağı → HONOR_BOARD_RECOMMENDED, ödül kararı → AWARDED.
    """
    if not isinstance(ids, list) or not ids:
        raise drf_serializers.ValidationError(
            "certificate_ids: en az bir belge id'si içeren liste zorunludur."
        )
    resolved = []
    for raw in ids:
        cert_id = _to_int(str(raw))
        cert = selectors.get_honor_certificate(cert_id) if cert_id is not None else None
        if cert is None:
            raise drf_serializers.ValidationError("Geçersiz onur belgesi kimliği.")
        allowed_statuses = (
            (required_status,) if isinstance(required_status, str) else required_status
        )
        if required_status and cert.status not in allowed_statuses:
            raise drf_serializers.ValidationError(
                "Resmî tutanak yalnız beklenen durumdaki belgeyi taşır (md. 161): "
                f"{cert.get_status_display()} durumundaki belge eklenemez."
            )
        resolved.append(cert)
    if require_same_term and len({cert.school_term_id for cert in resolved}) != 1:
        raise drf_serializers.ValidationError(
            "Teklif çizelgesi yalnız aynı döneme ait kayıtlarla üretilebilir."
        )
    return resolved


def _pdf_response(pdf_bytes: bytes, filename: str) -> FileResponse:
    """PDF'i tarayıcıda GÖSTERİLECEK (inline) yanıta sarar — OYS paritesi."""
    from io import BytesIO

    response = FileResponse(BytesIO(pdf_bytes), filename=filename, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


class HonorProposalFormBlankView(APIView):
    def get(self, request: Request) -> FileResponse:
        return _pdf_response(
            honor_documents.render_proposal_form_blank(), "onur-belgesi-teklif-formu-bos.pdf"
        )


class HonorProposalFormView(APIView):
    def post(self, request: Request) -> FileResponse:
        certificates = _certificates_or_400(request.data.get("certificate_ids"))
        with _service_errors():
            pdf = honor_documents.render_proposal_form(
                certificates, proposer_name=str(request.data.get("proposer_name", ""))
            )
        return _pdf_response(pdf, "onur-belgesi-teklif-formu.pdf")


class HonorRecommendationRecordView(APIView):
    def post(self, request: Request) -> FileResponse:
        certificates = _certificates_or_400(
            request.data.get("certificate_ids"),
            required_status=HonorCertificateStatus.HONOR_BOARD_RECOMMENDED,
            require_same_term=True,
        )
        with _service_errors():
            pdf = honor_documents.render_recommendation_record(
                certificates,
                board=selectors.get_active_honor_board(),
                committee=selectors.get_active_committee(),
            )
        return _pdf_response(pdf, "onur-kurulu-teklif-tutanagi.pdf")


class HonorAwardRecordView(APIView):
    def post(self, request: Request) -> FileResponse:
        certificates = _certificates_or_400(
            request.data.get("certificate_ids"),
            required_status=(
                HonorCertificateStatus.AWARDED,
                HonorCertificateStatus.PRINCIPAL_APPROVED,
                HonorCertificateStatus.PRINCIPAL_REJECTED,
            ),
            require_same_term=True,
        )
        with _service_errors():
            pdf = honor_documents.render_award_decision_record(
                certificates, committee=selectors.get_active_committee()
            )
        return _pdf_response(pdf, "odul-disiplin-kurulu-onur-karari.pdf")
