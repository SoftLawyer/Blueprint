# main.py

import os
import traceback
from flask import Flask
from google.cloud import storage
import re
import time

# Kendi modüllerimizi import ediyoruz
from hikayeuretir import run_story_generation_process
from googleilesesolustur import run_audio_and_srt_process
from profilfotoolusturur import run_profile_photo_generation
from profilfotonunarkasinisiler import run_background_removal
from videoyapar import run_video_creation
from kucukresimolusturur import run_thumbnail_generation

# --- AYARLAR ---
CIKTI_BUCKET_ADI = "video-fabrikam-ciktilar"
KAYNAK_BUCKET_ADI = "video-fabrikam-kaynaklar"

app = Flask(__name__)

@app.route("/", methods=["POST"])
def handle_request():
    """
    Bu ana fonksiyon, dışarıdan bir istek geldiğinde tetiklenir
    ve TÜM başlıklar bitene kadar video üretimini sırasıyla yönetir.
    """
    
    processed_videos_count = 0
    
    try:
        print("🏭 Fabrika tetiklendi, tam video üretim hattı başlıyor...")
        
        # --- TÜM BAŞLIKLARI İŞLEYEN ANA DÖNGÜ ---
        while True:
            print("\n" + "="*50)
            print(f"🔄 DÖNGÜ {processed_videos_count + 1} BAŞLIYOR...")
            print("="*50)

            # Her çalıştığında /tmp klasörünü temizleyerek başlayalım
            for item in os.listdir('/tmp'):
                item_path = os.path.join('/tmp', item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                except Exception as e:
                    print(f"/tmp temizlenirken hata: {e}")
            
            # Adım 1: Hikayeyi Üret. Bu fonksiyon artık 5 değer döndürecek.
            story_text, story_title, protagonist_profile, api_keys, formatted_story_text = run_story_generation_process(KAYNAK_BUCKET_ADI)
            
            # Eğer işlenecek başlık kalmadıysa, döngüyü sonlandır.
            if not story_text:
                print("✅ İşlenecek başka başlık bulunamadı. Üretim hattı durduruluyor.")
                break

            # Her video için GCS'de benzersiz bir klasör adı oluştur
            safe_folder_name = re.sub(r'[^a-zA-Z0-9_]', '', story_title.replace(' ', '_'))[:50]
            print(f"🗂️ Bu video için GCS klasörü: {safe_folder_name}")

            # Adım 1.5: Üretilen formatlı hikaye metnini geçici dosyaya yaz
            hikaye_path = "/tmp/hikaye.txt"
            with open(hikaye_path, "w", encoding="utf-8") as f:
                f.write(formatted_story_text)
            print(f"  -> Hikaye metni geçici olarak '{hikaye_path}' dosyasına yazıldı.")

            # Adım 2: Sesi ve Altyazıyı Oluştur
            audio_path, srt_path = run_audio_and_srt_process(story_text, "/tmp", api_keys)

            # Adım 3: Profil Fotoğrafını ve Küçük Resim için Fotoğrafı Oluştur
            profile_photo_path, thumbnail_photo_path = run_profile_photo_generation(protagonist_profile, "/tmp")

            # Adım 4: Profil Fotoğrafının Arka Planını Sil
            final_profile_photo_path = run_background_removal(profile_photo_path, "/tmp")

            # Adım 5: Videoyu Yap
            storage_client = storage.Client()
            kaynak_bucket = storage_client.bucket(KAYNAK_BUCKET_ADI)
            bg_video_blob = kaynak_bucket.blob("arkaplan.mp4")
            bg_video_path = "/tmp/arkaplan.mp4"
            bg_video_blob.download_to_filename(bg_video_path)
            
            # HATA ÖNLEME: İndirilen dosyanın geçerli olup olmadığını kontrol et
            if not os.path.exists(bg_video_path) or os.path.getsize(bg_video_path) < 1024: # 1KB'dan küçükse bozuktur
                raise Exception(f"arkaplan.mp4 dosyası GCS'den indirilemedi veya bozuk.")
            print("  -> arkaplan.mp4 başarıyla indirildi ve doğrulandı.")
            
            final_video_path = run_video_creation(bg_video_path, audio_path, srt_path, final_profile_photo_path, protagonist_profile, "/tmp")

            # Adım 6: YouTube Küçük Resmini Oluştur
            thumbnail_path = run_thumbnail_generation(story_text, thumbnail_photo_path, "/tmp", api_keys)

            # Adım 7: Tüm Çıktıları GCS'deki Klasöre Yükle
            print("☁️ Tüm üretilen bileşenler GCS'ye yükleniyor...")
            cikti_bucket = storage_client.bucket(CIKTI_BUCKET_ADI)
            
            files_to_upload = {
                f"{safe_folder_name}/video.mp4": final_video_path,
                f"{safe_folder_name}/ses.wav": audio_path,
                f"{safe_folder_name}/altyazi.srt": srt_path,
                f"{safe_folder_name}/kucuk_resim.png": thumbnail_path,
                f"{safe_folder_name}/profil_foto.png": final_profile_photo_path,
                f"{safe_folder_name}/hikaye.txt": hikaye_path,
            }

            for gcs_path, local_path in files_to_upload.items():
                if local_path and os.path.exists(local_path):
                    blob = cikti_bucket.blob(gcs_path)
                    blob.upload_from_filename(local_path)
                    print(f"  -> Yüklendi: {gcs_path}")

            processed_videos_count += 1
            print(f"✅ Döngü {processed_videos_count} başarıyla tamamlandı.")
            
            # API'ları yormamak için döngüler arasında kısa bir mola verelim.
            time.sleep(10) 

        # Döngü bittiğinde
        print(f"\n🎉 Tam video üretim hattı başarıyla tamamlandı! Toplam {processed_videos_count} video üretildi.")
        return f"Başarıyla tamamlandı: Toplam {processed_videos_count} video üretildi.", 200
        
    except Exception as e:
        print(f"❌❌❌ ANA İŞ AKIŞINDA KRİTİK HATA ❌❌❌")
        print(f"Hata {processed_videos_count + 1}. videoda meydana geldi.")
        print(traceback.format_exc())
        return "Sunucuda kritik bir hata oluştu.", 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
