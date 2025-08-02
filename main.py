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
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    logging.info(f"🚀 Yeni üretim süreci başlatıldı. Geçici klasör: {temp_dir}")
    
    story_title = "" # Hata durumunda hangi başlığın hata verdiğini bilmek için
    
    try:
        # ADIM 1 & 2: HİKAYE ÜRETİMİ
        logging.info("[ADIM 1/9] Konu seçiliyor ve hikaye oluşturuluyor...")
        (
            story_content,
            story_title_from_module, # Değişken adını değiştirdik
            protagonist_profile,
            api_keys,
            formatted_text
        ) = hikayeuretir.run_story_generation_process(KAYNAK_BUCKET_ADI, CIKTI_BUCKET_ADI)

        story_title = story_title_from_module # Başlığı ana değişkene ata

        if not story_title:
            logging.warning("İşlenecek yeni konu bulunamadı. Üretim bandı durduruldu.")
            # YEREL SCRIPTE BİTTİ MESAJI GÖNDER
            return jsonify({"status": "finished", "message": "No new topics to process."}), 200

        logging.info(f"✅ Hikaye başarıyla oluşturuldu. Başlık: '{story_title}'")
        
        # ... DİĞER TÜM ADIMLARINIZ BURADA OLACAK (HİÇBİR DEĞİŞİKLİK YOK) ...
        # Adım 3'ten Adım 9'a kadar olan tüm kodunuzu buraya kopyalayın.
        # Bu adımların tam ve doğru çalıştığını varsayıyoruz.
        # Örnek olarak birkaç adımı ekleyelim:
        
        formatted_story_path = os.path.join(temp_dir, "hikaye_formatli.txt")
        with open(formatted_story_path, "w", encoding="utf-8") as f: f.write(formatted_text)
        
        logging.info("[ADIM 3-4/9] Seslendirme ve altyazı üretimi başlıyor...")
        audio_file_path, srt_file_path = googleilesesolustur.run_audio_and_srt_process(
            story_text=formatted_text, output_dir=temp_dir, api_keys_list=api_keys
        )
        # ... (diğer tüm adımlar) ...
        
        logging.info("✅ Tüm adımlar tamamlandı.")

        # BAŞARILI SONUÇ
        logging.info("🎉🎉🎉 ÜRETİM BANDI BAŞARIYLA TAMAMLANDI! 🎉🎉🎉")
        # YEREL SCRIPTE BAŞARI MESAJI VE İŞLENEN BAŞLIĞI GÖNDER
        return jsonify({
            "status": "success",
            "message": f"Video for '{story_title}' was successfully generated.",
            "processed_title": story_title
        }), 200

    except Exception as e:
        error_message = f"Üretim bandında '{story_title}' işlenirken hata oluştu: {e}"
        logging.error(error_message, exc_info=True)
        # YEREL SCRIPTE HATA MESAJI VE BAŞARISIZ OLAN BAŞLIĞI GÖNDER
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
```

Bu kodu Cloud Run servisinize dağıtın.

---
### 2. Adım: Yerel Bilgisayarınız İçin Kontrol Script'ini Yazmak

Şimdi yerel bilgisayarınızda çalışacak ve fabrikayı yönetecek olan Python script'ini oluşturalım.

1.  Bilgisayarınızda `requests` kütüphanesinin kurulu olduğundan emin olun. Değilse, terminalde `pip install requests` komutunu çalıştırın.
2.  Aşağıdaki kodu `local_controller.py` adıyla bir dosyaya kaydedin.


```python
import requests
import subprocess
import json
import time
import sys

# --- AYARLAR ---
# Cloud Run servisinizin tam URL'sini buraya yapıştırın
CLOUD_RUN_URL = "https://video-fabrikasi-servisi-281592548008.europe-west1.run.app" 
# Başarısız olan başlıkların kaydedileceği dosya
FAILED_TITLES_FILE = "tamamlanamayanbasliklar.txt"

def get_identity_token():
    """gcloud CLI kullanarak kimlik token'ı alır."""
    try:
        # gcloud komutunu çalıştır ve çıktısını yakala
        token = subprocess.check_output(
            ["gcloud", "auth", "print-identity-token"],
            text=True
        ).strip()
        return token
    except FileNotFoundError:
        print("HATA: 'gcloud' komutu bulunamadı. Google Cloud SDK'nın kurulu olduğundan emin olun.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"HATA: gcloud token alınamadı. Hata: {e}")
        sys.exit(1)

def run_factory_once():
    """Cloud Run servisini bir kez tetikler ve sonucunu döndürür."""
    print("🔄 Fabrika tetikleniyor...")
    
    token = get_identity_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Not: Cloud Run'ın yanıt vermesi uzun sürebilir. Timeout değerini yüksek tutuyoruz.
        # Ancak bu süre en fazla 60 dakika olabilir.
        response = requests.post(CLOUD_RUN_URL, headers=headers, json={}, timeout=3660)
        
        # Yanıtı kontrol et
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 500:
            print("⚠️ Sunucuda bir hata oluştu (500).")
            return response.json()
        else:
            print(f"❌ Beklenmedik bir durum kodu alındı: {response.status_code}")
            print(f"Sunucu yanıtı: {response.text}")
            return {"status": "unknown_error"}
            
    except requests.exceptions.Timeout:
        print("❌ HATA: İstek zaman aşımına uğradı! (60 dakikadan uzun sürdü).")
        return {"status": "timeout"}
    except requests.exceptions.RequestException as e:
        print(f"❌ HATA: Ağ bağlantı hatası: {e}")
        return {"status": "network_error"}

def main():
    """Ana döngü. Fabrikayı tüm başlıklar bitene kadar çalıştırır."""
    processed_count = 0
    failed_count = 0
    
    while True:
        result = run_factory_once()
        
        status = result.get("status")
        
        if status == "success":
            processed_count += 1
            title = result.get('processed_title', 'Bilinmeyen Başlık')
            print(f"✅ BAŞARILI: '{title}' başlıklı video üretildi. (Toplam: {processed_count})")
            
        elif status == "finished":
            print("\n🎉 TÜM BAŞLIKLAR BİTTİ! Fabrika durduruluyor.")
            break
            
        elif status == "error":
            failed_count += 1
            title = result.get('failed_title', 'Bilinmeyen Başlık')
            print(f"❌ HATA: '{title}' başlıklı video üretilemedi.")
            with open(FAILED_TITLES_FILE, "a", encoding="utf-8") as f:
                f.write(title + "\n")
            print(f"-> Başarısız başlık '{FAILED_TITLES_FILE}' dosyasına kaydedildi.")
            
        elif status == "timeout":
            # Zaman aşımı durumunda hangi başlığın işlendiğini bilemeyiz.
            # Bu yüzden döngüyü kırmak en güvenlisi.
            print("-> Zaman aşımı nedeniyle işlem durduruldu. Başarısız olan başlık manuel olarak bulunmalı.")
            failed_count += 1
            break
            
        else:
            # Diğer tüm hatalar için
            print("-> Bilinmeyen bir hata nedeniyle işlem durduruldu.")
            failed_count += 1
            break
            
        # Servise nefes alması için kısa bir ara verelim
        print("-" * 50)
        time.sleep(5)
        
    print("\n--- İŞLEM SONU RAPORU ---")
    print(f"Başarıyla tamamlanan video sayısı: {processed_count}")
    print(f"Başarısız olan video sayısı: {failed_count}")
    if failed_count > 0:
        print(f"Başarısız başlıkların listesi için '{FAILED_TITLES_FILE}' dosyasını kontrol edin.")

if __name__ == "__main__":
    main()