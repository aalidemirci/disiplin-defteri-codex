"""`okul` URL'leri — kebab-case, çoğul kaynak adları (OYS API sözleşmesi)."""

from __future__ import annotations

from django.urls import path

from apps.okul import views

urlpatterns = [
    # Kurulum sihirbazı
    path("setup/status/", views.SetupStatusView.as_view(), name="setup-status"),
    path("setup/school-config/", views.SchoolConfigView.as_view(), name="setup-school-config"),
    path("setup/complete/", views.SetupCompleteView.as_view(), name="setup-complete"),
    # GitHub Release tabanlı uygulama güncellemesi
    path("updates/latest/", views.UpdateStatusView.as_view(), name="update-latest"),
    path(
        "updates/latest/installer/",
        views.UpdateInstallerView.as_view(),
        name="update-installer",
    ),
    # Öğrenim seviyeleri (UI seçicileri — onur kurulu üye seviyesi, md. 183/b)
    path("grade-levels/", views.GradeLevelsView.as_view(), name="grade-levels"),
    # Ders yılları
    path("school-years/", views.SchoolYearListCreateView.as_view(), name="school-year-list"),
    path(
        "school-years/<int:pk>/terms/",
        views.SchoolTermView.as_view(),
        name="school-year-terms",
    ),
    path(
        "school-years/<int:pk>/activate/",
        views.SchoolYearActivateView.as_view(),
        name="school-year-activate",
    ),
    # Tatiller
    path("holidays/", views.HolidayListCreateView.as_view(), name="holiday-list"),
    path("holidays/seed/", views.HolidaySeedView.as_view(), name="holiday-seed"),
    path("holidays/<int:pk>/", views.HolidayDetailView.as_view(), name="holiday-detail"),
    # Öğrenciler / Personel
    path("students/", views.StudentListCreateView.as_view(), name="student-list"),
    path("students/<int:pk>/", views.StudentDetailView.as_view(), name="student-detail"),
    path("personnel/", views.PersonnelListCreateView.as_view(), name="personnel-list"),
    path("personnel/<int:pk>/", views.PersonnelDetailView.as_view(), name="personnel-detail"),
    path(
        "class-responsibilities/",
        views.ClassResponsibilityListCreateView.as_view(),
        name="class-responsibility-list",
    ),
    path(
        "class-responsibilities/<int:pk>/",
        views.ClassResponsibilityDetailView.as_view(),
        name="class-responsibility-detail",
    ),
    # İçe aktarma (dosya veya pano metni)
    path(
        "imports/students/preview/",
        views.StudentImportPreviewView.as_view(),
        name="import-students-preview",
    ),
    path(
        "imports/students/commit/",
        views.StudentImportCommitView.as_view(),
        name="import-students-commit",
    ),
    path(
        "imports/personnel/preview/",
        views.PersonnelImportPreviewView.as_view(),
        name="import-personnel-preview",
    ),
    path(
        "imports/personnel/commit/",
        views.PersonnelImportCommitView.as_view(),
        name="import-personnel-commit",
    ),
    # Şablon indirme
    path("templates/students/", views.StudentTemplateView.as_view(), name="template-students"),
    path("templates/personnel/", views.PersonnelTemplateView.as_view(), name="template-personnel"),
    # Yıl devri sihirbazı (tasarım §4.6)
    path(
        "year-rollover/status/",
        views.YearRolloverStatusView.as_view(),
        name="year-rollover-status",
    ),
    path(
        "year-rollover/school-year/",
        views.YearRolloverSchoolYearView.as_view(),
        name="year-rollover-school-year",
    ),
    path(
        "year-rollover/promote-students/",
        views.YearRolloverPromoteStudentsView.as_view(),
        name="year-rollover-promote-students",
    ),
    # Uygulama parolası / kilit (tasarım §6) — bu ön ek kilit kapısından muaftır
    # (`apps.okul.lock_middleware.ALLOWED_PREFIXES` ile birebir aynı kalmalıdır).
    path("security/status/", views.SecurityStatusView.as_view(), name="security-status"),
    path("security/enable/", views.SecurityEnableView.as_view(), name="security-enable"),
    path("security/unlock/", views.SecurityUnlockView.as_view(), name="security-unlock"),
    path("security/lock/", views.SecurityLockView.as_view(), name="security-lock"),
    path("security/recover/", views.SecurityRecoverView.as_view(), name="security-recover"),
    path(
        "security/change-password/",
        views.SecurityChangePasswordView.as_view(),
        name="security-change-password",
    ),
    path("security/disable/", views.SecurityDisableView.as_view(), name="security-disable"),
    path(
        "backups/encrypted/",
        views.EncryptedBackupDownloadView.as_view(),
        name="encrypted-backup-download",
    ),
]
