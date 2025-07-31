# googleilesesolustur.py

import os
import requests
import json
import time
import wave
import base64
import whisper

# --- Sabitler (Sizin orijinal kodunuzdan) ---
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 4500 

# --- Yardımcı Fonksiyonlar (Sizin orijinal kodunuzdan, buluta uyarlandı) ---

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

def test_api_key(api_key, key_number):
    """API anahtarını test eder."""
    try:
        print(f"🔍 TTS API anahtarı {key_number} test ediliyor...")
        test_url = f"https://texttospeech.googleapis.com/v1/voices?key={api_key}"
        response = requests.get(test_url, timeout=15)
        if response.status_code == 200:
            print(f"✅ TTS API anahtarı {key_number} geçerli")
            return True
        else:
            error_details = response.json().get('error', {}).get('message', 'Bilinmeyen Hata')
            print(f"❌ TTS API anahtarı {key_number} geçersiz (HTTP {response.status_code}): {error_details}")
            return False
    except Exception as e:
        print(f"❌ TTS API anahtarı {key_number} test edilirken hata: {e}")
        return False

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
        
        try:
            for i, chunk in enumerate(text_chunks, 1):
                print(f"  ➡️ Parça {i}/{len(text_chunks)} işleniyor...")
                url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
                data = {
                    "input": {"text": chunk},
                    "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Enceladus"},
                    "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": 0.95, "sampleRateHertz": SAMPLE_RATE}
                }
                
                response = requests.post(url, json=data, timeout=90, headers={'Content-Type': 'application/json'})
                
                if response.status_code == 200 and 'audioContent' in response.json():
                    combined_audio_content += base64.b64decode(response.json()['audioContent'])
                else:
                    error_msg = response.json().get('error', {}).get('message', f"HTTP {response.status_code}")
                    print(f"  ❌ Parça {i} işlenirken API Hatası: {error_msg}")
                    all_chunks_successful = False
                    break
            
            if all_chunks_successful:
                print(f"✅ API anahtarı {key_number} ile tüm parçalar başarıyla sese çevrildi!")
                return combined_audio_content
            else:
                print(f"⏭️ Sonraki API anahtarı deneniyor...")
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"❌ API anahtarı {key_number}: Ağ hatası - {e}")
            continue
    
    print("\n❌ HATA: Tüm API anahtarları denendi ve ses oluşturulamadı!")
    return None

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses verisini .wav dosyası olarak geçici belleğe kaydeder."""
    try:
        full_path = os.path.join(output_dir, filename)
        with wave.open(full_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_content)
        print(f"✅ Ses dosyası başarıyla geçici olarak kaydedildi: {full_path}")
        return full_path
    except Exception as e:
        print(f"❌ HATA: Ses dosyası kaydedilirken hata oluştu: {e}")
        return None

def seconds_to_srt_time(seconds):
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"

def generate_synchronized_srt(audio_file_path, output_dir):
    """Whisper ile ses dosyasından tam senkronize SRT altyazısı oluşturur."""
    try:
        print("\n🤖 Whisper modeli yükleniyor...")
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
        print(f"❌ HATA: Whisper ile altyazı oluşturulurken hata oluştu: {e}")
        import traceback
        traceback.print_exc()
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
