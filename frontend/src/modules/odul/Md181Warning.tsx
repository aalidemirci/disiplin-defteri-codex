import Icon from "../../ui/Icon";
import { formatDate } from "../../lib/format";
import type { Md181Penalty } from "./api";

// md. 181/1: "disiplin cezası alan öğrencilerin üyeliği düşer." Program üyeliği kendisi
// sonlandırmaz (kullanıcı kararı 26.09.2026); aktif üyede yürürlükte ceza varsa uyarır.
export default function Md181Warning({ penalty }: { penalty: Md181Penalty }) {
  return (
    <p className="mt-1 flex items-start gap-1.5 text-label-small text-error">
      <Icon name="warning" size="sm" />
      <span>
        md. 181/1: {penalty.penalty_type_display} cezası aldı ({penalty.decision_no},{" "}
        {formatDate(penalty.decision_date)}) — üyeliği düşmeli; görevini sonlandırın.
      </span>
    </p>
  );
}

export function md181EndReason(penalty: Md181Penalty | null | undefined): string {
  return penalty ? `md. 181/1: disiplin cezası (${penalty.decision_no})` : "Görev değişikliği";
}
