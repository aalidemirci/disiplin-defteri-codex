// Geri yükleme kartını bir düğmenin arkasında sunar: kilit ekranı ve kurulum
// sihirbazı gibi asıl işi başka olan ekranlarda kart ancak istenince açılır
// (ve yedek özeti ancak o zaman istenir).

import { useState } from "react";

import Button from "../../ui/Button";
import YedektenGeriYukleme from "./YedektenGeriYukleme";

export default function YedektenGeriYuklemeAcilir({ etiket }: { etiket: string }) {
  const [acik, setAcik] = useState(false);

  return (
    <div className="flex flex-col gap-3">
      <div>
        <Button
          variant="text"
          type="button"
          icon="settings_backup_restore"
          aria-expanded={acik}
          onClick={() => setAcik((onceki) => !onceki)}
        >
          {etiket}
        </Button>
      </div>
      {acik && <YedektenGeriYukleme />}
    </div>
  );
}
