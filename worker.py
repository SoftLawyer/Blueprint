# worker.py (v15 - Nihai Sürüm)

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

# Projenizdeki güncellenmiş modülleri import ediyoruz
import hikayeuretir
import googleilesesolustur
import videoyapar
import kucukresimolusturur

from google.cloud import storage
from google.api_core import exceptions

# --- LOGGING AYARLARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- SABİT DEĞİŞKENLER (GÜNCELLENDİ) ---
KAYNAK_BUCKET_ADI = "video-fabrikasi-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikasi-ciktilar"
HATA_BUCKET_ADI = "video-fabrikasi-hatalar"
IDLE_SHUTDOWN_SECONDS = 600  # 10 dakika
PROJECT_ID = "video-fabrikasi" # Proje ID'niz buraya sabitlendi

# --- YARDIMCI FONKSİYONLAR ---

def get_metadata(metadata_path):
    """VM metadata sunucusundan bilgi alır."""
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
    """Boşta kalan instance grubunu kapatır."""
    logging.warning(f"🔴 {IDLE_SHUTDOWN_SECONDS / 60:.0f} dakikadır boşta. Kapatma prosedürü başlatılıyor...")
    try:
        zone_full = get_metadata("instance/zone")
        instance_name = get_metadata("instance/name")
        if not zone_full or not instance_name:
            logging.error("❌ Zone veya instance adı alınamadığı için kapatma işlemi iptal edildi.")
            return
        zone = zone_full.split('/')[-1]
        # Instance adından grup adını tahmin et
        if "-group-" in instance_name:
             group_name = instance_name.rsplit("-group-", 1)[0] + "-group"
        else: # Standart isimlendirme
             group_name = instance_name.rsplit('-', 1)[0]

        logging.info(f"Kapatılacak grup adı: {group_name}, Bölge: {zone}")
        command = ["gcloud", "compute", "instance-groups", "managed", "resize", group_name, "--size=0", f"--zone={zone}", "--quiet"]
        subprocess.run(command, check=True)
        logging.info(f"✅ {group_name} başarıyla kapatıldı.")
    except Exception as e:
        logging.error(f"❌ Instance grubunu kapatırken hata oluştu: {e}", exc_info=True)

def get_random_background_video(storage_client, temp_dir):
    """Cloud Storage'dan rastgele bir arka plan videosu seçer ve indirir."""
    try:
        bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
        blobs = list(bucket.list_blobs(prefix="arkaplan_videolari/"))
        video_blobs = [b for b in blobs if b.name.lower().endswith((".mp4", ".mov")) and b.size > 0]
        if not video_blobs:
            raise FileNotFoundError(f"'{KAYNAK_BUCKET_ADI}/arkaplan_videolari/' klasöründe video bulunamadı.")
        random_blob = random.choice(video_blobs)
        logging.info(f"📹 Rastgele arka plan videosu seçildi: {random_blob.name}")
        bg_video_path = os.path.join(temp_dir, os.path.basename(random_blob.name))
        random_blob.download_to_filename(bg_video_path)
        logging.info(f"✅ Arka plan videosu indirildi: {bg_video_path}")
        return bg_video_path
    except Exception as e:
        logging.error(f"❌ Arka plan videosu seçilirken/indirilirken hata oluştu: {e}")
        raise

def log_error_to_gcs(storage_client, bucket_name, title, error_details):
    """Hata detaylarını GCS'e loglar."""
    instance_name = get_metadata("instance/name") or "unknown-instance"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_content = (
        f"Zaman Damgası: {timestamp}\n"
        f"Makine: {instance_name}\n"
        f"Başlık: {title or 'N/A'}\n"
        f"--- HATA DETAYI ---\n{error_details}\n"
        f"{'='*80}\n\n"
    )
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob("hatalarblogu.txt")
        current_content = blob.download_as_text() if blob.exists() else ""
        blob.upload_from_string(log_content + current_content, content_type="text/plain; charset=utf-8")
        logging.info("📝 Hata logu GCS'e yazıldı.")
    except Exception as e:
        logging.error(f"🚨 GCS'e HATA LOGU YAZILIRKEN KRİTİK HATA OLUŞTU: {e}")

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
            
            # ADIM 1: GCS'den işlenecek konuyu al
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            titles_blob = kaynak_bucket.blob("creator_blueprint_titles.txt")
            if not titles_blob.exists():
                logging.warning(f"{KAYNAK_BUCKET_ADI}/creator_blueprint_titles.txt bulunamadı. Boşta bekleniyor.")
                all_titles = []
            else:
                all_titles = titles_blob.download_as_text(encoding="utf-8").strip().splitlines()

            if not all_titles:
                story_title = None
            else:
                story_title = all_titles[0]
                remaining_titles = "\n".join(all_titles[1:])
                titles_blob.upload_from_string(remaining_titles, content_type="text/plain; charset=utf-8")
                logging.info(f"🔹 '{story_title}' başlığı GCS'den alındı. Kalan başlık sayısı: {len(all_titles) - 1}")

            if not story_title:
                if idle_start_time is None:
                    idle_start_time = time.time()
                if (time.time() - idle_start_time) > IDLE_SHUTDOWN_SECONDS:
                    shutdown_instance_group()
                    break
                logging.info(f"😴 İşlenecek yeni konu bulunamadı. Kapanmadan önce {int(IDLE_SHUTDOWN_SECONDS - (time.time() - idle_start_time))} saniye beklenecek.")
                time.sleep(60)
                continue
            
            idle_start_time = None # İş bulunduğu için sayacı sıfırla
            logging.info(f"🎯 YENİ VİDEO BAŞLADI: '{story_title}'")
            logging.info("=" * 80)

            # ADIM 2: HİKAYE METNİNİ ÜRET
            formatted_text = hikayeuretir.run_script_generation_process(PROJECT_ID, story_title)
            if not formatted_text:
                 raise Exception(f"'{story_title}' için metin üretilemedi.")
            
            temp_dir = tempfile.mkdtemp(dir="/tmp")
            logging.info(f"📁 Geçici dizin oluşturuldu: {temp_dir}")
            hikaye_path = os.path.join(temp_dir, "hikaye.txt")
            with open(hikaye_path, "w", encoding="utf-8") as f: f.write(formatted_text)
            
            # ADIM 3: SES VE ALTYAZI ÜRET
            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(formatted_text, temp_dir, PROJECT_ID)

            # ADIM 4: GEREKLİ GÖRSEL VARLIKLARI İNDİR
            leo_photo_blob = kaynak_bucket.blob("leo_final.png")
            leo_photo_path = os.path.join(temp_dir, "leo_final.png")
            leo_photo_blob.download_to_filename(leo_photo_path)
            logging.info("✅ 'leo_final.png' (profil fotoğrafı) indirildi.")

            thumbnail_photo_blob = kaynak_bucket.blob("kucukresimicinfoto.png")
            thumbnail_photo_path = os.path.join(temp_dir, "kucukresimicinfoto.png")
            thumbnail_photo_blob.download_to_filename(thumbnail_photo_path)
            logging.info("✅ 'kucukresimicinfoto.png' (thumbnail için) indirildi.")

            # ADIM 5: KÜÇÜK RESİM ÜRET
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(
                story_text=formatted_text,
                profile_photo_path=thumbnail_photo_path,
                output_dir=temp_dir,
                worker_project_id=PROJECT_ID
            )

            # ADIM 6: RASTGELE ARKAPLAN VİDEOSU SEÇ
            bg_video_path = get_random_background_video(storage_client, temp_dir)

            # ADIM 7: VİDEOYU OLUŞTUR
            final_video_path = videoyapar.run_video_creation(
                bg_video_path=bg_video_path, 
                audio_path=audio_file_path, 
                srt_path=srt_file_path, 
                profile_photo_path=leo_photo_path,
                output_dir=temp_dir
            )

            # ADIM 8: ÜRETİLEN DOSYALARI YÜKLE
            cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
            safe_folder_name = "".join(c for c in story_title if c.isalnum() or c in " -_").rstrip()
            
            files_to_upload = {
                "nihai_video.mp4": final_video_path,
                "kucuk_resim.png": final_thumbnail_path,
                "altyazi.srt": srt_file_path,
                "ses.wav": audio_file_path,
                "hikaye.txt": hikaye_path
            }
            
            for filename, local_path in files_to_upload.items():
                if local_path and os.path.exists(local_path):
                    logging.info(f"📤 Yükleniyor: {filename}")
                    blob = cikti_bucket.blob(f"{safe_folder_name}/{filename}")
                    blob.upload_from_filename(local_path)
                    logging.info(f"✅ Yüklendi: {filename}")
            
            logging.info("=" * 80)
            logging.info(f"🎉🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")

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
                logging.info(f"🗑️ Geçici dizin temizlendi.")
            logging.info("-" * 80)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()

