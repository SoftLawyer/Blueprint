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
import profilfotoolusturur
import profilfotonunarkasinisiler
import videoyapar
import kucukresimolusturur

# --- TEMEL AYARLAR ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def video_fabrikasi_baslat():
    """
    Bu fonksiyon, bir POST isteği aldığında tüm video üretim hattını tetikler.
    Adım adım ilerler, her adımı loglar ve sonunda tüm çıktıları Cloud Storage'a yükler.
    """
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    logging.info(f"🚀 Yeni üretim süreci başlatıldı. Geçici klasör: {temp_dir}")
    
    story_title = "" # Hata durumunda hangi başlığın hata verdiğini bilmek için
    
    try:
        # ==============================================================================
        # ADIM 1 & 2: HİKAYE ÜRETİMİ
        # ==============================================================================
        logging.info("[ADIM 1/9] Konu seçiliyor ve hikaye oluşturuluyor...")
        (
            story_content,
            story_title_from_module,
            protagonist_profile,
            api_keys,
            formatted_text
        ) = hikayeuretir.run_story_generation_process(KAYNAK_BUCKET_ADI, CIKTI_BUCKET_ADI)

        story_title = story_title_from_module

        if not story_title:
            logging.warning("İşlenecek yeni konu bulunamadı. Üretim bandı durduruldu.")
            return jsonify({"status": "finished", "message": "No new topics to process."}), 200

        logging.info(f"✅ Hikaye başarıyla oluşturuldu. Başlık: '{story_title}'")
        
        formatted_story_path = os.path.join(temp_dir, "hikaye_formatli.txt")
        with open(formatted_story_path, "w", encoding="utf-8") as f:
            f.write(formatted_text)
        logging.info(f"💾 Formatlanmış hikaye geçici olarak kaydedildi: {formatted_story_path}")

        # ==============================================================================
        # ADIM 3 & 4: SESLENDİRME VE ALTYAZI
        # ==============================================================================
        logging.info("[ADIM 3-4/9] Seslendirme ve senkronize altyazı üretimi başlıyor...")
        audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(
            story_text=formatted_text,
            output_dir=temp_dir,
            api_keys_list=api_keys
        )
        if not audio_file_path or not srt_file_path:
            raise Exception("Ses veya altyazı dosyası oluşturulamadı.")
        logging.info("✅ Ses ve altyazı başarıyla oluşturuldu.")

        # ==============================================================================
        # ADIM 5: PROFİL FOTOĞRAFI ÜRETİMİ
        # ==============================================================================
        logging.info("[ADIM 5/9] Profil fotoğrafı üretimi başlıyor...")
        original_photo_path, thumbnail_photo_path = profilfotoolusturur.run_profile_photo_generation(
            protagonist_profile=protagonist_profile,
            output_dir=temp_dir
        )
        if not original_photo_path or not thumbnail_photo_path:
            raise Exception("Profil fotoğrafı veya küçük resim için fotoğraf üretilemedi.")
        logging.info("✅ Profil fotoğrafı ve küçük resim versiyonu başarıyla üretildi.")

        # ==============================================================================
        # ADIM 6: ARKA PLAN TEMİZLEME
        # ==============================================================================
        logging.info("[ADIM 6/9] Profil fotoğrafının arka planı temizleniyor...")
        cleaned_photo_path = profilfotonunarkasinisiler.run_background_removal(
            input_path=original_photo_path,
            output_dir=temp_dir
        )
        if not cleaned_photo_path:
            raise Exception("Profil fotoğrafının arka planı temizlenemedi.")
        logging.info("✅ Arka plan başarıyla temizlendi.")

        # ==============================================================================
        # ADIM 7: VİDEO BİRLEŞTİRME
        # ==============================================================================
        logging.info("[ADIM 7/9] Video birleştirme işlemi başlıyor...")
        
        storage_client = storage.Client()
        kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
        bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
        bg_video_path = os.path.join(temp_dir, "arkaplan.mp4")
        bg_video_blob.download_to_filename(bg_video_path)
        logging.info("✅ Arka plan videosu indirildi.")

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
        # ADIM 8: YOUTUBE KÜÇÜK RESMİ OLUŞTURMA
        # ==============================================================================
        logging.info("[ADIM 8/9] YouTube küçük resmi oluşturuluyor...")
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
        # ADIM 9: PAKETLEME VE TESLİMAT (CLOUD STORAGE'A YÜKLEME)
        # ==============================================================================
        logging.info("[ADIM 9/9] Üretilen dosyalar Cloud Storage'a yükleniyor...")
        cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
        safe_folder_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in story_title)

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
            else:
                logging.warning(f"  -> ATLANDI: {local_path} bulunamadı.")
        
        logging.info("✅ Tüm dosyalar başarıyla Cloud Storage'a yüklendi.")

        # BAŞARILI SONUÇ
        logging.info("🎉🎉🎉 ÜRETİM BANDI BAŞARIYLA TAMAMLANDI! 🎉🎉�")
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
