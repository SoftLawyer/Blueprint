# worker.py (v11 - Gelişmiş Hata Ayıklama)

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
# YENİ: Hatalar için ayrı bir bucket adı
HATA_BUCKET_ADI = "video-fabrikam-hatalar"
IDLE_SHUTDOWN_SECONDS = 600 # 10 dakika

# --- Yardımcı Fonksiyonlar ---
def get_metadata(metadata_path):
    try:
        response = requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/{metadata_path}",
            headers={'Metadata-Flavor': 'Google'}, timeout=5
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Metadata sunucusundan bilgi alınamadı ({metadata_path}): {e}")
        return None

def shutdown_instance_group():
    logging.warning("10 dakikadır boşta. Kapatma prosedürü başlatılıyor...")
    try:
        zone_full = get_metadata("instance/zone")
        instance_name = get_metadata("instance/name")
        if not zone_full or not instance_name:
            logging.error("Zone veya instance adı alınamadığı için kapatma işlemi iptal edildi.")
            return
        zone = zone_full.split('/')[-1]
        if "fabrika-isci" in instance_name:
            group_name = "video-fabrikasi-grubu"
            command = ["gcloud", "compute", "instance-groups", "managed", "resize", group_name, "--size=0", f"--zone={zone}", "--quiet"]
            subprocess.run(command, check=True)
            logging.info(f"{group_name} başarıyla kapatıldı.")
    except Exception as e:
        logging.error(f"Instance grubunu kapatırken hata oluştu: {e}")

# GÜNCELLENMİŞ: Merkezi ve tek dosyaya yazan hata kaydı fonksiyonu
def _safe_prepend_to_gcs_file(storage_client, bucket_name, filename, content_to_prepend, max_retries=5):
    """
    Bir GCS dosyasının başına, çakışmaları önleyerek, güvenli bir şekilde yeni içerik ekler.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        
        for attempt in range(max_retries):
            try:
                # 1. Dosyanın mevcut halini ve "generation" numarasını oku
                current_content = blob.download_as_text()
                current_generation = blob.generation
            except exceptions.NotFound:
                # Dosya yoksa, boş olarak kabul et
                current_content = ""
                current_generation = 0
            except exceptions.PreconditionFailed:
                logging.warning(f"'{filename}' için GCS çakışması. Tekrar deneniyor... ({attempt + 1})")
                time.sleep(1)
                continue

            # 2. Yeni içeriği eskisinin başına ekle
            updated_content = content_to_prepend + current_content
            
            # 3. Dosyayı, sadece bizim okuduğumuz versiyon ise güncellemeye izin ver
            try:
                blob.upload_from_string(updated_content, content_type="text/plain; charset=utf-8", if_generation_match=current_generation)
                logging.info(f"Log GCS'teki merkezi dosyaya eklendi: gs://{bucket_name}/{filename}")
                return # Başarılı, döngüden çık
            except exceptions.PreconditionFailed:
                logging.warning(f"'{filename}' için GCS yazma çakışması. Tekrar deneniyor... ({attempt + 1})")
                time.sleep(1)
        
        logging.error(f"'{filename}' dosyasına {max_retries} denemeden sonra yazılamadı.")

    except Exception as e:
        logging.error(f"!!! GCS'e HATA LOGU YAZILIRKEN KRİTİK HATA OLUŞTU: {e}")

def log_error_to_gcs(storage_client, bucket_name, title, error_details):
    """Hata loglarını ilgili merkezi dosyalara yönlendirir."""
    instance_name = get_metadata("instance/name") or "unknown-instance"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Detaylı hata logunu oluştur
    log_content = (
        f"Zaman Damgası: {timestamp}\n"
        f"Makine: {instance_name}\n"
        f"Başlık: {title or 'N/A'}\n"
        f"--- HATA DETAYI ---\n{error_details}\n"
        f"{'='*80}\n\n"
    )
    _safe_prepend_to_gcs_file(storage_client, bucket_name, "hatalarblogu.txt", log_content)

    # Sadece tamamlanamayan başlığı kaydet
    if title:
        title_content = f"{timestamp} - {title}\n"
        _safe_prepend_to_gcs_file(storage_client, bucket_name, "tamamlanamayanbasliklar.txt", title_content)

# --- ANA İŞ AKIŞI ---
def main_loop():
    storage_client = storage.Client()
    idle_start_time = None
    logging.info("🚀 Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")
    
    while True:
        story_title = None
        temp_dir = None
        try:
            # YENİ HATA AYIKLAMA LOGLARI
            logging.info("Döngünün başına gelindi. hikayeuretir çağrılacak...")
            
            (
                story_content,
                story_title_from_module,
                protagonist_profile,
                api_keys,
                formatted_text
            ) = hikayeuretir.run_story_generation_process(KAYNAK_BUCKET_ADI, CIKTI_BUCKET_ADI)
            
            # YENİ HATA AYIKLAMA LOGLARI
            logging.info("✅ hikayeuretir başarıyla tamamlandı. Başlık kontrol edilecek...")
            
            story_title = story_title_from_module

            if not story_title:
                if idle_start_time is None:
                    idle_start_time = time.time()
                if time.time() - idle_start_time > IDLE_SHUTDOWN_SECONDS:
                    shutdown_instance_group()
                    break
                logging.info(f"İşlenecek yeni konu bulunamadı. Kapanmaya kalan süre: {int(IDLE_SHUTDOWN_SECONDS - (time.time() - idle_start_time))} saniye.")
                time.sleep(60)
                continue
            
            idle_start_time = None
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            
            formatted_story_path = os.path.join(temp_dir, "hikaye.txt")
            with open(formatted_story_path, "w", encoding="utf-8") as f:
                 f.write(formatted_text)

            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(formatted_text, temp_dir, api_keys)
            original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(protagonist_profile, temp_dir)
            cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(original_photo_path, temp_dir)
            
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(formatted_text, thumbnail_photo_path, temp_dir, api_keys)
            
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
            bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
            bg_video_blob.download_to_filename(bg_video_path)
            final_video_path = videoyapar.run_video_creation(bg_video_path, audio_file_path, srt_file_path, cleaned_photo_path, protagonist_profile, temp_dir)
            
            cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
            safe_folder_name = "".join(c for c in story_title if c.isalnum() or c in " -_").rstrip()
            files_to_upload = {
                "nihai_video.mp4": final_video_path, "kucuk_resim.png": final_thumbnail_path,
                "altyazi.srt": srt_file_path, "ses.wav": audio_file_path,
                "hikaye.txt": formatted_story_path, "profil_foto_temiz.png": cleaned_photo_path,
                "profil_foto_orijinal.png": original_photo_path
            }
            for filename, local_path in files_to_upload.items():
                if os.path.exists(local_path):
                    blob = cikti_bucket.blob(f"{safe_folder_name}/{filename}")
                    blob.upload_from_filename(local_path)
            
            logging.info(f"🎉🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(f"❌ HATA OLUŞTU: '{story_title}' başlıklı video üretilemedi. ❌")
            # GÜNCELLENDİ: Hataları yeni bucket'a kaydet
            log_error_to_gcs(storage_client, HATA_BUCKET_ADI, story_title, error_details)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
