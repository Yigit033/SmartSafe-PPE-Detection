# Versiyonu oku
$DOCKER_USER = "smartsafe"
$VERSION = Get-Content "VERSION" -Raw
$VERSION = $VERSION.Trim()

echo "---------------------------------------------------"
echo "SmartSafe AI Yayınlanıyor (Versiyon: $VERSION)"
echo "---------------------------------------------------"

# 1. CORE
echo "[1/3] Core derleniyor (latest & $VERSION)..."
docker build --build-arg APP_VERSION=$VERSION -t $DOCKER_USER/smartsafeai-core:latest -t $DOCKER_USER/smartsafeai-core:$VERSION -f Dockerfile.core.prod ..
docker push $DOCKER_USER/smartsafeai-core:latest
docker push $DOCKER_USER/smartsafeai-core:$VERSION

# 2. BACKEND
echo "[2/3] Backend derleniyor (latest & $VERSION)..."
docker build --build-arg APP_VERSION=$VERSION -t $DOCKER_USER/smartsafeai-backend:latest -t $DOCKER_USER/smartsafeai-backend:$VERSION -f Dockerfile.backend.prod ..
docker push $DOCKER_USER/smartsafeai-backend:latest
docker push $DOCKER_USER/smartsafeai-backend:$VERSION

# 3. FRONTEND
echo "[3/3] Frontend derleniyor (latest & $VERSION)..."
docker build --build-arg APP_VERSION=$VERSION -t $DOCKER_USER/smartsafeai-frontend:latest -t $DOCKER_USER/smartsafeai-frontend:$VERSION -f Dockerfile.frontend.prod ..
docker push $DOCKER_USER/smartsafeai-frontend:latest
docker push $DOCKER_USER/smartsafeai-frontend:$VERSION

echo "---------------------------------------------------"
echo "YAYINLAMA TAMAMLANDI!"
echo "Artik Installer bu imajlari her yerden cekebilir."
echo "---------------------------------------------------"
