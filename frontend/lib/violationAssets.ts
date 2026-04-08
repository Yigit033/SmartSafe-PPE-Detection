/**
 * DB’deki snapshot_path → tarayıcıda açılabilir URL.
 * İhlaller sayfası ile aynı: `public/storage/violations` (Docker’da storage mount) üzerinden `/storage/violations/...`
 */
export function violationSnapshotUrl(
  snapshotPath: string | null | undefined,
): string | null {
  if (snapshotPath == null || String(snapshotPath).trim() === "") return null;
  let p = String(snapshotPath).replace(/\\/g, "/").trim();
  p = p.replace(/^(storage\/)?violations\//i, "");
  if (!p) return null;
  return `/storage/violations/${p}`;
}

/** Ham violation_type / eksik PPE listesinden kısa Türkçe başlık */
export function formatViolationEventTitle(violationType: string): string {
  const t = (violationType || "").toLowerCase();
  if (/no_helmet|baret|helmet|kask/.test(t)) return "Baret İhlali Tespit Edildi";
  if (/no_vest|yelek|vest|safety_vest/.test(t)) return "Yelek İhlali Tespit Edildi";
  if (/ayakkabı|shoe|safety_shoe/.test(t)) return "Ayakkabı İhlali Tespit Edildi";
  if (/eldiven|glove/.test(t)) return "Eldiven İhlali Tespit Edildi";
  if (/gözlük|glass|goggle/.test(t)) return "Gözlük İhlali Tespit Edildi";
  if (/maske|mask|face_mask/.test(t)) return "Maske İhlali Tespit Edildi";
  if (/kulak|ear/.test(t)) return "Kulak Koruyucu İhlali Tespit Edildi";
  if (/kayış|harness/.test(t)) return "Emniyet Kemeri İhlali Tespit Edildi";
  return "Güvenlik İhlali Tespit Edildi";
}
