// Panel "Müdür onayı bekleyenler" kartı (04.10.2026, kurul işleyişi Aşama 1): okul
// müdürünün onayını bekleyen kurul kararları tek yerde — Ödül ve Disiplin Kurulunun onur
// belgesi kabulleri (md. 161/1, 196/3) ve onay mercii müdür olan disiplin kurulu kararları
// (md. 163/2). Bekleyen yoksa kart görünmez; onay işlemi ilgili ekranda yapılır.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { formatDate, formatNumber } from "../../lib/format";
import Icon from "../../ui/Icon";
import { kurulApi, type PrincipalPending } from "../kurul/api";

export default function MudurOnayiKarti({ reloadKey = 0 }: { reloadKey?: number }) {
  const [data, setData] = useState<PrincipalPending | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Eski test taklitleri kurul istemcisini sağlamayabilir; kart sessizce gizlenir.
    const request = kurulApi?.principalPending?.();
    if (!request) return;
    request
      .then((rows) => {
        if (!cancelled) setData(rows);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const honor = data?.honor_certificates ?? [];
  const decisions = data?.decisions ?? [];
  const total = honor.length + decisions.length;
  if (total === 0) return null;

  return (
    <section className="dd-panel" aria-labelledby="mudur-onayi-baslik">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-outline-variant/70 px-5 py-4">
        <div>
          <h2 id="mudur-onayi-baslik" className="text-title-large font-semibold text-on-surface">
            Müdür onayı bekleyenler
          </h2>
          <p className="mt-0.5 text-body-small text-on-surface-variant">
            Kurul kararları okul müdürüne sunuldu (md. 163/2, 196/3)
          </p>
        </div>
        <span className="rounded-shape-xl bg-tertiary-container px-3 py-1 text-label-large font-semibold text-on-tertiary-container">
          {formatNumber(total)}
        </span>
      </div>
      <ul className="divide-y divide-outline-variant/70">
        {decisions.map((d) => (
          <li key={`d${d.id}`}>
            <Link
              to={`/disiplin/${d.case}`}
              className="flex items-center gap-3 px-5 py-3 hover:bg-on-surface/8"
            >
              <Icon name="gavel" className="shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body-medium text-on-surface">
                  {d.student_name} — {d.penalty_type_display}
                </span>
                <span className="block text-body-small text-on-surface-variant">
                  Disiplin kurulu kararı · {d.case_no} · {formatDate(d.decision_date)}
                </span>
              </span>
              <Icon name="chevron_right" className="text-on-surface-variant" />
            </Link>
          </li>
        ))}
        {honor.length > 0 && (
          <li>
            <Link
              to="/odul-disiplin-kurulu?sekme=mudur-onayi"
              className="flex items-center gap-3 px-5 py-3 hover:bg-on-surface/8"
            >
              <Icon name="workspace_premium" className="shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="block text-body-medium text-on-surface">
                  {formatNumber(honor.length)} onur belgesi kararı
                </span>
                <span className="block truncate text-body-small text-on-surface-variant">
                  {honor.map((c) => c.student_name).join(", ")}
                </span>
              </span>
              <Icon name="chevron_right" className="text-on-surface-variant" />
            </Link>
          </li>
        )}
      </ul>
    </section>
  );
}
