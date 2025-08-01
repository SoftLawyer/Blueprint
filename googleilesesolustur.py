# googleilesesolustur.py

import os
import requests
import json
import time
import wave
import base64
import whisper

# --- Sabitler ---
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 4500 
MAX_RETRIES = 3
SERVICE_RETRY_INTERVAL = 30  # Servis down olduğunda 30 saniye bekle

# --- Yardımcı Fonksiyonlar ---

def split_text(text, max_length=API_CHUNK_SIZE):
    """Metni, kelimeleri bölmemeye çalışarak API sınırlarına uygun parçalara böler."""
    chunks = []
    if not text or not text.strip():
        return chunks
    while len(text) > max_length:
        split_pos = text.rfind(' ', 0, max_length)
        if split_pos == -1: split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    chunks.append(text)
    return chunks

def get_error_reason(status_code, response_text):
    """HTTP hata koduna göre sebep açıklaması döner"""
    try:
        error_data = json.loads(response_text)
        error_message = error_data.get('error', {}).get('message', '')
        
        if 'quota' in error_message.lower() or 'limit' in error_message.lower():
            return f"KOTA AŞIMI: {error_message}"
        elif 'suspended' in error_message.lower():
            return f"API ANAHTARI ASKIYA ALINDI: {error_message}"
        elif 'permission' in error_message.lower():
            return f"YETKİ SORUNU: {error_message}"
        elif 'billing' in error_message.lower():
            return f"FATURA/ÖDEME SORUNU: {error_message}"
        else:
            return f"API HATASI: {error_message}"
    except:
        pass
    
    # HTTP status koduna göre genel açıklama
    error_reasons = {
        400: "KÖTÜ İSTEK: API parametreleri hatalı",
        401: "YETKİSİZ ERİŞİM: API anahtarı geçersiz",
        403: "YASAK ERİŞİM: Kota aşımı veya API anahtarı askıda",
        404: "BULUNAMADI: API endpoint hatalı",
        429: "ÇOK FAZLA İSTEK: Rate limit aşımı",
        500: "SUNUCU HATASI: Google'ın iç sunucu hatası",
        502: "BAD GATEWAY: Google servisi geçici olarak erişilemez",
        503: "SERVİS KULLANILAMAZ: Google servisi bakımda",
        504: "GATEWAY TIMEOUT: Google servisi yanıt vermiyor"
    }
    
    return error_reasons.get(status_code, f"BİLİNMEYEN HATA: HTTP {status_code}")

def test_api_key(api_key, key_number):
    """API anahtarını test eder."""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"🔍 TTS API anahtarı {key_number} test ediliyor... (Deneme {attempt + 1}/{MAX_RETRIES})")
            test_url = f"https://texttospeech.googleapis.com/v1/voices?key={api_key}"
            response = requests.get(test_url, timeout=15)
            
            if response.status_code == 200:
                try:
                    response.json()  # JSON parse kontrolü
                    print(f"✅ TTS API anahtarı {key_number} geçerli")
                    return True
                except json.JSONDecodeError:
                    print(f"⚠️ API anahtarı {key_number}: JSON parse hatası (Deneme {attempt + 1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2)
                        continue
            else:
                error_reason = get_error_reason(response.status_code, response.text)
                print(f"❌ TTS API anahtarı {key_number} geçersiz: {error_reason}")
                return False
        except Exception as e:
            print(f"⚠️ TTS API anahtarı {key_number} test edilirken hata (Deneme {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
    
    print(f"❌ TTS API anahtarı {key_number}: {MAX_RETRIES} deneme sonrası başarısız")
    return False

def make_tts_request_with_service_wait(chunk, api_key, chunk_number, total_chunks):
    """Tek bir chunk için TTS isteği yapar, servis down ise sürekli bekler"""
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    data = {
        "input": {"text": chunk},
        "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Enceladus"},
        "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": 0.95, "sampleRateHertz": SAMPLE_RATE}
    }
    
    attempt = 0
    while True:  # Sonsuz döngü - servis düzelene kadar bekle
        attempt += 1
        try:
            print(f"  ➡️ Parça {chunk_number}/{total_chunks} işleniyor... (Deneme {attempt})")
            
            response = requests.post(url, json=data, timeout=90, headers={'Content-Type': 'application/json'})
            
            if response.status_code == 200:
                try:
                    response_json = response.json()
                    if 'audioContent' in response_json:
                        audio_content = base64.b64decode(response_json['audioContent'])
                        print(f"  ✅ Parça {chunk_number} başarıyla işlendi")
                        return audio_content
                    else:
                        print(f"  ⚠️ Parça {chunk_number}: audioContent bulunamadı")
                except json.JSONDecodeError as e:
                    print(f"  ⚠️ Parça {chunk_number}: JSON parse hatası - {e}")
            else:
                error_reason = get_error_reason(response.status_code, response.text)
                
                # Eğer kalıcı hata ise (kota, yetki vs) döngüden çık
                if response.status_code in [401, 403] and ('quota' in error_reason.lower() or 'suspended' in error_reason.lower() or 'billing' in error_reason.lower()):
                    print(f"  ❌ Parça {chunk_number}: KALİCI HATA - {error_reason}")
                    return None
                
                # Geçici hata ise bekle ve devam et
                print(f"  🔄 Parça {chunk_number}: SERVİSTEN YANIT ALINAMIYOR - {error_reason}")
                print(f"  ⏳ {SERVICE_RETRY_INTERVAL} saniye sonra tekrar denenecek...")
                time.sleep(SERVICE_RETRY_INTERVAL)
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"  🔄 Parça {chunk_number}: SERVİSTEN YANIT ALINAMIYOR - Ağ hatası: {e}")
            print(f"  ⏳ {SERVICE_RETRY_INTERVAL} saniye sonra tekrar denenecek...")
            time.sleep(SERVICE_RETRY_INTERVAL)
            continue
        except Exception as e:
            print(f"  🔄 Parça {chunk_number}: SERVİSTEN YANIT ALINAMIYOR - Beklenmeyen hata: {e}")
            print(f"  ⏳ {SERVICE_RETRY_INTERVAL} saniye sonra tekrar denenecek...")
            time.sleep(SERVICE_RETRY_INTERVAL)
            continue

def text_to_speech_chirp3_only(text, api_keys):
    """Metni parçalara ayırır, Chirp3-HD-Enceladus sesi ile sese çevirir ve birleştirir."""
    print("🔍 TTS API anahtarları test ediliyor...")
    valid_keys = [(i, key) for i, key in enumerate(api_keys, 1) if test_api_key(key, i)]
    
    if not valid_keys:
        print("❌ HATA: Hiçbir geçerli TTS API anahtarı bulunamadı!")
        return None
    
    print(f"✅ {len(valid_keys)} geçerli API anahtarı bulundu")
    print("🎵 SADECE en-US-Chirp3-HD-Enceladus sesi kullanılacak!")

    text_chunks = split_text(text)
    print(f"ℹ️ Metin, API'ye gönderilmek üzere {len(text_chunks)} parçaya ayrıldı.")

    for key_number, api_key in valid_keys:
        print(f"\n🔄 API anahtarı {key_number} ile tüm metin deneniyor...")
        combined_audio_content = b''
        all_chunks_successful = True
        
        for i, chunk in enumerate(text_chunks, 1):
            audio_content = make_tts_request_with_service_wait(chunk, api_key, i, len(text_chunks))
            
            if audio_content is not None:
                combined_audio_content += audio_content
            else:
                print(f"  ❌ Parça {i} kalıcı hata nedeniyle işlenemedi, sonraki API anahtarına geçiliyor...")
                all_chunks_successful = False
                break
        
        if all_chunks_successful:
            print(f"✅ API anahtarı {key_number} ile tüm parçalar başarıyla sese çevrildi!")
            return combined_audio_content
        else:
            print(f"⏭️ Sonraki API anahtarı deneniyor...")
            continue
    
    print("\n❌ HATA: Tüm API anahtarları denendi ve ses oluşturulamadı!")
    return None

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses verisini .wav dosyası olarak geçici belleğe kaydeder."""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"💾 Ses dosyası kaydediliyor... (Deneme {attempt + 1}/{MAX_RETRIES})")
            full_path = os.path.join(output_dir, filename)
            with wave.open(full_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(audio_content)
            print(f"✅ Ses dosyası başarıyla geçici olarak kaydedildi: {full_path}")
            return full_path
        except Exception as e:
            print(f"⚠️ Ses dosyası kaydedilirken hata (Deneme {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
    
    print(f"❌ HATA: Ses dosyası {MAX_RETRIES} deneme sonrası kaydedilemedi")
    return None

def seconds_to_srt_time(seconds):
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"

def generate_synchronized_srt(audio_file_path, output_dir):
    """Whisper ile ses dosyasından tam senkronize SRT altyazısı oluşturur."""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"\n🤖 Whisper modeli yükleniyor... (Deneme {attempt + 1}/{MAX_RETRIES})")
            model = whisper.load_model("base") 
            print(f"🎤 '{os.path.basename(audio_file_path)}' dosyası deşifre ediliyor...")
            result = model.transcribe(audio_file_path, fp16=False, language="en") 

            srt_content = []
            for i, segment in enumerate(result['segments'], 1):
                start_time = seconds_to_srt_time(segment['start'])
                end_time = seconds_to_srt_time(segment['end'])
                text = segment['text'].strip()
                srt_content.extend([str(i), f"{start_time} --> {end_time}", text, ""])

            srt_file_path = os.path.join(output_dir, "altyazi.srt")
            with open(srt_file_path, 'w', encoding='utf-8') as srt_file:
                srt_file.write('\n'.join(srt_content))
            print(f"✅ Tam senkronize SRT altyazı dosyası başarıyla oluşturuldu: {srt_file_path}")
            return srt_file_path
        except Exception as e:
            print(f"⚠️ Whisper ile altyazı oluşturulurken hata (Deneme {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(3)
                continue
            else:
                import traceback
                traceback.print_exc()
    
    print(f"❌ HATA: Altyazı {MAX_RETRIES} deneme sonrası oluşturulamadı")
    return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_audio_and_srt_process(story_text, output_dir, api_keys_list):
    """Ana ses ve senkronize altyazı üretme iş akışını yönetir."""
    print("--- Ses ve Senkronize Altyazı Üretim Modülü Başlatıldı ---")
    
    audio_content = text_to_speech_chirp3_only(story_text, api_keys_list)
    if audio_content is None:
        raise Exception("Ses içeriği üretilemedi.")
    
    audio_file_path = save_audio(audio_content, output_dir)
    if not audio_file_path:
        raise Exception("Ses dosyası geçici olarak kaydedilemedi.")
        
    srt_file_path = generate_synchronized_srt(audio_file_path, output_dir)
    
    return audio_file_path, srt_file_path
