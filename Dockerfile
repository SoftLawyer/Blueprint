# Adım 1: Daha tam bir Python ortamı olan 'python:3.10'u kullanıyoruz.
# 'slim' versiyonu yerine bu, kütüphane kurulumunda daha az sorun çıkarır.
FROM python:3.10

# Kurulum sırasında interaktif pencerelerin çıkmasını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Adım 2: Gerekli tüm sistem programlarını, FONT'ları ve video kütüphanelerini kur
RUN apt-get update && \
    # Microsoft fontları gibi "özgür olmayan" paketlerin bulunabilmesi için
    # Debian'ın 'contrib' ve 'non-free' depolarını etkinleştiriyoruz.
    # BU, 'ttf-mscorefonts-installer' paketinin bulunmasını garantiler.
    sed -i 's/main/main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    # Microsoft fontları için lisans sözleşmesini otomatik olarak kabul et
    echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    git \
    # Microsoft Fontları (Arial, Impact vb. için)
    ttf-mscorefonts-installer \
    # Alternatif açık kaynak fontlar
    fonts-liberation \
    # Font önbelleğini yönetmek için
    fontconfig \
    # OpenCV ve diğer resim işleme kütüphanelerinin ihtiyaç duyduğu gizli bağımlılıklar
    libgl1-mesa-glx \
    libglib2.0-0 \
    && \
    # İndirilen paket listelerini temizle
    rm -rf /var/lib/apt/lists/*

# Adım 3: ImageMagick'in güvenlik politikasını düzenle (Nihai Çözüm)
# Bu komut, geçici dosya işlemlerini engelleyen kuralı bulur ve
# "none" (hiçbir hak yok) olan iznini "read|write" (okuma|yazma) olarak değiştirir.
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@\*"/g' /etc/ImageMagick-6/policy.xml

# Adım 4: Yüklenen yeni fontları sisteme tanıt
RUN fc-cache -f -v

# Adım 5: Uygulama klasörünü oluştur ve içine gir
WORKDIR /app

# Adım 6: Gerekli Python kütüphanelerini kur
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Adım 7: Kurulumu doğrulamak için (opsiyonel)
RUN python -c "import moviepy.editor; print('✅ MoviePy Başarıyla Yüklendi!')"
RUN python -c "import cv2; print('✅ OpenCV Başarıyla Yüklendi!')"
RUN python -c "from rembg import remove; print('✅ Rembg Başarıyla Yüklendi!')"

# Adım 8: Proje kodlarını kopyala
COPY . .

# Adım 9: Uygulamayı çalıştır
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 3600 main:app
