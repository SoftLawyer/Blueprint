#!/bin/bash
set -e

# Proje klasörüne git, yoksa GitHub'dan indir
cd /
if [ ! -d "Blueprint" ]; then
    git clone https://github.com/SoftLawyer/Blueprint.git
fi
cd Blueprint

# En güncel kodu çek
git pull

# Python sanal ortamını aktifleştir, yoksa oluştur
if [ ! -d "venv" ]; then
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Worker'ı arka planda başlat ve tüm çıktıları log dosyasına yönlendir
nohup python3 worker.py >> /var/log/worker.log 2>&1 &
