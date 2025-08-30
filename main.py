# main.py - Yerel Kontrolcüye Rapor Veren Orkestra Şefi

import os
import logging
import traceback
import tempfile
import shutil
from flask import Flask, request, jsonify
from google.cloud import storage

# Kendi modüllerimizi import edelim
import hikayeuretir
import googleilesesolustur
# profilfotoolusturur ve profilfotonunarkasinisiler artık kullanılmıyor
import videoyapar
import kucukresimolusturur

# --- TEMEL AYARLAR ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- SABİT DEĞİŞKENLER (GÜNCELLENDİ) ---
KAYNAK_BUCKET_ADI = "video-fabrikasi-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikasi-ciktilar"
PROJECT_ID = "video-fabrikasi" 

app = Flask(__name__)

@app.route("/", methods=["POST"])
def video_fabrikasi_baslat():
    """
    Bu fonksiyon, bir POST isteği aldığında tüm video üretim hattını tetikler.
    Bu artık ana çalışma yöntemi olmasa da, tutarlılık için güncellenmiştir.
    """
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    logging.info(f"🚀 Yeni üretim süreci başlatıldı. Geçici klasör: {temp_dir}")
    
    story_title = "" 
    
    try:
        # ==============================================================================
        # ADIM 1: KONU SEÇİMİ (GCS'den)
        # ==============================================================================
        storage_client = storage.Client()
        kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
        titles_blob = kaynak_bucket.blob("creator_blueprint_titles.txt")
        
        if not titles_blob.exists():
            logging.warning("İşlenecek yeni konu bulunamadı (creator_blueprint_titles.txt yok). Üretim bandı durduruldu.")
            return jsonify({"status": "finished", "message": "No new topics to process."}), 200

        all_titles = titles_blob.download_as_text(encoding="utf-8").strip().splitlines()
        if not all_titles:
            logging.warning("İşlenecek yeni konu bulunamadı (dosya boş). Üretim bandı durduruldu.")
            return jsonify({"status": "finished", "message": "No new topics to process."}), 200

        story_title = all_titles[0]
        remaining_titles = "\n".join(all_titles[1:])
        titles_blob.upload_from_string(remaining_titles, content_type="text/plain; charset=utf-8")
        logging.info(f"🔹 '{story_title}' başlığı GCS'den alındı.")

        # ==============================================================================
        # ADIM 2: HİKAYE ÜRETİMİ
        # ==============================================================================
        logging.info("[ADIM 2/7] Hikaye oluşturuluyor...")
        formatted_text = hikayeuretir.run_script_generation_process(PROJECT_ID, story_title)
        if not formatted_text:
            raise Exception(f"'{story_title}' için metin üretilemedi.")
        logging.info(f"✅ Hikaye başarıyla oluşturuldu.")
        
        hikaye_path = os.path.join(temp_dir, "hikaye.txt")
        with open(hikaye_path, "w", encoding="utf-8") as f:
            f.write(formatted_text)
        logging.info(f"💾 Hikaye geçici olarak kaydedildi.")

        # ==============================================================================
        # ADIM 3: SESLENDİRME VE ALTYAZI
        # ==============================================================================
        logging.info("[ADIM 3/7] Seslendirme ve altyazı üretimi başlıyor...")
        audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(
            story_text=formatted_text,
            output_dir=temp_dir,
            project_id=PROJECT_ID
        )
        logging.info("✅ Ses ve altyazı başarıyla oluşturuldu.")
        
        # ==============================================================================
        # ADIM 4: GEREKLİ GÖRSEL VARLIKLARI İNDİRME
        # ==============================================================================
        logging.info("[ADIM 4/7] Gerekli görseller indiriliyor...")
        
        # Profil fotoğrafı
        leo_photo_blob = kaynak_bucket.blob("leo_final.png")
        leo_photo_path = os.path.join(temp_dir, "leo_final.png")
        leo_photo_blob.download_to_filename(leo_photo_path)
        
        # Thumbnail fotoğrafı
        thumbnail_photo_blob = kaynak_bucket.blob("kucukresimicinfoto.png")
        thumbnail_photo_path = os.path.join(temp_dir, "kucukresimicinfoto.png")
        thumbnail_photo_blob.download_to_filename(thumbnail_photo_path)
        
        logging.info("✅ Gerekli görseller indirildi.")

        # ==============================================================================
        # ADIM 5: YOUTUBE KÜÇÜK RESMİ OLUŞTURMA
        # ==============================================================================
        logging.info("[ADIM 5/7] YouTube küçük resmi oluşturuluyor...")
        final_thumbnail_path = kucukresimolusturur.run_thumbnail_generation(
            story_text=formatted_text,
            profile_photo_path=thumbnail_photo_path,
            output_dir=temp_dir,
            worker_project_id=PROJECT_ID
        )
        logging.info("✅ YouTube küçük resmi başarıyla oluşturuldu.")
        
        # ==============================================================================
        # ADIM 6: VİDEO BİRLEŞTİRME
        # ==============================================================================
        logging.info("[ADIM 6/7] Video birleştirme işlemi başlıyor...")
        
        # Arka plan videosu indirme
        bg_video_path = get_random_background_video(storage_client, temp_dir)

        final_video_path = videoyapar.run_video_creation(
            bg_video_path=bg_video_path,
            audio_path=audio_file_path,
            srt_path=srt_file_path,
            profile_photo_path=leo_photo_path,
            output_dir=temp_dir
        )
        logging.info("✅ Video başarıyla birleştirildi.")

        # ==============================================================================
        # ADIM 7: PAKETLEME VE TESLİMAT (CLOUD STORAGE'A YÜKLEME)
        # ==============================================================================
        logging.info("[ADIM 7/7] Üretilen dosyalar Cloud Storage'a yükleniyor...")
        cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
        safe_folder_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in story_title)

        files_to_upload = {
            "nihai_video.mp4": final_video_path,
            "kucuk_resim.png": final_thumbnail_path,
            "altyazi.srt": srt_file_path,
            "ses.wav": audio_file_path,
            "hikaye.txt": hikaye_path
        }

        for filename, local_path in files_to_upload.items():
            if os.path.exists(local_path):
                blob_path = f"{safe_folder_name}/{filename}"
                blob = cikti_bucket.blob(blob_path)
                blob.upload_from_filename(local_path)
                logging.info(f"  -> Yüklendi: {blob_path}")
        
        logging.info("✅ Tüm dosyalar başarıyla Cloud Storage'a yüklendi.")

        logging.info("🎉🎉🎉 ÜRETİM BANDI BAŞARIYLA TAMAMLANDI! 🎉🎉🎉")
        return jsonify({
            "status": "success",
            "message": f"Video for '{story_title}' was successfully generated and uploaded.",
            "processed_title": story_title
        }), 200

    except Exception as e:
        error_message = f"Üretim bandında '{story_title}' işlenirken hata oluştu: {e}"
        logging.error(error_message, exc_info=True)
        return jsonify({
            "status": "error",
            "message": error_message,
            "failed_title": story_title
        }), 500

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logging.info(f"🧹 Geçici klasör temizlendi: {temp_dir}")

def get_random_background_video(storage_client, temp_dir):
    try:
        bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
        blobs = list(bucket.list_blobs(prefix="arkaplan_videolari/"))
        video_blobs = [b for b in blobs if b.name.endswith(".mp4") and b.size > 0]
        if not video_blobs:
            raise FileNotFoundError("'arkaplan_videolari' klasöründe video bulunamadı.")
        random_blob = random.choice(video_blobs)
        bg_video_path = os.path.join(temp_dir, os.path.basename(random_blob.name))
        random_blob.download_to_filename(bg_video_path)
        return bg_video_path
    except Exception as e:
        logging.error(f"❌ Arka plan videosu indirilirken hata: {e}")
        raise

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

