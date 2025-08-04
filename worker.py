# worker.py - Video Fabrikası İşçi Scripti
# Bu script, sanal makinede sürekli çalışarak GCS'ten görevleri alır ve video üretir.

import os
import logging
import traceback
import tempfile
import shutil
import time
from datetime import datetime

# Projenizdeki mevcut modülleri import ediyoruz
import hikayeuretir
import googleilesesolustur
import profilfotoolusturur
import profilfotonunarkasinisiler
import videoyapar
import kucukresimolusturur

from google.cloud import storage

# --- TEMEL AYARLAR ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"
HATALI_BASLIKLAR_DOSYASI = "tamamlanamayanbasliklar.txt"

def get_and_lock_title(storage_client, bucket_name, source_filename="hikayelerbasligi.txt"):
    """
    GCS'ten bir başlık alır ve birden fazla worker'ın aynı başlığı almasını önler.
    Bu basit bir "optimistic locking" yöntemidir.
    """
    kaynak_bucket = storage_client.bucket(bucket_name)
    blob = kaynak_bucket.blob(source_filename)

    for attempt in range(5): # Çakışma durumunda birkaç kez dene
        try:
            # Blob'un mevcut "generation" numarasını al. Bu, dosyanın o anki versiyonudur.
            blob.reload()
            current_generation = blob.generation

            lines = blob.download_as_text(encoding="utf-8").strip().splitlines()
            
            if not lines:
                return None # İşlenecek başlık yok

            title_to_process = lines[0].strip()
            remaining_lines = "\n".join(lines[1:])

            # Dosyayı GÜNCELLERKEN, sadece bizim okuduğumuz versiyon ise güncellemeye izin ver.
            # Eğer başka bir worker bizden önce dosyayı güncellediyse, "generation" numarası değişir
            # ve bu komut hata verir (PreconditionFailed).
            blob.upload_from_string(remaining_lines, content_type="text/plain; charset=utf-8", if_generation_match=current_generation)
            
            logging.info(f"Başlık başarıyla alındı ve kilitlendi: '{title_to_process}'")
            return title_to_process

        except exceptions.PreconditionFailed:
            logging.warning(f"Başlık çakışması tespit edildi. Başka bir worker başlığı aldı. Tekrar deneniyor... ({attempt+1}/5)")
            time.sleep(2) # Kısa bir süre bekle ve tekrar dene
        except Exception as e:
            logging.error(f"Başlık alınırken beklenmedik hata: {e}")
            return None
    
    logging.error("Başlık çakışması çözülemedi. Bir süre sonra tekrar denenecek.")
    return None


def log_failed_title(title, error_details):
    """
    Başarısız olan video başlığını ve hata detayını yerel dosyaya yazar.
    """
    try:
        with open(HATALI_BASLIKLAR_DOSYASI, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] - BAŞLIK: {title}\n")
            f.write(f"HATA DETAYI: {error_details}\n")
            f.write("-" * 50 + "\n")
        logging.info(f"Hatalı başlık dosyaya kaydedildi: {title}")
    except Exception as e:
        logging.error(f"Hatalı başlık dosyasına yazılırken hata oluştu: {e}")

def main_loop():
    """
    Ana işçi döngüsü. Sürekli çalışır ve görevleri işler.
    """
    storage_client = storage.Client()
    logging.info("🚀 Video Fabrikası İşçisi başlatıldı. Görev bekleniyor...")

    while True:
        story_title = None
        temp_dir = None
        
        try:
            # 1. ADIM: GÖREV ALMA
            # story_title = get_and_lock_title(storage_client, KAYNAK_BUCKET_ADI)
            
            # NOT: hikayeuretir modülünüz zaten başlık alıp güncellemeyi yapıyor.
            # Şimdilik onu kullanmaya devam edelim. Daha sonra yukarıdaki kilitli
            # fonksiyona geçilebilir.
            
            # ==============================================================================
            # ADIM 2: HİKAYE ÜRETİMİ
            # ==============================================================================
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
                logging.info("İşlenecek yeni konu bulunamadı. 1 dakika bekleniyor...")
                time.sleep(60)
                continue # Döngünün başına dön

            logging.info(f"✅ Hikaye başarıyla oluşturuldu. Başlık: '{story_title}'")
            
            # Geçici bir klasör oluştur
            temp_dir = tempfile.mkdtemp()
            logging.info(f"Geçici çalışma klasörü oluşturuldu: {temp_dir}")

            formatted_story_path = os.path.join(temp_dir, "hikaye_formatli.txt")
            with open(formatted_story_path, "w", encoding="utf-8") as f:
                f.write(formatted_text)

            # ==============================================================================
            # ADIM 3: SESLENDİRME VE ALTYAZI
            # ==============================================================================
            logging.info("Seslendirme ve senkronize altyazı üretimi başlıyor...")
            audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(
                story_text=formatted_text,
                output_dir=temp_dir,
                api_keys_list=api_keys
            )
            if not audio_file_path or not srt_file_path:
                raise Exception("Ses veya altyazı dosyası oluşturulamadı.")
            logging.info("✅ Ses ve altyazı başarıyla oluşturuldu.")

            # ==============================================================================
            # ADIM 4: PROFİL FOTOĞRAFI ÜRETİMİ
            # ==============================================================================
            logging.info("Profil fotoğrafı üretimi başlıyor...")
            original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(
                protagonist_profile=protagonist_profile,
                output_dir=temp_dir
            )
            if not original_photo_path or not thumbnail_photo_path:
                raise Exception("Profil fotoğrafı veya küçük resim için fotoğraf üretilemedi.")
            logging.info("✅ Profil fotoğrafı ve küçük resim versiyonu başarıyla üretildi.")

            # ==============================================================================
            # ADIM 5: ARKA PLAN TEMİZLEME
            # ==============================================================================
            logging.info("Profil fotoğrafının arka planı temizleniyor...")
            cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(
                input_path=original_photo_path,
                output_dir=temp_dir
            )
            if not cleaned_photo_path:
                raise Exception("Profil fotoğrafının arka planı temizlenemedi.")
            logging.info("✅ Arka plan başarıyla temizlendi.")

            # ==============================================================================
            # ADIM 6: VİDEO BİRLEŞTİRME
            # ==============================================================================
            logging.info("Video birleştirme işlemi başlıyor...")
            
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
            bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
            bg_video_blob.download_to_filename(bg_video_path)

            final_video_path = videoyapar.run_video_creation(
                bg_video_path=bg_video_path,
                audio_path=audio_file_path,
                srt_path=srt_file_path,
                profile_photo_path=cleaned_photo_path,
                protagonist_profile=protagonist_profile,
                output_dir=temp_dir
            )
            if not final_video_path:
                raise Exception("Nihai video dosyası oluşturulamadı.")
            logging.info("✅ Video başarıyla birleştirildi.")

            # ==============================================================================
            # ADIM 7: YOUTUBE KÜÇÜK RESMİ OLUŞTURMA
            # ==============================================================================
            logging.info("YouTube küçük resmi oluşturuluyor...")
            final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(
                story_text=formatted_text,
                profile_photo_path=thumbnail_photo_path,
                output_dir=temp_dir,
                api_keys=api_keys
            )
            if not final_thumbnail_path:
                raise Exception("YouTube küçük resmi oluşturulamadı.")
            logging.info("✅ YouTube küçük resmi başarıyla oluşturuldu.")

            # ==============================================================================
            # ADIM 8: ÇIKTILARI GCS'E YÜKLEME
            # ==============================================================================
            logging.info("Üretilen dosyalar Cloud Storage'a yükleniyor...")
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
                    blob_path = f"{safe_folder_name}/{filename}"
                    blob = cikti_bucket.blob(blob_path)
                    blob.upload_from_filename(local_path)
                    logging.info(f"  -> Yüklendi: {blob_path}")
            
            logging.info(f"🎉🎉🎉 ÜRETİM BAŞARIYLA TAMAMLANDI: '{story_title}' 🎉🎉🎉")

        except Exception as e:
            # Hata yakalama bloğu
            error_details = traceback.format_exc()
            logging.error(f"❌ HATA OLUŞTU: '{story_title}' başlıklı video üretilemedi. ❌")
            logging.error(error_details)
            if story_title:
                log_failed_title(story_title, str(e))

        finally:
            # Geçici klasörü her durumda temizle
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logging.info(f"Geçici klasör temizlendi: {temp_dir}")
            
            # Bir sonraki döngüden önce kısa bir mola
            logging.info("-" * 80)
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
