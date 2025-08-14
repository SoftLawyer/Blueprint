# worker.py (v11 - Detaylı Süreç Takibi + Random Arkaplan Video)

import os
import logging
import traceback
import tempfile
import shutil
import time
import requests
import subprocess
import random
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

# --- DETAYLI LOGGING AYARLARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Ana logger'ı al
logger = logging.getLogger()

# Console handler ekle (eğer yoksa)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"
HATA_BUCKET_ADI = "video-fabrikam-hatalar"
IDLE_SHUTDOWN_SECONDS = 600

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
    logging.warning("🔴 10 dakikadır boşta. Kapatma prosedürü başlatılıyor...")
    try:
        zone_full = get_metadata("instance/zone")
        instance_name = get_metadata("instance/name")
        if not zone_full or not instance_name:
            logging.error("❌ Zone veya instance adı alınamadığı için kapatma işlemi iptal edildi.")
            return
        zone = zone_full.split('/')[-1]
        if "fabrika-isci" in instance_name:
            group_name = "video-fabrikasi-grubu"
            command = ["gcloud", "compute", "instance-groups", "managed", "resize", group_name, "--size=0", f"--zone={zone}", "--quiet"]
            subprocess.run(command, check=True)
            logging.info(f"✅ {group_name} başarıyla kapatıldı.")
    except Exception as e:
        logging.error(f"❌ Instance grubunu kapatırken hata oluştu: {e}")

def _safe_prepend_to_gcs_file(storage_client, bucket_name, filename, content_to_prepend, max_retries=5):
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        for attempt in range(max_retries):
            try:
                current_content = blob.download_as_text()
                current_generation = blob.generation
            except exceptions.NotFound:
                current_content = ""
                current_generation = 0
            except exceptions.PreconditionFailed:
                logging.warning(f"⚠️ '{filename}' için GCS çakışması. Tekrar deneniyor... ({attempt + 1})")
                time.sleep(1)
                continue
            updated_content = content_to_prepend + current_content
            try:
                blob.upload_from_string(updated_content, content_type="text/plain; charset=utf-8", if_generation_match=current_generation)
                logging.info(f"📝 Log GCS'teki merkezi dosyaya eklendi: gs://{bucket_name}/{filename}")
                return
            except exceptions.PreconditionFailed:
                logging.warning(f"⚠️ '{filename}' için GCS yazma çakışması. Tekrar deneniyor... ({attempt + 1})")
                time.sleep(1)
        logging.error(f"❌ '{filename}' dosyasına {max_retries} denemeden sonra yazılamadı.")
    except Exception as e:
        logging.error(f"🚨 GCS'e HATA LOGU YAZILIRKEN KRİTİK HATA OLUŞTU: {e}")

def log_error_to_gcs(storage_client, bucket_name, title, error_details):
    instance_name = get_metadata("instance/name") or "unknown-instance"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_content = (
        f"Zaman Damgası: {timestamp}\n"
        f"Makine: {instance_name}\n"
        f"Başlık: {title or 'N/A'}\n"
        f"--- HATA DETAYI ---\n{error_details}\n"
        f"{'='*80}\n\n"
    )
    _safe_prepend_to_gcs_file(storage_client, bucket_name, "hatalarblogu.txt", log_content)
    if title:
        title_content = f"{timestamp} - {title}\n"
        _safe_prepend_to_gcs_file(storage_client, bucket_name, "tamamlanamayanbasliklar.txt", title_content)

def get_random_background_video(storage_client, temp_dir):
    """Random arkaplan videosu seçer ve indirir."""
    try:
        logging.info("🎬 Random arkaplan videosu seçiliyor...")
        kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
        
        random_number = random.randint(1, 10)
        selected_video_name = f"arkaplan{random_number}.mp4"
        
        bg_video_blob = kaynak_bucket.blob(selected_video_name)
        if not bg_video_blob.exists():
            logging.warning(f"⚠️ '{selected_video_name}' bulunamadı, arkaplan1.mp4 kullanılacak.")
            selected_video_name = "arkaplan1.mp4"
            bg_video_blob = kaynak_bucket.blob(selected_video_name)
        
        bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
        logging.info(f"📥 Arkaplan videosu indiriliyor: {selected_video_name}")
        bg_video_blob.download_to_filename(bg_video_path)
        
        logging.info(f"✅ Random arkaplan videosu hazır: {selected_video_name}")
        return bg_video_path
        
    except Exception as e:
        logging.error(f"❌ Random arkaplan video seçiminde hata: {e}")
        try:
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan1.mp4")
            bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
            bg_video_blob.download_to_filename(bg_video_path)
            logging.info("✅ Hata nedeniyle varsayılan arkaplan1.mp4 kullanıldı.")
            return bg_video_path
        except Exception as fallback_error:
            logging.error(f"❌ Varsayılan arkaplan videosu da indirilemedi: {fallback_error}")
            raise

# --- ANA İŞ AKIŞI ---
def main_loop():
    storage_client = storage.Client()
    idle_start_time = None
    
    logging.info("🚀 Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")
    logging.info("=" * 80)
    
    worker_project_id = os.environ.get("GCP_PROJECT") or get_metadata("project/project-id")
    if not worker_project_id:
        logging.critical("❌ Makinenin Proje ID'si alınamadı! Worker durduruluyor.")
        return

    while True:
        story_title = None
        temp_dir = None
        try:
            logging.info("\n🔍 Yeni hikaye konusu aranıyor...")
            
            # HİKAYE ÜRETİM SÜRECİ - DETAYLI TAKİP
            logging.info("📚 HİKAYE ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            
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
                    logging.info("⏳ Boşta kalma sayacı başlatıldı...")
                
                remaining_time = int(IDLE_SHUTDOWN_SECONDS - (time.time() - idle_start_time))
                if remaining_time <= 0:
                    shutdown_instance_group()
                    break
                
                logging.info(f"😴 İşlenecek yeni konu bulunamadı. Kapanmaya kalan süre: {remaining_time} saniye.")
                time.sleep(60)
                continue
            
            idle_start_time = None
            logging.info(f"🎯 YENİ HİKAYE BAŞLADI: '{story_title}'")
            logging.info("=" * 80)
            
            # Hikaye içeriği kontrolü
            if not story_content or len(story_content.strip()) < 100:
                logging.error(f"❌ Hikaye içeriği çok kısa veya boş! İçerik uzunluğu: {len(story_content) if story_content else 0}")
                raise Exception("Hikaye içeriği yetersiz")
            
            logging.info(f"✅ Hikaye içeriği hazır ({len(story_content)} karakter)")
            logging.info(f"✅ Kahraman profili hazır ({len(protagonist_profile)} karakter)")
            
            # Geçici dizin oluştur
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            logging.info(f"📁 Geçici dizin oluşturuldu: {temp_dir}")
            
            # Hikaye dosyasını kaydet
            formatted_story_path = os.path.join(temp_dir, "hikaye.txt")
            with open(formatted_story_path, "w", encoding="utf-8") as f:
                f.write(formatted_text)
            logging.info("💾 Hikaye dosyası kaydedildi")

            # SES VE ALTYAZI ÜRETİMİ
            logging.info("\n🎵 SES VE ALTYAZI ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(formatted_text, temp_dir, api_keys)
            logging.info("✅ Ses ve altyazı dosyaları hazır")

            # PROFİL FOTOĞRAFI ÜRETİMİ
            logging.info("\n📸 PROFİL FOTOĞRAFI ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(protagonist_profile, temp_dir)
            logging.info("✅ Profil fotoğrafları oluşturuldu")

            # ARKAPLAN SİLME SÜRECİ
            logging.info("\n🎨 ARKAPLAN SİLME SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(original_photo_path, temp_dir)
            logging.info("✅ Profil fotoğrafı arkaplanı temizlendi")

            # KÜÇÜK RESİM ÜRETİMİ
            logging.info("\n🖼️ KÜÇÜK RESİM ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(formatted_text, thumbnail_photo_path, temp_dir, worker_project_id)
            logging.info("✅ Küçük resim hazırlandı")

            # ARKAPLAN VİDEOSU SEÇİMİ
            logging.info("\n🎬 ARKAPLAN VİDEOSU SEÇİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            bg_video_path = get_random_background_video(storage_client, temp_dir)

            # VİDEO OLUŞTURMA SÜRECİ
            logging.info("\n🎥 VİDEO OLUŞTURMA SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            final_video_path = videoyapar.run_video_creation(bg_video_path, audio_file_path, srt_file_path, cleaned_photo_path, protagonist_profile, temp_dir)
            logging.info("✅ Final video oluşturuldu")

            # DOSYALARI YÜKLEME SÜRECİ
            logging.info("\n☁️ DOSYALARI GCS'E YÜKLEME SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            
            cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
            safe_folder_name = "".join(c for c in story_title if c.isalnum() or c in " -_").rstrip()
            
            files_to_upload = {
                "nihai_video.mp4": final_video_path,
                "kucuk_resim.png": final_thumbnail_path,
                "altyazi.srt": srt_file_path,
                "ses.wav": audio_file_path,
                "hikaye.txt": formatted_story_path,
                "profil_foto_temiz.png": cleaned_photo_path,
                "profil_foto_orijinal.png": original_photo_path
            }
            
            for filename, local_path in files_to_upload.items():
                if os.path.exists(local_path):
                    logging.info(f"📤 Yükleniyor: {filename}")
                    blob = cikti_bucket.blob(f"{safe_folder_name}/{filename}")
                    blob.upload_from_filename(local_path)
                    logging.info(f"✅ Yüklendi: {filename}")
                else:
                    logging.warning(f"⚠️ Dosya bulunamadı: {filename}")
            
            logging.info("=" * 80)
            logging.info(f"🎉🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")
            logging.info("=" * 80)

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error("=" * 80)
            logging.error(f"❌❌❌ HATA OLUŞTU: '{story_title}' başlıklı video üretilemedi ❌❌❌")
            logging.error(f"Hata detayı: {str(e)}")
            logging.error("=" * 80)
            log_error_to_gcs(storage_client, HATA_BUCKET_ADI, story_title, error_details)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logging.info(f"🗑️ Geçici dizin temizlendi: {temp_dir}")
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
