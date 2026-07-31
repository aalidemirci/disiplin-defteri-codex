"""`disiplin` URL'leri — OYS disiplin yüzeyi AYNEN (FE api.ts F4'te buna bağlanır).

Evrak uçları (documents/generate, honor/documents/…) F3'te eklenecek.
"Yaklaşan Süreler" ucu tasarım §4.5'in verdiği adla (`disiplin/yaklasan-sureler`).
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.disiplin import views, views_purge

router = DefaultRouter()
router.register("discipline/cases", views.DisciplineCaseViewSet, basename="discipline-case")
router.register(
    "discipline/decision-types",
    views.DisciplineDecisionTypeViewSet,
    basename="discipline-decision-type",
)
router.register("honor/certificates", views.HonorCertificateViewSet, basename="honor-certificate")
router.register("council/meetings", views.CouncilMeetingViewSet, basename="council-meeting")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "discipline/committee/",
        views.DisciplineCommitteeView.as_view(),
        name="discipline-committee",
    ),
    path(
        "discipline/committee/chair/",
        views.DisciplineCommitteeChairView.as_view(),
        name="discipline-committee-chair",
    ),
    path(
        "discipline/committee/members/",
        views.DisciplineCommitteeMemberAddView.as_view(),
        name="discipline-committee-member-add",
    ),
    path(
        "discipline/committee/members/<int:member_id>/",
        views.DisciplineCommitteeMemberRemoveView.as_view(),
        name="discipline-committee-member-remove",
    ),
    path("honor/board/", views.HonorBoardView.as_view(), name="honor-board"),
    path("honor/board/chair/", views.HonorBoardChairView.as_view(), name="honor-board-chair"),
    path(
        "honor/board/substitute-chair/",
        views.HonorBoardSubstituteChairView.as_view(),
        name="honor-board-substitute-chair",
    ),
    path(
        "honor/board/members/",
        views.HonorBoardMemberAddView.as_view(),
        name="honor-board-member-add",
    ),
    path(
        "honor/board/members/<int:member_id>/",
        views.HonorBoardMemberRemoveView.as_view(),
        name="honor-board-member-remove",
    ),
    path(
        "honor/general-assembly/",
        views.HonorGeneralAssemblyView.as_view(),
        name="honor-general-assembly",
    ),
    path(
        "honor/general-assembly/<int:member_id>/end/",
        views.HonorGeneralAssemblyMemberEndView.as_view(),
        name="honor-general-assembly-member-end",
    ),
    path(
        "honor/compliance/",
        views.HonorComplianceView.as_view(),
        name="honor-compliance",
    ),
    # Onur evrakları (3 PDF — md. 161, 183/b)
    path(
        "honor/documents/proposal-form-blank/",
        views.HonorProposalFormBlankView.as_view(),
        name="honor-proposal-form-blank",
    ),
    path(
        "honor/documents/proposal-form/",
        views.HonorProposalFormView.as_view(),
        name="honor-proposal-form",
    ),
    path(
        "honor/documents/recommendation-record/",
        views.HonorRecommendationRecordView.as_view(),
        name="honor-recommendation-record",
    ),
    path(
        "honor/documents/award-record/",
        views.HonorAwardRecordView.as_view(),
        name="honor-award-record",
    ),
    path(
        "disiplin/yaklasan-sureler/",
        views.DeadlinesView.as_view(),
        name="discipline-deadlines",
    ),
    # md. 157/7 imha aracı — önizleme → tutanak (kalıcı tek iz) → uygula.
    path(
        "disiplin/imha/onizleme/",
        views_purge.PurgePreviewView.as_view(),
        name="discipline-purge-preview",
    ),
    path(
        "disiplin/imha/onizleme/ogrenci/<int:student_id>/",
        views_purge.PurgeStudentPreviewView.as_view(),
        name="discipline-purge-preview-student",
    ),
    path(
        "disiplin/imha/tutanak/",
        views_purge.PurgeRecordView.as_view(),
        name="discipline-purge-record",
    ),
    path(
        "disiplin/imha/uygula/",
        views_purge.PurgeExecuteView.as_view(),
        name="discipline-purge-execute",
    ),
]
