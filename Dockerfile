# Adım 1: Tam Python ortamını kullan
FROM python:3.10

# Kurulum sırasında interaktif pencerelerin çıkmasını engelle
ENV DEBIAN_FRONTEND=noninteractive

# Adım 2: Gerekli tüm sistem programlarını, FONT'ları ve video kütüphanelerini kur
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    git \
    # Sorunlu Microsoft fontları yerine, onlarla uyumlu, açık kaynaklı Liberation fontlarını kuruyoruz.
    fonts-liberation \
    fontconfig \
    # OpenCV ve diğer resim işleme kütüphanelerinin ihtiyaç duyduğu gizli bağımlılıklar
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && \
    # İndirilen paket listelerini temizle
    rm -rf /var/lib/apt/lists/*

# Adım 3: ImageMagick'in güvenlik politikasını düzenle (Bu satır videoyapar hatasını çözer)
# Bu komut, ImageMagick'in metinleri işlemesine izin verir.
RUN sed -i 's/<policy domain="path" rights="none" pattern="@\*" \/>/<!-- <policy domain="path" rights="none" pattern="@\*" \/> -->/g' /etc/ImageMagick-6/policy.xml

# Adım 4: Yüklenen yeni fontları sisteme tanıt
RUN fc-cache -f -v

# Adım 5: Uygulama klasörünü oluştur ve içine gir
WORKDIR /app

# Adım 6: Pip'i güncelle
RUN pip install --upgrade pip setuptools wheel

# Adım 7: Gerekli Python kütüphanelerini kur
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Adım 8: Kurulumu doğrulamak için (opsiyonel)
RUN python -c "import moviepy.editor; print('MoviePy Başarıyla Yüklendi!')"
RUN python -c "import cv2; print('OpenCV Başarıyla Yüklendi!')"
RUN python -c "from rembg import remove; print('Rembg Başarıyla Yüklendi!')"

# Adım 9: Proje kodlarını kopyala
COPY . .

# Adım 10: Uygulamayı çalıştır
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 3600 main:app
