# Adım 1: Python 3.10 tabanlı Debian imajını kullan
FROM python:3.10

# Adım 2: Gerekli ortam değişkenlerini ayarla
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Adım 3: Gerekli tüm sistem programlarını, FONT'ları ve video kütüphanelerini kur
# Bu blok, sanal makinede başarıyla uyguladığımız nihai kurulum adımlarını içerir.
RUN apt-get update && \
    # Debian'ın paket kaynak listesini contrib ve non-free depolarını içerecek şekilde düzenle
    sed -i 's/ main/ main contrib non-free/g' /etc/apt/sources.list && \
    apt-get update && \
    # Microsoft fontları için lisans sözleşmesini otomatik olarak kabul et
    echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections && \
    # Gerekli tüm paketleri kur
    apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    git \
    ttf-mscorefonts-installer \
    fonts-liberation \
    fontconfig \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && \
    # İndirilen paket listelerini temizle
    rm -rf /var/lib/apt/lists/*

# Adım 4: ImageMagick'in güvenlik politikasını düzenle (Nihai Çözüm)
RUN sed -i 's/rights="none"/rights="read|write"/g' /etc/ImageMagick-6/policy.xml

# Adım 5: Yüklenen yeni fontları sisteme tanıt
RUN fc-cache -f -v

# Adım 6: Uygulama klasörünü oluştur ve içine gir
WORKDIR /app

# Adım 7: Gerekli Python kütüphanelerini kur
# Önce requirements.txt dosyasını kopyala
COPY requirements.txt .
# Sanal ortam oluştur ve kütüphaneleri içine kur
RUN python3 -m venv venv
RUN venv/bin/pip install --no-cache-dir --upgrade pip
RUN venv/bin/pip install --no-cache-dir -r requirements.txt

# Adım 8: Projenin geri kalan kodlarını kopyala
COPY . .

# Adım 9: Uygulamayı çalıştır
# GÜNCELLEME: Artık bir web sunucusu (gunicorn) yerine,
# doğrudan video üreten worker script'ini başlatıyoruz.
CMD ["/app/venv/bin/python", "worker.py"]
