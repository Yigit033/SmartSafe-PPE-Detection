## Dataset tools

Bu klasör, dataset indirme ve master dataset hazırlığı için araçlar içerir.

### 1) Roboflow indirme

- Kaynak listesi: `tools/datasets/dataset_sources.yaml`
- Komutlar:

```bash
# PowerShell
$env:ROBOFLOW_API_KEY="..."
python tools/datasets/download_roboflow.py --list
python tools/datasets/download_roboflow.py --name ppe_food_manufacturing_v5
python tools/datasets/download_roboflow.py --all
```

İndirilen datasetler şuraya gelir:
- `datasets/raw/<name>/`

### 2) Sonraki adım

İndirilen datasetleri `datasets/staging/master_food_ppe_v1/` altına birleştirecek
`build_master_dataset.py` script'i, mapping + leakage-proof split + crop-check ile eklenmelidir.

### 3) Master dataset build + validate

```bash
python tools/datasets/build_master_dataset.py --config tools/datasets/master_food_ppe_config.yaml
python tools/datasets/validate_master_dataset.py --data datasets/staging/master_food_ppe_v1
```

Konfig:
- `tools/datasets/master_food_ppe_config.yaml`

Not:
- Mapping **name-based** (class id değil)
- `glasses -> goggles` ve `gown -> apron` alias'ları dataset'e göre riskli olabilir.
  İlk QC crop-check (`datasets/staging/.../qc/crops/`) ile mutlaka gözle doğrula.

