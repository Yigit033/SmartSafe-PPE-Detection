## Master dataset builder plan (Food PPE)

Bu dosya, `build_master_dataset.py` script'inin senior gereksinimlerini tanımlar.
Bir sonraki adımda bu script'i implemente edeceğiz.

### Girdiler

- `datasets/raw/<source>/data.yaml` ve `train/valid/test` YOLO klasörleri (Roboflow export)
- Kaynak registry: `tools/datasets/dataset_sources.yaml` (sadece download için)

### Çıktılar

- `datasets/staging/master_food_ppe_v1/`
  - `images/train`, `images/val`, `images/test` (opsiyonel)
  - `labels/train`, `labels/val`, `labels/test`
  - `data.yaml` (canonical 5 class)
  - `manifest.json` (source breakdown, counts, mapping, timestamp)
  - `qc/crops/<class>/` (crop-check çıktıları)

### Canonical sınıflar

0. `apron`
1. `goggles`
2. `haircap`  (hairnet/bone)
3. `mask`
4. `gloves`

### Senior kurallar

- **Name-based mapping**: class id değil, class ismi üzerinden mapping.
- **Unknown class drop**: map'lenmeyen sınıf label satırları atılır.
- **Leakage-proof split**: Eğer aynı video/kamera ardışık frame ise, random split yapılmaz (klip/kamera bazlı).
- **QC crop-check**: her sınıftan N adet bbox crop örneklenir.
- **No in-place mutate**: `datasets/raw/` asla değiştirilmez; staging yeniden üretilir.

