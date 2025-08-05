#!/bin/bash
set -e

# /opt/app klasörüne git
cd /opt/app

# Kodun en son halini çek (isteğe bağlı ama önerilir)
sudo git pull

# Worker'ı çalıştır. Çıktıları log dosyasına yaz.
sudo venv/bin/python worker.py >> /var/log/worker.log 2>&1 &