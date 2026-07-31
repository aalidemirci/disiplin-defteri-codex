"""md. 157/7 imha aracı API uçları — İNCE view'lar (View → Service → Model).

AYRI DOSYA: `views.py` disiplin/onur/kurul yüzeyinin OYS paritesini taşır; imha
aracı F5'te eklenen bağımsız bir yüzeydir ve o dosyayı büyütmeden burada durur.
Hata sözleşmesi (`{code, message, fields}`) `views.py::_service_errors` deseninin
aynısıdır — servis `ValueError`'ları 400'e çevrilir, Türkçe mesaj korunur.

urls.py bağlantısı (bkz. rapor):
    path("disiplin/imha/onizleme/", views_purge.PurgePreviewView.as_view(), ...)
    path("disiplin/imha/onizleme/ogrenci/<int:student_id>/", ...)
    path("disiplin/imha/tutanak/", views_purge.PurgeRecordView.as_view(), ...)
    path("disiplin/imha/uygula/", views_purge.PurgeExecuteView.as_view(), ...)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from io import BytesIO
from typing import Any

from django.http import FileResponse
from rest_framework import serializers as drf_serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.disiplin.selectors import purge as purge_selectors
from apps.disiplin.services import purge as purge_service


@contextmanager
def _service_errors() -> Iterator[None]:
    """Servis hatalarını sözleşmeli 400'e çevirir (views.py::_service_errors deseni)."""
    try:
        yield
    except ValueError as exc:
        raise drf_serializers.ValidationError(str(exc)) from exc


def _parse_optional_date(value: Any) -> date | None:
    """Boş/eksik → None; dolu ama geçersiz → sözleşmeli 400."""
    if value in (None, ""):
        return None
    parsed: date = drf_serializers.DateField().to_internal_value(value)
    return parsed


def _to_int(raw: Any) -> int | None:
    """İstek gövdesindeki kimliği güvenle int'e çevirir — çevrilemeyen her şey None."""
    if raw in (None, ""):
        return None
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _case_payload(item: purge_selectors.PurgeCaseItem) -> dict[str, Any]:
    return {
        "case_id": item.case_id,
        "case_no": item.case_no,
        "petition_date": _iso(item.petition_date),
        "closed_on": _iso(item.closed_on),
        "students": list(item.students),
        "warning_count": item.warning_count,
        "warning_letter_count": item.warning_letter_count,
        "document_count": item.document_count,
        "event_count": item.event_count,
        "attachment_count": item.attachment_count,
        "participant_count": item.participant_count,
        "in_active_school_year": item.in_active_school_year,
    }


def _warning_payload(item: purge_selectors.PurgeWarningItem) -> dict[str, Any]:
    return {
        "warning_id": item.warning_id,
        "case_id": item.case_id,
        "case_no": item.case_no,
        "student_id": item.student_id,
        "student_name": item.student_name,
        "warning_date": _iso(item.warning_date),
        "warning_letter_count": item.warning_letter_count,
        "whole_case_purgeable": item.whole_case_purgeable,
    }


class PurgePreviewView(APIView):
    """Ders yılı sonu (toplu) imha önizlemesi — neyin silineceğinin tam dökümü."""

    def get(self, request: Request) -> Response:
        preview = purge_service.preview()
        return Response(
            {
                "cases": [_case_payload(c) for c in preview.cases],
                "students": [
                    {
                        "student_id": s.student_id,
                        "full_name": s.full_name,
                        "class_label": s.class_label,
                        "status": s.status,
                        "warning_count": s.warning_count,
                    }
                    for s in preview.students
                ],
                "totals": preview.totals,
                "active_school_year_name": preview.active_school_year_name,
                "active_school_year_end": _iso(preview.active_school_year_end),
            }
        )


class PurgeStudentPreviewView(APIView):
    """Nakil eden öğrencinin tekil imha önizlemesi + "+5 iş günü" göstergesi."""

    def get(self, request: Request, student_id: int) -> Response:
        transfer = _parse_optional_date(request.query_params.get("nakil_tarihi"))
        with _service_errors():
            preview = purge_service.preview_student(int(student_id), transfer_date=transfer)
        return Response(
            {
                "student_id": preview.student_id,
                "student_name": preview.student_name,
                "class_label": preview.class_label,
                "warnings": [_warning_payload(w) for w in preview.warnings],
                "whole_case_ids": preview.whole_case_ids,
                "totals": preview.totals,
                "transfer_date": _iso(preview.transfer_date),
                "purge_deadline": _iso(preview.purge_deadline),
                "working_days_left": preview.working_days_left,
                "overdue": preview.overdue,
            }
        )


class PurgeRecordView(APIView):
    """BİRİNCİ onay: imha tutanağı PDF'i üretir; jeton `X-Imha-Token` başlığında döner.

    İkinci onay (uygulama) YALNIZ bu jetonla mümkündür — tutanaksız imha yoktur.
    """

    def post(self, request: Request) -> FileResponse:
        data = request.data
        raw_student = data.get("student_id")
        raw_cases = data.get("case_ids")
        if raw_cases is not None and not isinstance(raw_cases, list):
            raise drf_serializers.ValidationError("case_ids: dosya kimlikleri listesi bekleniyor.")
        with _service_errors():
            record = purge_service.issue_record(
                case_ids=[int(i) for i in raw_cases] if isinstance(raw_cases, list) else None,
                student_id=_to_int(raw_student),
                transfer_date=_parse_optional_date(data.get("nakil_tarihi")),
                purge_date=_parse_optional_date(data.get("imha_tarihi")),
                confirmed=bool(data.get("onay", False)),
            )
        response = FileResponse(
            BytesIO(record.pdf_bytes), filename=record.filename, content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{record.filename}"'
        response["X-Imha-Token"] = record.token
        response["X-Imha-Tutanak-Yolu"] = record.stored_path
        # Tarayıcı fetch'i özel başlıkları ancak açıkça açığa çıkarılırsa görebilir.
        response["Access-Control-Expose-Headers"] = "X-Imha-Token, X-Imha-Tutanak-Yolu"
        return response


class PurgeExecuteView(APIView):
    """İKİNCİ onay: jetonla imhayı uygular (geri alınamaz hard delete)."""

    def post(self, request: Request) -> Response:
        data = request.data
        with _service_errors():
            result = purge_service.execute(
                token=str(data.get("token", "")),
                confirmed=bool(data.get("onay", False)),
            )
        return Response(
            {
                "purged_cases": result.purged_cases,
                "purged_warnings": result.purged_warnings,
                "purged_documents": result.purged_documents,
                "purged_events": result.purged_events,
                "purged_attachments": result.purged_attachments,
                "purged_participants": result.purged_participants,
                "record_path": result.record_path,
                "case_numbers": result.case_numbers,
            }
        )
