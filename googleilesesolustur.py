# googleilesesolustur.py (v5 - Girinti Hatası Düzeltilmiş)


import os
import re
import logging
import tempfile
import wave
import struct

# --- Gerekli Google Cloud ve AI Kütüphaneleri ---
try:
    from google.cloud import texttospeech, secretmanager
    from google.oauth2 import service_account
    import whisper
except ImportError:
    print("⚠️ Gerekli Google Cloud kütüphaneleri bulunamadı.")
    print("   Lütfen 'pip install google-cloud-texttospeech google-cloud-secret-manager google-auth git+https://github.com/openai/whisper.git' komutunu çalıştırın.")
    exit()

# --- Global Değişkenler ---
SERVICE_ACCOUNT_SECRET_NAME = "vertex-ai-sa-key"
temp_key_path = None

# Sabitler
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 3000
MAX_RECURSION_DEPTH = 3

# --- Güvenli Kimlik Doğrulama Fonksiyonu ---

def load_sa_key_from_secret_manager(project_id):
    """Servis hesabı anahtarını Secret Manager'dan indirip geçici bir dosyaya yazar."""
    global temp_key_path
    if temp_key_path and os.path.exists(temp_key_path):
        return temp_key_path
    try:
        logging.info(f"🔄 Servis hesabı anahtarı '{SERVICE_ACCOUNT_SECRET_NAME}' Secret Manager'dan okunuyor...")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{SERVICE_ACCOUNT_SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        key_payload = response.payload.data

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as temp_file:
            temp_file.write(key_payload.decode('utf-8'))
            temp_key_path = temp_file.name
        
        logging.info(f"✅ Servis hesabı anahtarı başarıyla geçici dosyaya yazıldı: {temp_key_path}")
        return temp_key_path
    except Exception as e:
        logging.error(f"❌ Secret Manager'dan servis hesabı anahtarı okunurken hata oluştu: {e}")
        return None

# --- WAV Olarak Ses Üretimi ---

def process_single_chunk_tts(client, chunk, chunk_id, recursion_depth=0):
    """Tek bir metin parçasını WAV (LINEAR16) formatında sese dönüştürür."""
    if recursion_depth > MAX_RECURSION_DEPTH:
        logging.error(f"❌ Parça {chunk_id}: Maksimum bölme derinliği aşıldı! Atlanıyor...")
        return None
    try:
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Chirp3-HD-Enceladus")
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=0.99,
            sample_rate_hertz=SAMPLE_RATE
        )
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        logging.info(f"✅ Parça {chunk_id} başarıyla sese dönüştürüldü.")
        return response.audio_content
    except Exception as e:
        logging.error(f"❌ Parça {chunk_id} API hatası: {e}")
        if "too long" in str(e).lower() and recursion_depth < MAX_RECURSION_DEPTH:
            logging.warning(f"   🔪 Parça {chunk_id} çok uzun, daha küçük parçalara bölünüyor...")
            smaller_chunks = smart_text_splitter(chunk, API_CHUNK_SIZE // 2)
            combined_audio = b''
            for i, small_chunk in enumerate(smaller_chunks):
                small_audio = process_single_chunk_tts(client, small_chunk, f"{chunk_id}.{i+1}", recursion_depth + 1)
                if small_audio:
                    combined_audio += small_audio
            return combined_audio
        return None

def text_to_speech_with_sa_key(text, worker_project_id):
    """Ana TTS fonksiyonu - Secret Manager'dan alınan anahtarla çalışır."""
    try:
        key_path = load_sa_key_from_secret_manager(worker_project_id)
        if not key_path:
            raise Exception("Servis hesabı anahtarı Secret Manager'dan yüklenemedi.")
            
        credentials = service_account.Credentials.from_service_account_file(key_path)
        client = texttospeech.TextToSpeechClient(credentials=credentials)
        logging.info("✅ Text-to-Speech client (Servis Hesabı) başarıyla oluşturuldu.")
        
        text_chunks = smart_text_splitter(text)
        
        combined_audio_content = b''
        for i, chunk in enumerate(text_chunks, 1):
            audio_data = process_single_chunk_tts(client, chunk, str(i))
            if audio_data:
                combined_audio_content += audio_data
                if i < len(text_chunks):
                    silence = b'\x00\x00' * int(SAMPLE_RATE * 0.2)
                    combined_audio_content += silence
            else:
                logging.error(f"    ❌ Parça {i} başarısız oldu, ses üretimi durduruluyor.")
                return None
        
        logging.info("✅ Tüm parçalar başarıyla birleştirildi!")
        final_audio = apply_fade_out(combined_audio_content)
        final_audio += b'\x00\x00' * int(10 * SAMPLE_RATE) # Sona 10 saniye sessizlik
        return final_audio

    except Exception as e:
        logging.error(f"❌ TTS genel hatası: {e}")
        return None
        
# --- Diğer Fonksiyonlar (Değiştirilmedi) ---
def apply_fade_out(audio_data, fade_duration_ms=500):
    try:
        logging.info(f"🌬️ Sona doğal bir bitiş için {fade_duration_ms}ms'lik 'fade-out' efekti uygulanıyor...")
        sample_width = 2
        fade_samples = int(SAMPLE_RATE * (fade_duration_ms / 1000.0))
        total_samples = len(audio_data) // sample_width
        fade_samples = min(fade_samples, total_samples)
        if fade_samples == 0: return audio_data
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
        logging.warning(f"⚠️ Fade-out uygulanamadı: {e}. Ses orjinal haliyle bırakılıyor.")
        return audio_data

def extract_target_sections(text):
    try:
        logging.info("🔍 STORY: ve VIEWER ENGAGEMENT: bölümleri aranıyor...")
        story_match = re.search(r'STORY:\s*\n(.*?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)', text, re.DOTALL | re.IGNORECASE)
        engagement_match = re.search(r'VIEWER ENGAGEMENT:\s*\n(.*?)(?=\n\s*[-]{5,}|\Z)', text, re.DOTALL | re.IGNORECASE)
        extracted_text = ""
        if story_match and story_match.group(1).strip(): extracted_text += story_match.group(1).strip() + "\n\n"
        if engagement_match and engagement_match.group(1).strip(): extracted_text += engagement_match.group(1).strip()
        if not extracted_text: logging.warning("❌ Hiçbir hedef bölüm bulunamadı! Tüm metin kullanılacak."); return text.strip()
        return extracted_text.strip()
    except Exception as e:
        logging.error(f"❌ Bölüm çıkarma hatası: {e}. Tüm metin kullanılacak."); return text.strip()

# DÜZELTİLMİŞ FONKSİYON
def smart_text_splitter(text, max_length=API_CHUNK_SIZE):
    chunks = []
    while len(text.encode('utf-8')) > max_length:
        split_pos = -1
        # Cümle sonu karakterlerini (. ! ?) önceliklendir
        for delimiter in ['.', '!', '?']:
            pos = text.rfind(delimiter, 0, max_length)
            if pos > split_pos:
                split_pos = pos
        
        # Cümle sonu bulunamazsa, en yakın boşluktan böl
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, max_length)
        
        # Hiçbir bölme noktası bulunamazsa, zorla böl
        if split_pos == -1:
            split_pos = max_length
        
        # Bölme noktasını bir karakter ileri alarak noktalama işaretini dahil et
        split_pos += 1
        
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    chunks.append(text)
    logging.info(f"✅ Metin {len(chunks)} parçaya güvenli şekilde bölündü")
    return chunks

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses dosyasını WAV olarak kaydeder."""
    try:
        if not audio_content: logging.error("❌ Kaydedilecek ses verisi yok!"); return None
        full_path = os.path.join(output_dir, filename)
        with wave.open(full_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_content)
        logging.info(f"✅ WAV dosyası kaydedildi: {full_path} ({len(audio_content):,} byte)"); return full_path
    except Exception as e: logging.error(f"❌ WAV kaydetme hatası: {e}"); return None

def seconds_to_srt_time(seconds):
    try:
        hours, rem = divmod(seconds, 3600); minutes, seconds = divmod(rem, 60); milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"
    except: return "00:00:00,000"

def generate_synchronized_srt(audio_file_path, output_dir):
    try:
        logging.info("🤖 Whisper modeli yükleniyor..."); model = whisper.load_model("base"); logging.info("🎤 Ses dosyası deşifre ediliyor...")
        result = model.transcribe(audio_file_path, fp16=False, language="en"); srt_content = []
        for i, segment in enumerate(result['segments'], 1):
            start_time = seconds_to_srt_time(segment['start']); end_time = seconds_to_srt_time(segment['end']); text = segment['text'].strip()
            srt_content.extend([str(i), f"{start_time} --> {end_time}", text, ""])
        srt_file_path = os.path.join(output_dir, "altyazi.srt")
        with open(srt_file_path, 'w', encoding='utf-8') as srt_file: srt_file.write('\n'.join(srt_content))
        logging.info(f"✅ SRT altyazı dosyası oluşturuldu: {srt_file_path}"); return srt_file_path
    except Exception as e: logging.error(f"❌ Altyazı oluşturma hatası: {e}"); return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_audio_and_srt_process(story_text, output_dir, worker_project_id):
    """Ana ses ve senkronize altyazı üretme iş akışını yönetir."""
    logging.info("--- Ses ve Senkronize Altyazı Üretim Modülü Başlatıldı (Secret Manager & WAV) ---")
    
    target_text = extract_target_sections(story_text)
    if not target_text:
        raise Exception("Hedef bölümler bulunamadı!")
    
    audio_content = text_to_speech_with_sa_key(target_text, worker_project_id)
    if audio_content is None:
        raise Exception("Ses içeriği üretilemedi.")
    
    audio_file_path = save_audio(audio_content, output_dir)
    if not audio_file_path:
        raise Exception("WAV dosyası kaydedilemedi.")
        
    srt_file_path = generate_synchronized_srt(audio_file_path, output_dir)
    
    return audio_file_path, srt_file_path
