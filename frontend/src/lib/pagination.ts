// DRF sayfalı yanıt tipi + çözücü (Tur 615 — F-fe DRY konsolidasyonu).
// 20+ modül api.ts'i kendi `Paginated<T>` kopyasını, 10'u özdeş `unwrap`
// kopyasını taşıyordu — tek doğruluk kaynağı burası. Yeni kod bunu kullanır.

/** DRF PageNumber/LimitOffset sayfalı liste yanıtı (kanonik tam şekil). */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** DRF list uçları sayfalıdır; bazı özel action'lar düz dizi döndürür —
 * iki biçimi de diziye indirger. */
export function unwrap<T>(data: Paginated<T> | T[]): T[] {
  return Array.isArray(data) ? data : data.results;
}

/** Sayfalı ucu `next` bitene dek dolaşıp TÜM kayıtları toplar (LimitOffset).
 * Tek sayfalık `limit=N` çağrısı N'den sonrasını sessizce kesiyordu (ör. 200.
 * dosyadan sonrası listede/aramada görünmüyordu). */
export async function collectPages<T>(
  fetchPage: (offset: number) => Promise<Paginated<T> | T[]>,
): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  for (;;) {
    const data = await fetchPage(offset);
    if (Array.isArray(data)) return [...items, ...data];
    items.push(...data.results);
    if (!data.next || data.results.length === 0) return items;
    offset += data.results.length;
  }
}
