// Yıl devri sihirbazı API istemcisi — backend `apps/okul/views.py`
// (YearRolloverStatusView / YearRolloverSchoolYearView / YearRolloverPromoteStudentsView)
// ile BİREBİR. Tel anahtarı çevirisi (camelCase → snake_case) yalnız bu sınırda yapılır.
//
// SINIR NOTU: devrin disiplin tarafındaki gerçekleri (kapanmamış dosyalar, yeni
// yılda kurul tanımlı mı) BU uçlarda YOKTUR — `apps.okul` `apps.disiplin`e
// bağlanmaz. Sihirbaz sayfası o iki bilgiyi mevcut disiplin/ödül istemcilerinden
// (`disiplinApi.listCases` / `disiplinApi.getCommittee` / `odulApi.getBoard`) okur.

import { api } from "../../lib/api";
import type { SchoolYear } from "../okul/api";

export type { SchoolYear };

/** Bir sınıf seviyesinin yükseltme dökümü (9→10 gibi). */
export interface LevelMove {
  from_level: number;
  to_level: number;
  count: number;
}

/** Sicil dağılımı satırı — yükseltme DEĞİL (12. sınıfın hedef seviyesi yoktur). */
export interface LevelCount {
  level: number;
  count: number;
}

/** `GET /year-rollover/status/` — sihirbaz açılış özeti. */
export interface YearRolloverStatus {
  active_school_year: SchoolYear | null;
  suggested_year: { name: string; start_date: string; end_date: string };
  active_student_count: number;
  students_without_level: number;
  level_counts: LevelCount[];
}

export interface RolloverYearBody {
  name: string;
  start_date: string;
  end_date: string;
  first_term_end?: string;
  second_term_start?: string;
  /** Varsayılan true — yeni yılın resmî + dini tatillerini yükler. */
  seed_holidays?: boolean;
}

/** `POST /year-rollover/school-year/` sonucu — yeni yıl AKTİF doğar. */
export interface RolloverResult {
  school_year: SchoolYear;
  previous_school_year_name: string;
  holidays_created: number;
  holidays_skipped: number;
}

/** `POST /year-rollover/promote-students/` raporu — önizleme ve uygulama AYNI şekli döner. */
export interface PromotionReport {
  applied: boolean;
  graduate_final_level: boolean;
  promoted: number;
  graduated: number;
  final_level_kept: number;
  skipped_inactive: number;
  skipped_no_level: number;
  skipped_out_of_range: number;
  moves: LevelMove[];
}

export const yilDevriApi = {
  getStatus: (): Promise<YearRolloverStatus> =>
    api.get<YearRolloverStatus>("/year-rollover/status/"),

  /** Yeni ders yılını açar ve AKTİF yapar (eski yıl pasife çekilir). */
  createSchoolYear: (body: RolloverYearBody): Promise<RolloverResult> =>
    api.post<RolloverResult>("/year-rollover/school-year/", body),

  /**
   * Toplu sınıf yükseltme. `apply=false` ÖNİZLEMEDİR (hiçbir şey yazılmaz);
   * `apply=true` GERİ ALINAMAZ (eski sınıf bilgisi saklanmaz).
   */
  promoteStudents: (params: {
    apply: boolean;
    graduateFinalLevel: boolean;
  }): Promise<PromotionReport> =>
    api.post<PromotionReport>("/year-rollover/promote-students/", {
      apply: params.apply,
      graduate_final_level: params.graduateFinalLevel,
    }),
};
