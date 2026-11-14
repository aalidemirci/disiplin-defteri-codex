// Otomatik yedek özeti + yedekten geri yükleme istemcisi.
// Backend `apps/okul/views.py::BackupRestoreView` (`/security/backups/`) ile BİREBİR.
// Uç kilit kapısından muaftır: kilitliyken ve kurulum tamamlanmadan da çağrılabilir.

import { api } from "../../lib/api";

/** Yedekler klasöründeki bir dosya (kişisel veri içermez). */
export interface YedekBilgisi {
  name: string;
  /** "daily" günlük · "pre_migrate" güncelleme öncesi · "transition" parola işlemi öncesi. */
  kind: "daily" | "pre_migrate" | "transition";
  /** Dosya adındaki tarih (yyyy-aa-gg); okunamadıysa null. */
  taken_on: string | null;
  size: number;
  /** `.ddbak` (şifreli) mi, düz `.sqlite3` mü? */
  encrypted: boolean;
}

export interface YedekOzeti {
  backup_dir: string;
  /** En yeni günlük yedeğin tarihi; hiç yedek yoksa null. */
  last_daily_on: string | null;
  /** Bir yedek hazırlandı ve programın yeniden açılmasını bekliyor mu? */
  pending_restore: boolean;
  /** En yeniden eskiye. */
  backups: YedekBilgisi[];
}

export interface GeriYuklemeSonucu extends YedekOzeti {
  message: string;
  /** Boş değilse kullanıcıya kalıcı olarak gösterilir. */
  warning: string;
}

/** Şifreli yedeği açan sırlar; düz yedekte ve kilit açıkken boş kalabilir. */
export interface YedekSirlari {
  password?: string;
  recovery_key?: string;
}

export const yedekApi = {
  ozet: () => api.get<YedekOzeti>("/security/backups/"),
  /** Yedekler klasöründeki bir dosyayı adıyla hazırlar. */
  addanHazirla: (name: string, sirlar: YedekSirlari = {}) =>
    api.post<GeriYuklemeSonucu>("/security/backups/", { name, ...sirlar }),
  /** Kullanıcının seçtiği dosyayı (USB'deki kopya vb.) hazırlar. */
  dosyadanHazirla: (file: File, sirlar: YedekSirlari = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (sirlar.password) form.append("password", sirlar.password);
    if (sirlar.recovery_key) form.append("recovery_key", sirlar.recovery_key);
    return api.postForm<GeriYuklemeSonucu>("/security/backups/", form);
  },
  /** Hazırlanmış geri yüklemeden vazgeçer (program yeniden açılmadan önce). */
  vazgec: () => api.del<YedekOzeti>("/security/backups/"),
};
