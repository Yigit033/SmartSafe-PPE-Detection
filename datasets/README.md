## datasets/

Bu klasör **lokal veri yönetimi** içindir (genelde git'e girmez).

### Klasörler

- `raw/`: Kaynaktan indirilen **ham** datasetler (dokunma, değiştirme).
- `staging/`: Master dataset çıktıları (mapping + split sonrası).

### Senior kuralı

- Ham veri asla “elle düzeltilmez”. Düzeltme gerekiyorsa `staging/` üretim script'lerinde yapılır.
- Her staging çıktısının yanında **manifest** tutulur (hangi kaynaklar, kaç görüntü, mapping).

