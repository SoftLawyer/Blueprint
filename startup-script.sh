#!/bin/bash
set -e

# Proje klasörüne git, eğer yoksa GitHub'dan indir
cd /
if [ ! -d "Blueprint" ]; then
    git clone [https://github.com/SoftLawyer/Blueprint.git](https://github.com/SoftLawyer/Blueprint.git)
fi
cd Blueprint

# En güncel kodu çek
git pull

# Önceden kurulmuş olan Python sanal ortamını aktifleştir ve worker'ı çalıştır
source venv/bin/activate
python3 worker.py