# googleilesesolustur.py (Orijinal Kodun Secret Manager Uyumlu Versiyonu)

import os
import re
import logging
import tempfile
import wave
import struct
import json
import base64

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

# Sabitler (Orijinal kodunuzdan alındı)
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 3500
MAX_SENTENCE_BYTES = 700
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

# --- Orijinal Kodunuzdaki Tüm Fonksiyonlar (Değiştirilmedi) ---

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
        logging.info(f"📋 Metin başlangıcı (ilk 200 karakter):\n{repr(text[:200])}")
        story_patterns = [
            r'STORY:\s*\n(.*?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)',
            r'STORY:\s*\r?\n(.*?)(?=\r?\n\s*[-]{5,}|\r?\n\s*VIEWER ENGAGEMENT:|\Z)',
            r'STORY:\s*(.*?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)',
            r'(?i)story:\s*\n(.*?)(?=\n\s*[-]{5,}|\n\s*viewer engagement:|\Z)'
        ]
        engagement_patterns = [
            r'VIEWER ENGAGEMENT:\s*\n(.*?)(?=\n\s*[-]{5,}|\Z)',
            r'VIEWER ENGAGEMENT:\s*\r?\n(.*?)(?=\n\s*[-]{5,}|\Z)',
            r'VIEWER ENGAGEMENT:\s*(.*?)(?=\n\s*[-]{5,}|\Z)',
            r'(?i)viewer engagement:\s*\n(.*?)(?=\n\s*[-]{5,}|\Z)'
        ]
        extracted_text = ""
        sections_found = 0
        story_match = None
        for pattern in story_patterns:
            story_match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if story_match: break
        if story_match:
            story_content = story_match.group(1).strip()
            if story_content:
                extracted_text += story_content + "\n\n"
                sections_found += 1
                logging.info(f"✅ STORY bölümü bulundu ({len(story_content)} karakter)")
        engagement_match = None
        for pattern in engagement_patterns:
            engagement_match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if engagement_match: break
        if engagement_match:
            engagement_content = engagement_match.group(1).strip()
            if engagement_content:
                extracted_text += engagement_content
                sections_found += 1
                logging.info(f"✅ VIEWER ENGAGEMENT bölümü bulundu ({len(engagement_content)} karakter)")
        if sections_found == 0:
            logging.warning("❌ Hiçbir hedef bölüm bulunamadı! Tüm metin kullanılacak.")
            return text.strip()
        extracted_text = extracted_text.strip()
        logging.info(f"✅ Toplam {sections_found} bölüm çıkarıldı ({len(extracted_text)} karakter)")
        return extracted_text
    except Exception as e:
        logging.error(f"❌ Bölüm çıkarma hatası: {e}. Tüm metin kullanılacak.")
        return text.strip()

def fix_long_sentences(text):
    logging.info("🔧 Uzun cümleler kontrol ediliyor ve düzeltiliyor...")
    sentences = re.split(r'(?<=[.!?])\s+', text)
    fixed_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence: continue
        if len(sentence.encode('utf-8')) <= MAX_SENTENCE_BYTES:
            fixed_sentences.append(sentence)
        else:
            logging.warning(f"   ⚠️ Uzun cümle bulundu: {len(sentence.encode('utf-8'))} byte - bölünüyor...")
            broken_parts = break_long_sentence_naturally(sentence)
            fixed_sentences.extend(broken_parts)
    result = ' '.join(fixed_sentences)
    logging.info("✅ Tüm uzun cümleler başarıyla düzeltildi")
    return result

def break_long_sentence_naturally(sentence):
    parts = []
    natural_patterns = [
        r'(,\s+(?:and|but|or|so|yet|for|nor)\s+)', r'(,\s+(?:however|therefore|moreover|furthermore|nevertheless)\s+)',
        r'(;\s+)', r'(,\s+(?:which|that|who|where|when)\s+)', r'(,\s+)', r'(:\s+)'
    ]
    current_sentence = sentence
    for pattern in natural_patterns:
        if len(current_sentence.encode('utf-8')) <= MAX_SENTENCE_BYTES: break
        split_parts = re.split(pattern, current_sentence)
        if len(split_parts) > 1:
            temp_parts = []
            current_part = ""
            for part in split_parts:
                test_part = current_part + part
                if len(test_part.encode('utf-8')) <= MAX_SENTENCE_BYTES:
                    current_part = test_part
                else:
                    if current_part.strip():
                        if not current_part.rstrip().endswith(('.', '!', '?')): current_part = current_part.rstrip() + '.'
                        temp_parts.append(current_part.strip())
                    current_part = part
            if current_part.strip():
                if not current_part.rstrip().endswith(('.', '!', '?')): current_part = current_part.rstrip() + '.'
                temp_parts.append(current_part.strip())
            if len(temp_parts) > 1: return temp_parts
    return break_by_words(sentence)

def break_by_words(sentence):
    words = sentence.split()
    parts = []
    current_part = ""
    for word in words:
        test_part = current_part + " " + word if current_part else word
        if len(test_part.encode('utf-8')) <= MAX_SENTENCE_BYTES - 10:
            current_part = test_part
        else:
            if current_part:
                if not current_part.rstrip().endswith(('.', '!', '?')): current_part = current_part.rstrip() + '.'
                parts.append(current_part.strip())
            current_part = word
    if current_part:
        if not current_part.rstrip().endswith(('.', '!', '?')): current_part = current_part.rstrip() + '.'
        parts.append(current_part.strip())
    return parts

def smart_text_splitter(text, max_length=API_CHUNK_SIZE):
    logging.info("🧠 Metin akıllı şekilde bölünüyor...")
    text = fix_long_sentences(text)
    chunks = []
    remaining_text = text
    while len(remaining_text.encode('utf-8')) > max_length:
        split_pos = find_safe_split_position(remaining_text, max_length)
        if split_pos <= 0: split_pos = len(remaining_text) // 2
        chunk = remaining_text[:split_pos].strip()
        if chunk: chunks.append(chunk)
        remaining_text = remaining_text[split_pos:].strip()
    if remaining_text.strip(): chunks.append(remaining_text.strip())
    logging.info(f"✅ Metin {len(chunks)} parçaya güvenli şekilde bölündü")
    return chunks

def find_safe_split_position(text, max_length):
    try:
        if len(text.encode('utf-8')) <= max_length: return len(text)
        for i in range(min(len(text), max_length), max_length // 2, -1):
            if i < len(text) and text[i-1] in '.!?': return i
        paragraph_end = text.rfind('\n', 0, max_length)
        if paragraph_end > max_length // 2: return paragraph_end
        word_end = text.rfind(' ', 0, max_length)
        if word_end > max_length // 2: return word_end
        return max_length // 2
    except Exception as e:
        logging.error(f"❌ Güvenli bölme hatası: {e}")
        return max_length // 2

# --- GÜNCELLENMİŞ: Google Cloud Kütüphanesi ile Ses Üretimi ---

def process_single_chunk(client, chunk, chunk_id, recursion_depth=0):
    """Tek bir metin parçasını sese dönüştürür."""
    if recursion_depth > MAX_RECURSION_DEPTH:
        logging.error(f"❌ Parça {chunk_id}: Maksimum bölme derinliği aşıldı! Atlanıyor...")
        return None
    try:
        logging.info(f"      📏 Parça {chunk_id} boyutu: {len(chunk.encode('utf-8'))} byte")
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Chirp3-HD-Enceladus")
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=0.99,
            sample_rate_hertz=SAMPLE_RATE
        )
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        logging.info(f"      ✅ Parça {chunk_id} başarıyla işlendi")
        return response.audio_content
    except Exception as e:
        logging.error(f"      ❌ Parça {chunk_id} API hatası: {e}")
        if "too long" in str(e).lower() and recursion_depth < MAX_RECURSION_DEPTH:
            logging.warning(f"         🔪 Parça {chunk_id} çok uzun, daha küçük parçalara bölünüyor...")
            smaller_chunks = smart_text_splitter(chunk, 1500)
            combined_audio = b''
            for i, small_chunk in enumerate(smaller_chunks):
                small_audio = process_single_chunk(client, small_chunk, f"{chunk_id}.{i+1}", recursion_depth + 1)
                if small_audio: combined_audio += small_audio
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
            logging.info(f"   ➡️ Parça {i}/{len(text_chunks)} işleniyor...")
            audio_data = process_single_chunk(client, chunk, str(i))
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
        final_audio += b'\x00\x00' * int(10 * SAMPLE_RATE)
        logging.info("➕ Sesin sonuna 10 saniye sessizlik eklendi.")
        return final_audio

    except Exception as e:
        logging.error(f"❌ TTS genel hatası: {e}")
        return None

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses dosyasını kaydeder."""
    try:
        if not audio_content:
            logging.error("❌ Kaydedilecek ses verisi yok!")
            return None
        full_path = os.path.join(output_dir, filename)
        with wave.open(full_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_content)
        file_size = os.path.getsize(full_path)
        logging.info(f"✅ Ses dosyası kaydedildi: {full_path} ({file_size:,} byte)")
        return full_path
    except Exception as e:
        logging.error(f"❌ Ses kaydetme hatası: {e}")
        return None

def seconds_to_srt_time(seconds):
    """Saniyeyi SRT formatına çevirir."""
    try:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    except:
        return "00:00:00,000"

def generate_synchronized_srt(audio_file_path, output_dir):
    """Whisper ile senkronize SRT altyazısı oluşturur."""
    try:
        logging.info("\n🤖 Whisper modeli yükleniyor...")
        model = whisper.load_model("base")
        logging.info("🎤 Ses dosyası deşifre ediliyor...")
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
        logging.info(f"✅ SRT altyazı dosyası oluşturuldu: {srt_file_path}")
        return srt_file_path
    except Exception as e:
        logging.error(f"❌ Altyazı oluşturma hatası: {e}")
        return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_audio_and_srt_process(story_text, output_dir, worker_project_id):
    """Ana ses ve senkronize altyazı üretme iş akışını yönetir."""
    logging.info("--- Ses ve Senkronize Altyazı Üretim Modülü Başlatıldı (Secret Manager & WAV) ---")
    
    target_text = extract_target_sections(story_text)
    if not target_text:
        raise Exception("Hedef bölümler bulunamadı!")
    
    logging.info(f"\n📊 İşlenecek metin bilgileri:")
    logging.info(f"    📝 Karakter: {len(target_text):,}")
    logging.info(f"    📝 Kelime: {len(target_text.split()):,}")
    logging.info(f"    📝 Byte: {len(target_text.encode('utf-8')):,}")
    
    logging.info("\n🎵 Chirp3-HD-Enceladus sesi ile işleniyor...")
    audio_content = text_to_speech_with_sa_key(target_text, worker_project_id)
    if audio_content is None:
        raise Exception("Ses içeriği üretilemedi.")
    
    audio_file_path = save_audio(audio_content, output_dir)
    if not audio_file_path:
        raise Exception("WAV dosyası kaydedilemedi.")
        
    srt_file_path = generate_synchronized_srt(audio_file_path, output_dir)
    
    return audio_file_path, srt_file_path
