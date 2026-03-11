---
description: Backend servisini güncelledikten sonra senkronize etme akışı
---
1. `/backend` dizinindeki kod değişikliklerini tamamla.
// turbo
2. Backend konteynerini yeniden başlat:
   `docker restart smartsafe-backend-encore`
3. Logları kontrol ederek servisin ayağa kalktığından emin ol:
   `docker logs smartsafe-backend-encore --tail 20`
