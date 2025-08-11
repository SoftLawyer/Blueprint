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

# --- Diğer Yardımcı Fonksiyonlar (DÜZELTİLDİ) ---
def shutdown_instance_group():
    """Mevcut sanal makinenin ait olduğu Yönetilen Örnek Grubunu (MIG) kapatır."""
    logging.warning("10 dakikadır boşta. Kapatma prosedürü başlatılıyor...")
    try:
        # Önce zone bilgisini al (örn: projects/12345/zones/europe-west1-b)
        zone_full = get_metadata("instance/zone")
        if not zone_full:
            logging.error("Zone bilgisi alınamadığı için kapatma işlemi iptal edildi.")
            return
        zone = zone_full.split('/')[-1]

        # Sonra instance adını al
        instance_name = get_metadata("instance/name")
        if not instance_name:
            logging.error("Instance adı alınamadığı için kapatma işlemi iptal edildi.")
            return

        # Instance adından grup adını bul
        if "fabrika-isci" in instance_name:
            group_name = "video-fabrikasi-grubu" # Rehberdeki isme göre sabitlendi
            logging.info(f"Ait olunan grup: {group_name}, Zone: {zone}")

            # Grubu kapatma (boyutunu 0'a indirme) komutunu çalıştır
            command = [
                "gcloud", "compute", "instance-groups", "managed",
                "resize", group_name,
                "--size=0",
                f"--zone={zone}",
                "--quiet" # Onay istemeden çalıştır
            ]
            subprocess.run(command, check=True)
            logging.info(f"{group_name} başarıyla kapatıldı.")
        else:
            logging.warning("Bu makine bir yönetilen gruba ait görünmüyor. Kapatma işlemi atlandı.")

    except subprocess.CalledProcessError as e:
        logging.error(f"Instance grubunu kapatırken hata oluştu: {e}")
    except Exception as e:
        logging.error(f"Kapatma prosedüründe beklenmedik bir hata: {e}")

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

            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(formatted_text, temp_dir, worker_project_id)
            original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(protagonist_profile, temp_dir)
            cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(original_photo_path, temp_dir)
            
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
            bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
            bg_video_blob.download_to_filename(bg_video_path)
            
            final_video_path = videoyapar.run_video_creation(bg_video_path, audio_file_path, srt_file_path, cleaned_photo_path, protagonist_profile, temp_dir)
            
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(formatted_text, thumbnail_photo_path, temp_dir)
            
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
            log_error_to_gcs(storage_client, CIKTI_BUCKET_ADI, story_title, error_details)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
