# worker.py - Video Fabrikası İşçi Scripti (v3 - Otomatik Kapanma ve Gelişmiş Hata Kaydı)

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
HATALI_BASLIKLAR_DOSYASI = "tamamlanamayanbasliklar.txt"
HATALAR_LOG_DOSYASI = "hatalarblogu.txt" # Yeni genel hata log dosyası
IDLE_SHUTDOWN_SECONDS = 600 # 10 dakika

# --- YENİ FONKSİYONLAR ---

def get_instance_metadata(metadata_key):
    """Sanal makinenin metadata sunucusundan bilgi alır."""
    try:
        response = requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/instance/{metadata_key}",
            headers={'Metadata-Flavor': 'Google'},
            timeout=5
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Metadata sunucusundan bilgi alınamadı ({metadata_key}): {e}")
        return None

def shutdown_instance_group():
    """Mevcut sanal makinenin ait olduğu Yönetilen Örnek Grubunu (MIG) kapatır."""
    logging.warning("10 dakikadır boşta. Kapatma prosedürü başlatılıyor...")
    try:
        # Önce zone bilgisini al (örn: projects/12345/zones/europe-west1-b)
        zone_full = get_instance_metadata("zone")
        if not zone_full:
            logging.error("Zone bilgisi alınamadığı için kapatma işlemi iptal edildi.")
            return
        zone = zone_full.split('/')[-1]

        # Sonra instance adını al
        instance_name = get_instance_metadata("name")
        if not instance_name:
            logging.error("Instance adı alınamadığı için kapatma işlemi iptal edildi.")
            return

        # Instance adından grup adını bul
        # Not: Bu, base-instance-name'in 'fabrika-isci' olduğu varsayımına dayanır.
        # Eğer base-instance-name değişirse, burası da güncellenmelidir.
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

def log_error_to_gcs(storage_client, bucket_name, filename, title, error_details):
    """Hata loglarını GCS'teki merkezi bir dosyaya ekler."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)

        try:
            existing_content = blob.download_as_text()
        except exceptions.NotFound:
            existing_content = ""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if title:
            new_log_entry = (
                f"[{timestamp}] - BAŞLIK: {title}\n"
                f"HATA ÖZETİ: {error_details.splitlines()[-1]}\n" # Sadece son hata satırı
                f"{'-'*80}\n"
            )
        else: # Genel hatalar için
             new_log_entry = (
                f"[{timestamp}] - GENEL HATA\n"
                f"HATA DETAYI:\n{error_details}\n"
                f"{'-'*80}\n"
            )

        updated_content = new_log_entry + existing_content
        blob.upload_from_string(updated_content, content_type="text/plain; charset=utf-8")
        
        logging.info(f"Hata logu GCS'e kaydedildi: gs://{bucket_name}/{filename}")

    except Exception as e:
        logging.error(f"GCS'teki hata dosyasına ({filename}) yazılırken kritik bir hata oluştu: {e}")

# --- ANA İŞ AKIŞI ---

def main_loop():
    """Ana işçi döngüsü."""
    storage_client = storage.Client()
    idle_start_time = None
    logging.info("🚀 Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")

    while True:
        story_title = None
        temp_dir = None
        
        try:
            logging.info("Yeni bir görev döngüsü başlatılıyor. Konu seçiliyor...")
            (
                story_content,
                story_title_from_module,
                protagonist_profile,
                api_keys,
                formatted_text
            ) = hikayeuretir.run_story_generation_process(KAYNAK_BUCKET_ADI, CIKTI_BUCKET_ADI)

            story_title = story_title_from_module

            if not story_title:
                if idle_start_time is None:
                    idle_start_time = time.time()
                    logging.info("İşlenecek yeni konu bulunamadı. 10 dakikalık otomatik kapanma sayacı başlatıldı...")
                
                elapsed_idle_time = time.time() - idle_start_time
                if elapsed_idle_time > IDLE_SHUTDOWN_SECONDS:
                    shutdown_instance_group()
                    break # Döngüyü sonlandır
                
                remaining_time = IDLE_SHUTDOWN_SECONDS - elapsed_idle_time
                logging.info(f"Sistem boşta. Kapanmaya kalan süre: {int(remaining_time // 60)} dakika {int(remaining_time % 60)} saniye.")
                time.sleep(60)
                continue
            
            # Başlık bulunduğunda sayacı sıfırla
            idle_start_time = None

            logging.info(f"✅ Hikaye başarıyla oluşturuldu. Başlık: '{story_title}'")
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            
            # ... (Video üretim adımlarının geri kalanı aynı)
            # ADIM 2: SESLENDİRME VE ALTYAZI
            # ...
            # ADIM 7: ÇIKTILARI GCS'E YÜKLEME
            # ...
            # (Bu kısımlar bir önceki versiyonla aynı olduğu için kısaltılmıştır)

            formatted_story_path = os.path.join(temp_dir, "hikaye_formatli.txt")
            with open(formatted_story_path, "w", encoding="utf-8") as f:
                f.write(formatted_text)
            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(formatted_text, temp_dir, api_keys)
            original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(protagonist_profile, temp_dir)
            cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(original_photo_path, temp_dir)
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
            bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
            bg_video_blob.download_to_filename(bg_video_path)
            final_video_path = videoyapar.run_video_creation(bg_video_path, audio_file_path, srt_file_path, cleaned_photo_path, protagonist_profile, temp_dir)
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(formatted_text, thumbnail_photo_path, temp_dir, api_keys)
            
            logging.info("Üretilen dosyalar Cloud Storage'a yükleniyor...")
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
            
            logging.info(f"�🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(f"❌ HATA OLUŞTU: '{story_title}' başlıklı video üretilemedi. ❌")
            logging.error(error_details)
            
            # Hataları ilgili dosyalara kaydet
            log_error_to_gcs(storage_client, CIKTI_BUCKET_ADI, HATALAR_LOG_DOSYASI, None, error_details)
            if story_title:
                log_error_to_gcs(storage_client, CIKTI_BUCKET_ADI, HATALI_BASLIKLAR_DOSYASI, story_title, str(e))

        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
�