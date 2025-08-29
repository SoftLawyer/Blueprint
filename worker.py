# worker.py (v12 - The Creator's Blueprint Uyumlu)

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
# GÜNCELLEME: Artık her video için yeni metin ve ses üreteceğiz, ama görseller sabit olacak.
import icerik_uretici_local_v3 as icerik_uretici # Yeni metin üretici
import ses_uretici_local as ses_uretici # Yeni ses üretici
import videoyapar 
import kucukresimolusturur # Bu modül sabit 'kucukresimicinfoto.png' kullanacak

from google.cloud import storage
from google.api_core import exceptions

# --- DETAYLI LOGGING AYARLARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger()
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# --- SABİT DEĞİŞKENLER ---
KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"
HATA_BUCKET_ADI = "video-fabrikam-hatalar"
IDLE_SHUTDOWN_SECONDS = 600 # 10 dakika

# --- Yardımcı Fonksiyonlar (Değişiklik yok) ---
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
                current_content = blob.download_as_text() if blob.exists() else ""
                current_generation = blob.generation if blob.exists() else 0
                updated_content = content_to_prepend + current_content
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

# --- ANA İŞ AKIŞI ---
def main_loop():
    storage_client = storage.Client()
    idle_start_time = None
    
    logging.info("🚀 'The Creator's Blueprint' Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")
    logging.info("=" * 80)
    
    while True:
        story_title = None
        temp_dir = None
        try:
            logging.info("\n🔍 Yeni video konusu aranıyor...")
            
            # ADIM 1: İÇERİK ÜRETİMİ
            logging.info("📚 İÇERİK ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            
            # Not: Bu fonksiyon artık yerel dosyalarla çalışıyor. GCS versiyonu için hikayeuretir'i kullanın.
            # Bu örnekte, yerel dosyaların GCS ile senkronize olduğunu varsayıyoruz.
            formatted_text, story_title = icerik_uretici.run_script_generation_process_for_worker()

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
            
            idle_start_time = None # İş bulunduğu için sayacı sıfırla
            logging.info(f"🎯 YENİ VİDEO BAŞLADI: '{story_title}'")
            logging.info("=" * 80)
            
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            logging.info(f"📁 Geçici dizin oluşturuldu: {temp_dir}")
            
            # ADIM 2: SES VE ALTYAZI ÜRETİMİ
            logging.info("\n🎵 SES VE ALTYAZI ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            audio_file_path, srt_file_path = ses_uretici.run_audio_and_srt_process(formatted_text, temp_dir)
            logging.info("✅ Ses ve altyazı dosyaları hazır")

            # GÜNCELLEME: Sabit varlıkları GCS'ten indiriyoruz.
            logging.info("\n🎨 SABİT GÖRSEL VARLIKLAR İNDİRİLİYOR")
            logging.info("-" * 50)
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            
            # Video için kullanılacak ana sunucu fotoğrafı
            leo_photo_blob = kaynak_bucket.blob("leo_final.png")
            leo_photo_path = os.path.join(temp_dir, "leo_final.png")
            leo_photo_blob.download_to_filename(leo_photo_path)
            logging.info("✅ 'leo_final.png' indirildi.")

            # Küçük resim için kullanılacak özel fotoğraf
            thumbnail_photo_blob = kaynak_bucket.blob("kucukresimicinfoto.png")
            thumbnail_photo_path = os.path.join(temp_dir, "kucukresimicinfoto.png")
            thumbnail_photo_blob.download_to_filename(thumbnail_photo_path)
            logging.info("✅ 'kucukresimicinfoto.png' indirildi.")

            # ADIM 3: KÜÇÜK RESİM ÜRETİMİ
            logging.info("\n🖼️ KÜÇÜK RESİM ÜRETİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(
                story_text=formatted_text,
                profile_photo_path=thumbnail_photo_path, # İndirilen özel fotoğrafı kullan
                output_dir=temp_dir
            )
            logging.info("✅ Küçük resim hazırlandı")

            # ADIM 4: ARKAPLAN VİDEOSU SEÇİMİ
            logging.info("\n🎬 ARKAPLAN VİDEOSU SEÇİM SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            bg_video_path = get_random_background_video(storage_client, temp_dir)

            # ADIM 5: VİDEO OLUŞTURMA SÜRECİ
            logging.info("\n🎥 VİDEO OLUŞTURMA SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            # Sabit "Leo" karakteri için sahte bir profil metni oluşturuyoruz
            leo_profile_text = "Protagonist: Leo" 
            final_video_path = videoyapar.run_video_creation(
                bg_video_path=bg_video_path, 
                audio_path=audio_file_path, 
                srt_path=srt_file_path, 
                profile_photo_path=leo_photo_path, # İndirilen Leo fotoğrafını kullan
                protagonist_profile=leo_profile_text, # Sabit "Leo" adını kullan
                output_dir=temp_dir
            )
            logging.info("✅ Final video oluşturuldu")

            # ADIM 6: DOSYALARI YÜKLEME SÜRECİ
            logging.info("\n☁️ DOSYALARI GCS'E YÜKLEME SÜRECİ BAŞLADI")
            logging.info("-" * 50)
            
            cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
            safe_folder_name = "".join(c for c in story_title if c.isalnum() or c in " -_").rstrip()
            
            # GÜNCELLEME: Yüklenecek dosya listesi yeni stratejiye göre düzenlendi.
            files_to_upload = {
                "nihai_video.mp4": final_video_path,
                "kucuk_resim.png": final_thumbnail_path,
                "altyazi.srt": srt_file_path,
                "ses.wav": audio_file_path,
                "icerik.txt": os.path.join(temp_dir, "icerik.txt") # icerik_uretici'nin kaydettiği dosya
            }
            
            for filename, local_path in files_to_upload.items():
                if local_path and os.path.exists(local_path):
                    logging.info(f"📤 Yükleniyor: {filename}")
                    blob = cikti_bucket.blob(f"{safe_folder_name}/{filename}")
                    blob.upload_from_filename(local_path)
                    logging.info(f"✅ Yüklendi: {filename}")
                else:
                    logging.warning(f"⚠️ Dosya bulunamadı, yükleme atlandı: {filename}")
            
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
    # Bu scriptin doğrudan çalıştırılması, GCS ortamı dışında test amaçlıdır.
    # Gerçek operasyon için bir VM üzerinde veya benzeri bir ortamda çalıştırılmalıdır.
    main_loop()
