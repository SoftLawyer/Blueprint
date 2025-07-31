# googleilesesolustur.py

import os
import requests
import json
import wave
import base64
import whisper
import time

# --- Sabitler ---
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 4500 

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

def make_api_request_with_retry(url, data, headers, chunk_num, max_retries=3, timeout=180):
    """API isteğini tekrar deneme mekanizması ile yapar."""
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, timeout=timeout, headers=headers)
            
            # ZIRHLI GÜNCELLEME: Cevabın JSON olup olmadığını kontrol et
            try:
                result = response.json()
            except json.JSONDecodeError:
                print(f"  ❌ Parça {chunk_num} işlenirken JSON parse hatası (Deneme {attempt + 1}/{max_retries}). Sunucu cevabı:")
                # Cevabın ilk 200 karakterini göstererek hatanın ne olduğunu anla
                print(f"     -> HTTP {response.status_code}, Cevap: {response.text[:200]}") 
                sleep_time = (2 ** attempt)
                print(f"     -> {sleep_time} saniye sonra tekrar denenecek...")
                time.sleep(sleep_time)
                continue

            # JSON parse edildiyse normal akışa devam et
            if response.status_code == 200:
                if 'audioContent' in result:
                    print(f"  ✅ Parça {chunk_num} başarıyla sese çevrildi.")
                    return base64.b64decode(result['audioContent'])
                else:
                    print(f"  ❌ Parça {chunk_num} için yanıtta ses verisi bulunamadı.")
                    return None
            
            error_msg = result.get('error', {}).get('message', f"HTTP {response.status_code}")
            print(f"  ❌ Parça {chunk_num} işlenirken API Hatası (Deneme {attempt + 1}/{max_retries}): {error_msg}")

            if response.status_code in [500, 503, 429]:
                sleep_time = (2 ** attempt)
                print(f"     -> Sunucu hatası, {sleep_time} saniye sonra tekrar denenecek...")
                time.sleep(sleep_time)
                continue
            else:
                return None

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Parça {chunk_num} işlenirken Ağ Hatası (Deneme {attempt + 1}/{max_retries}): {e}")
            sleep_time = (2 ** attempt)
            print(f"     -> {sleep_time} saniye sonra tekrar denenecek...")
            time.sleep(sleep_time)

    print(f"  ❌ Parça {chunk_num} tüm denemelere rağmen başarısız oldu.")
    return None

def text_to_speech_chirp3_only(text, api_keys):
    """Metni parçalara ayırır, Chirp3-HD-Enceladus sesi ile sese çevirir ve birleştirir."""
    if not api_keys:
        print("❌ HATA: Ses üretimi için API anahtarı bulunamadı!")
        return None
    
    print("🎵 SADECE en-US-Chirp3-HD-Enceladus sesi kullanılacak!")
    text_chunks = split_text(text)
    if not text_chunks:
        print("⚠️ Seslendirilecek metin boş, işlem atlanıyor.")
        return b''

    print(f"ℹ️ Metin, API'ye gönderilmek üzere {len(text_chunks)} parçaya ayrıldı.")

    for key_index, api_key in enumerate(api_keys):
        print(f"\n🔄 API anahtarı {key_index + 1}/{len(api_keys)} ile tüm metin deneniyor...")
        combined_audio_content = b''
        all_chunks_successful = True
        
        for i, chunk in enumerate(text_chunks, 1):
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
            data = {
                "input": {"text": chunk},
                "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Enceladus"},
                "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": 0.95, "sampleRateHertz": SAMPLE_RATE}
            }
            
            audio_chunk = make_api_request_with_retry(url, data, {'Content-Type': 'application/json'}, i)
            
            if audio_chunk:
                combined_audio_content += audio_chunk
            else:
                all_chunks_successful = False
                break
        
        if all_chunks_successful:
            print(f"✅ API anahtarı {key_index + 1} ile tüm parçalar başarıyla sese çevrildi!")
            return combined_audio_content
        else:
            print(f"⏭️ Bu anahtar başarısız oldu, sonraki API anahtarı denenecek...")
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
        result = model.transcribe(audio_file_path, fp16=False) 

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
