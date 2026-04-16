#!/bin/bash
# =============================================================
# Script thiết lập và build Cloudstream 3 Vietnamese Plugins
# Chạy trên Ubuntu VPS
# =============================================================

set -e

echo "========================================="
echo "  Cloudstream 3 VN Plugins - Setup & Build"
echo "========================================="

# 1. Cài đặt dependencies
echo ""
echo "[1/5] Cài đặt JDK 17 và Git..."
sudo apt update
sudo apt install -y openjdk-17-jdk git unzip wget

# Verify Java
java -version
echo "✅ JDK installed"

# 2. Tạo Gradle wrapper
echo ""
echo "[2/5] Tải Gradle wrapper..."
cd "$(dirname "$0")"

# Download gradle-wrapper.jar nếu chưa có
if [ ! -f "gradle/wrapper/gradle-wrapper.jar" ]; then
    echo "Downloading gradle-wrapper.jar..."
    mkdir -p gradle/wrapper
    wget -q "https://github.com/nickkdoesstuff/gradle-wrapper-jar/raw/main/gradle-wrapper.jar" \
        -O gradle/wrapper/gradle-wrapper.jar 2>/dev/null || \
    wget -q "https://raw.githubusercontent.com/nickkdoesstuff/gradle-wrapper-jar/main/gradle-wrapper.jar" \
        -O gradle/wrapper/gradle-wrapper.jar 2>/dev/null || \
    {
        # Fallback: install gradle and generate wrapper
        echo "Downloading Gradle distribution directly..."
        GRADLE_VERSION="8.9"
        wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -O /tmp/gradle.zip
        sudo unzip -qo /tmp/gradle.zip -d /opt/
        sudo ln -sf "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle
        gradle wrapper --gradle-version ${GRADLE_VERSION}
        rm -f /tmp/gradle.zip
    }
    echo "✅ Gradle wrapper ready"
else
    echo "✅ Gradle wrapper already exists"
fi

# 3. Set permissions
echo ""
echo "[3/5] Set permissions..."
chmod +x gradlew
echo "✅ Permissions set"

# 4. Build plugins
echo ""
echo "[4/5] Building plugins... (this may take a few minutes on first run)"
./gradlew ThuVienHDProvider:make ThuVienCineProvider:make GoogleSheetProvider:make

# 5. Collect built files
echo ""
echo "[5/5] Collecting built .cs3 files..."
mkdir -p builds
find . -name "*.cs3" -exec cp {} builds/ \;

echo ""
echo "========================================="
echo "  ✅ Build hoàn tất!"
echo "========================================="
echo ""
echo "Các file plugin đã build:"
ls -la builds/*.cs3 2>/dev/null || echo "  (Không tìm thấy file .cs3)"
echo ""
echo "📌 Bước tiếp theo:"
echo "1. Push repo lên GitHub/GitLab"
echo "2. Cập nhật URL trong repo.json và plugins.json"
echo "3. Thêm repo URL vào Cloudstream 3 app"
echo ""
echo "Repo URL format:"
echo "  https://raw.githubusercontent.com/YOUR_USERNAME/REPO_NAME/main/repo.json"
