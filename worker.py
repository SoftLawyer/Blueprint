# worker.py (v6 - Nihai Güvenilir Hata Kaydı)

import os
import logging
import traceback
import tempfile
import shutil
import time
import requests
import subprocess
from datetime import datetime

# Projenizdeki mevcut modülleri import ediyoruz
import hikayeuretir
import googleilesesolustur
import profilfotoolusturur
import profilfotonunarkasinisiler
import videoyapar
import kucukresimolusturur

from google.cloud import storage
from google.api_core import exceptions

# --- TEMEL AYARLAR ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"
IDLE_SHUTDOWN_SECONDS = 600 # 10 dakika

# --- YENİ ve GÜVENİLİR HATA KAYDI FONKSİYONU ---

def get_metadata(metadata_path):
    """Sanal makinenin metadata sunucusundan bilgi alır."""
    try:
        response = requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/{metadata_path}",
            headers={'Metadata-Flavor': 'Google'}, timeout=5
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException:
        # Hata durumunda loglama yapmadan None dön, ana programda loglanır.
        return None

def log_error_to_gcs(storage_client, bucket_name, title, error_details):
    """
    Hata loglarını GCS'teki merkezi bir klasöre, her hata için ayrı bir dosya olarak kaydeder.
    Bu yöntem, birden fazla makinenin aynı anda log yazmasından kaynaklanan çakışmaları önler.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        
        # Benzersiz dosya adı için gerekli bilgileri al
        instance_name = get_metadata("instance/name") or "unknown-instance"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # 1. Tam hata detayını 'hatalarblogu' klasörüne kaydet
        error_log_filename = f"hatalarblogu/{timestamp}-{instance_name}.log"
        error_blob = bucket.blob(error_log_filename)
        
        log_content = (
            f"Zaman Damgası: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Makine: {instance_name}\n"
            f"Başlık: {title or 'N/A'}\n\n"
            f"--- HATA DETAYI ---\n{error_details}"
        )
        
        error_blob.upload_from_string(log_content, content_type="text/plain; charset=utf-8")
        logging.info(f"Tam hata detayı GCS'e kaydedildi: gs://{bucket_name}/{error_log_filename}")

        # 2. Sadece başlığı 'tamamlanamayanbasliklar' klasörüne kaydet
        if title:
            failed_title_filename = f"tamamlanamayanbasliklar/{timestamp}-{instance_name}.txt"
            title_blob = bucket.blob(failed_title_filename)
            title_blob.upload_from_string(title, content_type="text/plain; charset=utf-8")
            logging.info(f"Tamamlanamayan başlık GCS'e kaydedildi: gs://{bucket_name}/{failed_title_filename}")

    except Exception as e:
        # Bu fonksiyonun kendisi hata verirse, ana loglara yaz
        logging.error(f"!!! GCS'e HATA LOGU YAZILIRKEN KRİTİK HATA OLUŞTU: {e}")

# --- Diğer Yardımcı Fonksiyonlar (Değiştirilmedi) ---
def shutdown_instance_group():
    # ... (Bu fonksiyon aynı kalır) ...

# --- ANA İŞ AKIŞI ---
def main_loop():
    storage_client = storage.Client()
    idle_start_time = None
    logging.info("🚀 Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")
    
    worker_project_id = os.environ.get("GCP_PROJECT") or get_metadata("project/project-id")
    if not worker_project_id:
        logging.critical("❌ Makinenin Proje ID'si alınamadı! Worker durduruluyor.")
        return

    while True:
        story_title = None
        temp_dir = None
        try:
            (
                story_content,
                story_title_from_module,
                protagonist_profile,
                formatted_text
            ) = hikayeuretir.run_story_generation_process(KAYNAK_BUCKET_ADI, CIKTI_BUCKET_ADI, worker_project_id)
            
            story_title = story_title_from_module

            if not story_title:
                # ... (Otomatik kapanma mantığı aynı) ...
                continue
            
            idle_start_time = None
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            
            # ... (Tüm video üretim adımları aynı) ...
            
            logging.info(f"🎉🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(f"❌ HATA OLUŞTU: '{story_title}' başlıklı video üretilemedi. ❌")
            # GÜNCELLENMİŞ HATA KAYDI ÇAĞRISI
            log_error_to_gcs(storage_client, CIKTI_BUCKET_ADI, story_title, error_details)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
