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
python tools/datasets/download_roboflow.py --name ppe_food_manufacturing_v5 --clean
python tools/datasets/download_roboflow.py --all
```

İndirilen datasetler şuraya gelir:
- `datasets/raw/<name>/`

Notlar:
- Script indirme sonrası `data.yaml` + `train/images` gibi minimum yapıyı **doğrular**. Boş/partial klasör kaldıysa `--clean` ile silip yeniden indir.
- Roboflow SDK notu: hedef klasör varsa `overwrite=False` ile indirme **atlanabilir**. Bu yüzden script default olarak `overwrite=True` kullanır; istemezsen `--no-overwrite`.
- IDE tarafında `datasets/raw/` ignore edilmiş olabilir; dosyalar diskte olup ağaçta gecikmeli görünebilir. Şüphedeysen PowerShell ile klasör boyutunu kontrol et.

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

