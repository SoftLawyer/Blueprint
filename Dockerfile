# Adım 1: Python 3.10 tabanlı Debian imajını kullan
FROM python:3.10

# Adım 2: Gerekli ortam değişkenlerini ayarla
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Adım 3: Gerekli tüm sistem programlarını, FONT'ları ve video kütüphanelerini kur
RUN apt-get update && \
    sed -i 's/Components: main/Components: main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections && \
    # Gerekli tüm paketleri kur (rustc ve cargo, whisper kurulumu için eklendi)
    apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    git \
    rustc \
    cargo \
    ttf-mscorefonts-installer \
    fonts-liberation \
    fontconfig \
    libgl1 \
    libglib2.0-0 \
    && \
    # İndirilen paket listelerini temizle
    rm -rf /var/lib/apt/lists/*

# Adım 4: ImageMagick'in güvenlik politikasını düzenle (Sürüme duyarsız hale getirildi)
RUN sed -i 's/rights="none"/rights="read|write"/g' /etc/ImageMagick-*/policy.xml

# Adım 5: Yüklenen yeni fontları sisteme tanıt
RUN fc-cache -f -v

# Adım 6: Uygulama klasörünü oluştur ve içine gir
WORKDIR /app

# Adım 7: Gerekli Python kütüphanelerini kur
COPY requirements.txt .
RUN python3 -m venv venv
RUN venv/bin/pip install --no-cache-dir --upgrade pip
RUN venv/bin/pip install --no-cache-dir -r requirements.txt

# Adım 8: Projenin geri kalan kodlarını kopyala
COPY . .

# Adım 9: Uygulamayı çalıştır
CMD ["/app/venv/bin/python", "worker.py"]

