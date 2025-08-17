# googleilesesolustur.py (v14 - Hata Toleransı ve Tekrar Deneme)

import os
import requests
import json
import time
import wave
import base64
import whisper
import re
import struct # Fade-out efekti için eklendi
import logging

from google.cloud import secretmanager
from google.api_core import exceptions

# --- TEMEL AYARLAR ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- SABİTLER ---
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 3500
MAX_SENTENCE_BYTES = 700
MAX_RECURSION_DEPTH = 3
# YENİ: Tekrar deneme ayarları
MAX_RETRIES = 4
INITIAL_BACKOFF_SECONDS = 2

# SECRET MANAGER AYARLARI
PROJECT_ID = "sizin-google-cloud-proje-id-niz" 
SECRET_ID = "gemini-api-anahtarlari"


def get_api_keys_from_secret_manager():
    """
    Google Cloud Secret Manager'dan API anahtarlarını güvenli bir şekilde alır.
    """
    logging.info(f"🤫 Secret Manager'dan '{SECRET_ID}' secret'ı alınıyor...")
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        api_keys = json.loads(payload)

        if not isinstance(api_keys, list) or not api_keys:
            logging.error("Secret içeriği geçerli bir liste değil veya boş.")
            raise ValueError("Secret'tan alınan veri formatı hatalı.")

        logging.info(f"✅ Başarıyla {len(api_keys)} adet API anahtarı Secret Manager'dan alındı.")
        return api_keys
    except Exception as e:
        logging.critical(f"❌ Secret Manager'dan anahtar alınırken kritik hata: {e}")
        raise

def apply_fade_out(audio_data, fade_duration_ms=500):
    """
    Ses verisinin sonuna yumuşak bir bitiş (linear fade-out) uygular.
    """
    try:
        logging.info(f"🌬️ Sona doğal bir bitiş için {fade_duration_ms}ms'lik 'fade-out' efekti uygulanıyor...")
        sample_width = 2
        fade_samples = int(SAMPLE_RATE * (fade_duration_ms / 1000.0))
        total_samples = len(audio_data) // sample_width
        fade_samples = min(fade_samples, total_samples)

        if fade_samples == 0:
            logging.warning("Fade-out uygulanamayacak kadar kısa ses, atlanıyor.")
            return audio_data

        main_part = audio_data[:-fade_samples * sample_width]
        fade_part = audio_data[-fade_samples * sample_width:]
        faded_audio = bytearray()
        
        for i in range(fade_samples):
            multiplier = 1.0 - (i / fade_samples)
            sample_bytes = fade_part[i * sample_width : (i + 1) * sample_width]
            original_sample = struct.unpack('<h', sample_bytes)[0]
            faded_sample = int(original_sample * multiplier)
            faded_audio.extend(struct.pack('<h', faded_sample))
            
        return main_part + faded_audio
    except Exception as e:
        logging.error(f"⚠️ Fade-out uygulanamadı: {e}. Ses orjinal haliyle bırakılıyor.")
        return audio_data

def extract_target_sections(text):
    """Metinden sadece seslendirilecek olan 'STORY:' ve 'VIEWER ENGAGEMENT:' bölümlerini çıkarır."""
    try:
        logging.info("🔍 STORY: ve VIEWER ENGAGEMENT: bölümleri aranıyor...")
        story_pattern = r'STORY:\s*(.*?)(?=\n\s*[-=]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)'
        engagement_pattern = r'VIEWER ENGAGEMENT:\s*(.*?)(?=\n\s*[-=]{5,}|\Z)'
        story_match = re.search(story_pattern, text, re.DOTALL | re.IGNORECASE)
        engagement_match = re.search(engagement_pattern, text, re.DOTALL | re.IGNORECASE)
        extracted_parts = []

        if story_match and story_match.group(1).strip():
            content = story_match.group(1).strip()
            extracted_parts.append(content)
            logging.info(f"✅ STORY bölümü bulundu ({len(content)} karakter).")
        else:
            logging.warning("STORY bölümü bulunamadı veya boş.")

        if engagement_match and engagement_match.group(1).strip():
            content = engagement_match.group(1).strip()
            extracted_parts.append(content)
            logging.info(f"✅ VIEWER ENGAGEMENT bölümü bulundu ({len(content)} karakter).")
        else:
            logging.warning("VIEWER ENGAGEMENT bölümü bulunamadı veya boş.")

        if not extracted_parts:
            logging.error("❌ Hiçbir hedef bölüm bulunamadı! Fallback olarak tüm metin kullanılacak.")
            return text.strip()
        
        final_text = "\n\n".join(extracted_parts)
        logging.info(f"✅ Toplam {len(extracted_parts)} bölüm birleştirildi ({len(final_text)} karakter).")
        return final_text
    except Exception as e:
        logging.error(f"❌ Bölüm çıkarma hatası: {e}. Fallback olarak tüm metin kullanılacak.")
        return text.strip()

def fix_long_sentences(text):
    """API limitini aşabilecek çok uzun cümleleri, anlamı bozmayacak şekilde noktalama işaretlerinden böler."""
    logging.info("🔧 Uzun cümleler kontrol ediliyor ve düzeltiliyor...")
    sentences = re.split(r'(?<=[.!?])\s+', text)
    fixed_sentences = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        if len(sentence.encode('utf-8')) <= MAX_SENTENCE_BYTES:
            fixed_sentences.append(sentence)
        else:
            logging.warning(f"Uzun cümle bulundu ({len(sentence.encode('utf-8'))} byte), bölünüyor...")
            parts = re.split(r'(,\s*(?:and|but|or|so|yet|for|nor|however|therefore|moreover|which|that|who)\s+|;\s+|:\s+)', sentence)
            new_sentence_parts = []
            current_part = ""
            for part in parts:
                if len((current_part + part).encode('utf-8')) > MAX_SENTENCE_BYTES and current_part:
                    new_sentence_parts.append(current_part.strip())
                    current_part = part
                else:
                    current_part += part
            if current_part:
                new_sentence_parts.append(current_part.strip())
            fixed_sentences.extend(new_sentence_parts)
    
    result = ' '.join(fixed_sentences)
    logging.info("✅ Uzun cümle düzeltme işlemi tamamlandı.")
    return result

def smart_text_splitter(text, max_length=API_CHUNK_SIZE):
    """Metni, cümle ve paragraf sonlarını dikkate alarak API limitlerine uygun parçalara böler."""
    logging.info("🧠 Metin, API için akıllı parçalara ayrılıyor...")
    text = fix_long_sentences(text)
    chunks = []
    remaining_text = text
    
    while len(remaining_text.encode('utf-8')) > max_length:
        split_pos = -1
        possible_split = remaining_text.rfind('.', 0, max_length)
        if possible_split != -1: split_pos = possible_split + 1
        possible_split = remaining_text.rfind('\n', 0, max_length)
        if possible_split > split_pos: split_pos = possible_split + 1
        if split_pos == -1:
            possible_split = remaining_text.rfind(' ', 0, max_length)
            if possible_split != -1: split_pos = possible_split + 1
        if split_pos == -1: split_pos = max_length
        chunk = remaining_text[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        remaining_text = remaining_text[split_pos:].strip()
    
    if remaining_text:
        chunks.append(remaining_text)
    
    logging.info(f"✅ Metin {len(chunks)} parçaya güvenli şekilde bölündü.")
    return chunks

def test_api_key(api_key, key_number):
    """Verilen Google Cloud API anahtarının geçerli olup olmadığını test eder."""
    try:
        logging.info(f"🔍 API anahtarı #{key_number} test ediliyor...")
        if not api_key or len(api_key) < 30:
            logging.error(f"❌ API anahtarı #{key_number} geçersiz formatta (çok kısa).")
            return False
        
        test_url = f"https://texttospeech.googleapis.com/v1/voices?key={api_key}"
        response = requests.get(test_url, timeout=10)
        
        if response.status_code == 200:
            logging.info(f"✅ API anahtarı #{key_number} geçerli.")
            return True
        else:
            logging.error(f"❌ API anahtarı #{key_number} geçersiz. Durum Kodu: {response.status_code}, Mesaj: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ API anahtarı #{key_number} test edilirken ağ hatası: {e}")
        return False

# --- GÜNCELLENMİŞ FONKSİYON ---
def process_single_chunk(chunk, api_key, chunk_id, recursion_depth=0):
    """
    Tek bir metin parçasını seslendirir.
    Geçici sunucu hatalarında (5xx) bekleyerek tekrar dener (exponential backoff).
    """
    if recursion_depth > MAX_RECURSION_DEPTH:
        logging.error(f"❌ Parça {chunk_id}: Maksimum bölme derinliği aşıldı! Atlanıyor...")
        return None
    
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    data = {
        "input": {"text": chunk},
        "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Iapetus"},
        "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": 1.0, "sampleRateHertz": SAMPLE_RATE}
    }
    
    backoff_time = INITIAL_BACKOFF_SECONDS
    for attempt in range(MAX_RETRIES):
        try:
            logging.info(f"➡️ Parça {chunk_id} işleniyor ({len(chunk.encode('utf-8'))} byte), deneme #{attempt + 1}...")
            response = requests.post(url, json=data, timeout=60)
            
            # --- BAŞARILI DURUM ---
            if response.status_code == 200:
                result = response.json()
                if 'audioContent' in result:
                    audio_data = base64.b64decode(result['audioContent'])
                    logging.info(f"✅ Parça {chunk_id} başarıyla seslendirildi.")
                    return audio_data
                else:
                    logging.error(f"❌ Parça {chunk_id}: API yanıtında 'audioContent' bulunamadı.")
                    return None # Başarılı ama içerik yok, tekrar deneme.

            # --- GEÇİCİ SUNUCU HATASI (5xx) ---
            elif response.status_code >= 500:
                logging.warning(f"⚠️ Parça {chunk_id} için geçici sunucu hatası alındı (Kod: {response.status_code}). {backoff_time} saniye sonra tekrar denenecek.")
                time.sleep(backoff_time)
                backoff_time *= 2 # Bir sonraki bekleme süresini ikiye katla
                continue # Döngünün bir sonraki adımına geç

            # --- KALICI İSTEMCİ HATASI (4xx) veya DİĞER HATALAR ---
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_msg = response.json().get('error', {}).get('message', error_msg)
                except json.JSONDecodeError:
                    error_msg = response.text
                logging.error(f"❌ Parça {chunk_id} için kalıcı API hatası: {error_msg}")
                
                # Metin çok uzunsa ve daha bölünebiliyorsa, tekrar bölmeyi dene
                if "too long" in error_msg.lower() or "exceeds the limit" in error_msg.lower():
                    logging.warning(f"🔪 Parça {chunk_id} çok uzun geldi, daha küçük parçalara bölünüyor...")
                    smaller_chunks = smart_text_splitter(chunk, max_length=API_CHUNK_SIZE // 2)
                    combined_audio = b''
                    for i, small_chunk in enumerate(smaller_chunks):
                        small_audio = process_single_chunk(small_chunk, api_key, f"{chunk_id}.{i+1}", recursion_depth + 1)
                        if small_audio: combined_audio += small_audio
                        else: return None
                    return combined_audio
                
                return None # Kalıcı hata, tekrar deneme.

        except requests.exceptions.RequestException as e:
            logging.warning(f"⚠️ Parça {chunk_id} işlenirken ağ hatası: {e}. {backoff_time} saniye sonra tekrar denenecek.")
            time.sleep(backoff_time)
            backoff_time *= 2
    
    logging.critical(f"❌ Parça {chunk_id}, {MAX_RETRIES} denemeden sonra hala işlenemedi.")
    return None


def text_to_speech_process(text, api_keys):
    """Metni seslendirmek için tüm süreci yönetir, geçerli API anahtarlarını dener."""
    logging.info("Geçerli API anahtarları bulunuyor...")
    valid_keys = [(i, key) for i, key in enumerate(api_keys, 1) if test_api_key(key, i)]
    
    if not valid_keys:
        logging.critical("❌ Hiçbir geçerli API anahtarı bulunamadı! İşlem durduruluyor.")
        return None
    
    logging.info(f"✅ {len(valid_keys)} adet geçerli API anahtarı bulundu.")
    text_chunks = smart_text_splitter(text)

    for key_number, api_key in valid_keys:
        logging.info(f"\n🔄 API anahtarı #{key_number} ile seslendirme deneniyor...")
        combined_audio_content = b''
        successful_chunks = 0
        
        for i, chunk in enumerate(text_chunks, 1):
            audio_data = process_single_chunk(chunk, api_key, str(i))
            if audio_data:
                combined_audio_content += audio_data
                successful_chunks += 1
                if i < len(text_chunks):
                    silence = b'\x00\x00' * int(SAMPLE_RATE * 0.2)
                    combined_audio_content += silence
            else:
                logging.error(f"Parça {i} bu API anahtarı ile başarısız oldu. Sonraki anahtar denenecek.")
                break
        
        if successful_chunks == len(text_chunks):
            logging.info(f"🎉 Tüm parçalar API anahtarı #{key_number} ile başarıyla işlendi!")
            final_audio = apply_fade_out(combined_audio_content)
            logging.info("➕ Sesin sonuna 10 saniye sessizlik ekleniyor...")
            silence_bytes = b'\x00\x00' * (SAMPLE_RATE * 10)
            final_audio += silence_bytes
            return final_audio

    logging.critical("❌ Tüm API anahtarları denendi ancak seslendirme tamamlanamadı.")
    return None

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses verisini belirtilen yola .wav dosyası olarak kaydeder."""
    if not audio_content:
        logging.error("❌ Kaydedilecek ses verisi yok!")
        return None
    try:
        full_path = os.path.join(output_dir, filename)
        with wave.open(full_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_content)
        logging.info(f"✅ Ses dosyası kaydedildi: {full_path} ({os.path.getsize(full_path):,} byte)")
        return full_path
    except Exception as e:
        logging.error(f"❌ Ses dosyası kaydedilirken hata: {e}")
        return None

def seconds_to_srt_time(seconds):
    """Saniye değerini SRT altyazı formatına (HH:MM:SS,mmm) çevirir."""
    millis = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

def generate_synchronized_srt(audio_file_path, output_dir):
    """Oluşturulan ses dosyasını OpenAI Whisper ile deşifre ederek senkronize SRT altyazısı oluşturur."""
    try:
        logging.info(f"\n🤖 Whisper modeli yükleniyor (base)...")
        model = whisper.load_model("base")
        logging.info(f"🎤 Ses dosyası deşifre ediliyor: {audio_file_path}")
        result = model.transcribe(audio_file_path, fp16=False, language="en")
        srt_content = [f"{i}\n{seconds_to_srt_time(s['start'])} --> {seconds_to_srt_time(s['end'])}\n{s['text'].strip()}\n" for i, s in enumerate(result['segments'], 1)]
        srt_file_path = os.path.join(output_dir, "altyazi.srt")
        with open(srt_file_path, 'w', encoding='utf-8') as srt_file:
            srt_file.write('\n'.join(srt_content))
        logging.info(f"✅ Senkronize SRT altyazı dosyası oluşturuldu: {srt_file_path}")
        return srt_file_path
    except Exception as e:
        logging.critical(f"❌ Whisper ile altyazı oluşturma hatası: {e}")
        return None

def run_audio_and_srt_process(story_text, output_dir, api_keys_list=None):
    """
    Ana ses ve altyazı üretme iş akışını yönetir.
    API anahtarları sağlanmazsa Secret Manager'dan almayı dener.
    """
    logging.info("--- Ses ve Senkronize Altyazı Üretim Modülü Başlatıldı ---")
    
    keys_to_use = []
    if api_keys_list:
        logging.info("API anahtarları parametre olarak sağlandı, onlar kullanılacak.")
        keys_to_use = api_keys_list
    else:
        logging.warning("API anahtarları parametre olarak sağlanmadı. Secret Manager'dan alınacak...")
        try:
            if PROJECT_ID == "sizin-google-cloud-proje-id-niz":
                raise ValueError("Lütfen koddaki PROJECT_ID değişkenini kendi Google Cloud Proje ID'niz ile güncelleyin.")
            keys_to_use = get_api_keys_from_secret_manager()
        except Exception as e:
            raise Exception(f"Secret Manager'dan API anahtarları alınamadı: {e}")

    if not keys_to_use:
         raise Exception("Kullanılacak API anahtarı bulunamadı.")

    target_text = extract_target_sections(story_text)
    if not target_text:
        raise Exception("Metin içinde 'STORY:' veya 'VIEWER ENGAGEMENT:' bölümleri bulunamadı.")
    
    logging.info(f"İşlenecek metin boyutu: {len(target_text)} karakter.")
    
    audio_content = text_to_speech_process(target_text, keys_to_use)
    if not audio_content:
        raise Exception("Tüm API anahtarları denendi ancak ses içeriği üretilemedi.")
    
    audio_file_path = save_audio(audio_content, output_dir)
    if not audio_file_path:
        raise Exception("Oluşturulan ses dosyası diske kaydedilemedi.")
        
    srt_file_path = generate_synchronized_srt(audio_file_path, output_dir)
    if not srt_file_path:
        logging.warning("Altyazı dosyası oluşturulamadı ancak işlem devam ediyor.")
    
    logging.info("--- Ses ve Altyazı Üretimi Başarıyla Tamamlandı ---")
    return audio_file_path, srt_file_path
