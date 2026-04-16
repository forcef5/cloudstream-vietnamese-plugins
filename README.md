# Cloudstream 3 Vietnamese Plugins

Extension repository cho Cloudstream 3 - Kho phim Việt Nam.

## 📦 Providers

### 1. ThuVienHD
- **Nguồn**: [thuvienhd.top](https://thuvienhd.top/)
- **Nội dung**: Phim lẻ, phim bộ Full HD, 4K link Fshare
- **Danh mục**: Phim mới, HOT, Phim lẻ, Phim bộ, Thuyết Minh, Lồng Tiếng, theo thể loại

### 2. ThuVienCine
- **Nguồn**: [thuviencine.com](https://thuviencine.com/)
- **Nội dung**: Phim HD 4K Vietsub link Fshare
- **Danh mục**: Phim lẻ, Phim bộ, Trending, theo thể loại

### 3. Kho Phim Sheet (Google Sheets)
- **Nguồn**: Google Sheets
- **Nội dung**: Kho phim tự quản lý từ Google Sheet
- **Sheet URL**: Tự cấu hình trong source code

## 🔗 Fshare Integration

Tích hợp Fshare getlink qua API:
```
http://fspoint.shop:8308/getlink?id={LINKCODE}
```
- Tự động extract linkcode từ URL Fshare
- Getlink trả về URL streaming trực tiếp
- Hỗ trợ phát hiện chất lượng (4K, 1080p, 720p)

## 🚀 Cài đặt

### Cách 1: Thêm Repo URL vào Cloudstream 3
1. Mở app Cloudstream 3
2. Vào Settings → Extensions → Add Repository
3. Nhập URL:
```
https://raw.githubusercontent.com/YOUR_USERNAME/cloudstream-vietnamese-plugins/main/repo.json
```
4. Cài đặt các plugin mong muốn

### Cách 2: Build thủ công
```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/cloudstream-vietnamese-plugins.git
cd cloudstream-vietnamese-plugins

# Build tất cả plugin
chmod +x gradlew
./gradlew ThuVienHDProvider:make
./gradlew ThuVienCineProvider:make
./gradlew GoogleSheetProvider:make

# File .cs3 sẽ được tạo trong thư mục build của mỗi provider
```

## 🛠 Build trên Ubuntu VPS

### Yêu cầu
- JDK 17+
- Git

### Cài đặt
```bash
# Cài JDK 17
sudo apt update
sudo apt install -y openjdk-17-jdk git

# Clone và build
git clone https://github.com/YOUR_USERNAME/cloudstream-vietnamese-plugins.git
cd cloudstream-vietnamese-plugins
chmod +x gradlew
./gradlew ThuVienHDProvider:make ThuVienCineProvider:make GoogleSheetProvider:make
```

## 📊 Cấu trúc Google Sheet

Sheet cần có các cột theo format CSV:
| Cột | Nội dung | Ví dụ |
|-----|----------|-------|
| A | Tên phim (có thể có BBCode) | `Wonka [B][COLOR yellow]{Thuyết Minh}[/COLOR][/B] Wonka 2023` |
| B | Link Fshare | `https://www.fshare.vn/folder/VWLYU1DH1DJB` |
| C | Poster URL | `https://img166.imagetwist.com/th/...` |
| D | Mô tả phim | `Câu chuyện kỳ diệu về hành trình...` |

## 📁 Cấu trúc dự án

```
├── repo.json                          # Manifest cho Cloudstream
├── plugins.json                       # Danh sách plugin  
├── build.gradle.kts                   # Root build config
├── settings.gradle.kts
├── .github/workflows/build.yml        # GitHub Actions auto-build
├── ThuVienHDProvider/
│   ├── build.gradle.kts
│   └── src/main/kotlin/com/cloudstreamvn/
│       ├── ThuVienHDPlugin.kt
│       └── ThuVienHDProvider.kt
├── ThuVienCineProvider/
│   ├── build.gradle.kts
│   └── src/main/kotlin/com/cloudstreamvn/
│       ├── ThuVienCinePlugin.kt
│       └── ThuVienCineProvider.kt
└── GoogleSheetProvider/
    ├── build.gradle.kts
    └── src/main/kotlin/com/cloudstreamvn/
        ├── GoogleSheetPlugin.kt
        └── GoogleSheetProvider.kt
```

## ⚙️ Tuỳ chỉnh

### Thay đổi Google Sheet
Sửa `sheetId` trong `GoogleSheetProvider.kt`:
```kotlin
private val sheetId = "YOUR_SHEET_ID_HERE"
```

### Thay đổi Fshare API
Sửa `fshareGetlinkApi` trong mỗi provider:
```kotlin
private val fshareGetlinkApi = "http://your-api-server:port/getlink"
```

## 📝 License
MIT License
