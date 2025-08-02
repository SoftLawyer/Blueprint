import os
import requests
import json
import time
import wave
import base64
import whisper
import re
import struct # Fade-out efekti için eklendi

# Sabitler
SAMPLE_RATE = 24000
API_CHUNK_SIZE = 3500  # Güvenli limit
MAX_SENTENCE_BYTES = 700  # Güvenli cümle limiti
MAX_RECURSION_DEPTH = 3  # Sonsuz döngüyü önler

# --- YENİ FONKSİYON: FADE-OUT EFEKTİ ---
def apply_fade_out(audio_data, fade_duration_ms=500):
    """
    Ses verisinin sonuna yumuşak bir bitiş (linear fade-out) uygular.
    Bu, sesin aniden kesilmesi yerine yavaşça kısılarak bitmesini sağlar.
    """
    try:
        print(f"🌬️ Sona doğal bir bitiş için {fade_duration_ms}ms'lik 'fade-out' efekti uygulanıyor...")
        sample_width = 2  # 16-bit ses (LINEAR16) için 2 byte
        
        # Fade-out uygulanacak sample (örnek) sayısı
        fade_samples = int(SAMPLE_RATE * (fade_duration_ms / 1000.0))
        
        # Toplam sample sayısını hesapla
        total_samples = len(audio_data) // sample_width
        
        # Fade-out yapılacak sample sayısı, toplam sample sayısından fazla olamaz
        fade_samples = min(fade_samples, total_samples)

        if fade_samples == 0:
            return audio_data # Fade-out uygulanamayacak kadar kısa ses

        # Sesi, fade-out uygulanacak ve uygulanmayacak kısım olarak ikiye ayır
        main_part = audio_data[:-fade_samples * sample_width]
        fade_part = audio_data[-fade_samples * sample_width:]

        faded_audio = bytearray()
        
        # Fade-out kısmındaki her bir sample'ı işle
        for i in range(fade_samples):
            # Ses seviyesi çarpanını hesapla (1.0'dan 0.0'a doğru azalır)
            multiplier = 1.0 - (i / fade_samples)
            
            # Mevcut sample'ı byte'lardan integer'a çevir
            sample_bytes = fade_part[i * sample_width : (i + 1) * sample_width]
            original_sample = struct.unpack('<h', sample_bytes)[0] # '<h' = little-endian, signed short
            
            # Sesi kıs ve yeni değeri hesapla
            faded_sample = int(original_sample * multiplier)
            
            # Yeni değeri tekrar byte'a çevirip ekle
            faded_audio.extend(struct.pack('<h', faded_sample))
            
        # Ana kısmı ve fade-out uygulanmış kısmı birleştir
        return main_part + faded_audio
        
    except Exception as e:
        print(f"⚠️ Fade-out uygulanamadı: {e}. Ses orjinal haliyle bırakılıyor.")
        return audio_data

def extract_target_sections(text):
    """STORY: ve VIEWER ENGAGEMENT: bölümlerini çıkarır"""
    try:
        print("🔍 STORY: ve VIEWER ENGAGEMENT: bölümleri aranıyor...")
        
        # DEBUG: Metnin başını kontrol et
        print(f"📋 Metin başlangıcı (ilk 200 karakter):")
        print(repr(text[:200]))
        
        # DAHA ESNEK REGEX PATTERN'LER
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
        
        # STORY bölümünü ara
        story_match = None
        for pattern in story_patterns:
            story_match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if story_match:
                print(f"✅ STORY bulundu - Pattern: {pattern[:50]}...")
                break
        
        if story_match:
            story_content = story_match.group(1).strip()
            if story_content:
                extracted_text += story_content + "\n\n"
                sections_found += 1
                print(f"✅ STORY bölümü bulundu ({len(story_content)} karakter)")
            else:
                print("⚠️ STORY bölümü boş")
        else:
            print("❌ STORY bölümü bulunamadı")
        
        # VIEWER ENGAGEMENT bölümünü ara
        engagement_match = None
        for pattern in engagement_patterns:
            engagement_match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if engagement_match:
                print(f"✅ VIEWER ENGAGEMENT bulundu - Pattern: {pattern[:50]}...")
                break
        
        if engagement_match:
            engagement_content = engagement_match.group(1).strip()
            if engagement_content:
                extracted_text += engagement_content
                sections_found += 1
                print(f"✅ VIEWER ENGAGEMENT bölümü bulundu ({len(engagement_content)} karakter)")
            else:
                print("⚠️ VIEWER ENGAGEMENT bölümü boş")
        else:
            print("❌ VIEWER ENGAGEMENT bölümü bulunamadı")
        
        if sections_found == 0:
            print("❌ Hiçbir hedef bölüm bulunamadı!")
            print("🔍 FALLBACK: Tüm metni kullanacağım...")
            return text.strip()
        
        extracted_text = extracted_text.strip()
        print(f"✅ Toplam {sections_found} bölüm çıkarıldı ({len(extracted_text)} karakter)")
        
        return extracted_text
        
    except Exception as e:
        print(f"❌ Bölüm çıkarma hatası: {e}")
        print("🔍 FALLBACK: Tüm metni kullanacağım...")
        return text.strip()

def fix_long_sentences(text):
    """Uzun cümleleri doğal noktalarda böler"""
    print("🔧 Uzun cümleler kontrol ediliyor ve düzeltiliyor...")
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    fixed_sentences = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_bytes = len(sentence.encode('utf-8'))
        
        if sentence_bytes <= MAX_SENTENCE_BYTES:
            fixed_sentences.append(sentence)
        else:
            print(f"    ⚠️ Uzun cümle bulundu: {sentence_bytes} byte - bölünüyor...")
            broken_parts = break_long_sentence_naturally(sentence)
            fixed_sentences.extend(broken_parts)
    
    result = ' '.join(fixed_sentences)
    print("✅ Tüm uzun cümleler başarıyla düzeltildi")
    return result

def break_long_sentence_naturally(sentence):
    """Cümleyi doğal noktalarda böler"""
    parts = []
    
    natural_patterns = [
        r'(,\s+(?:and|but|or|so|yet|for|nor)\s+)',
        r'(,\s+(?:however|therefore|moreover|furthermore|nevertheless)\s+)',
        r'(;\s+)',
        r'(,\s+(?:which|that|who|where|when)\s+)',
        r'(,\s+)',
        r'(:\s+)'
    ]
    
    current_sentence = sentence
    
    for pattern in natural_patterns:
        if len(current_sentence.encode('utf-8')) <= MAX_SENTENCE_BYTES:
            break
            
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
                        if not current_part.rstrip().endswith(('.', '!', '?')):
                            current_part = current_part.rstrip() + '.'
                        temp_parts.append(current_part.strip())
                    current_part = part
            
            if current_part.strip():
                if not current_part.rstrip().endswith(('.', '!', '?')):
                    current_part = current_part.rstrip() + '.'
                temp_parts.append(current_part.strip())
            
            if len(temp_parts) > 1:
                return temp_parts
    
    return break_by_words(sentence)

def break_by_words(sentence):
    """Kelime bazında böler - son çare"""
    words = sentence.split()
    parts = []
    current_part = ""
    
    for word in words:
        test_part = current_part + " " + word if current_part else word
        
        if len(test_part.encode('utf-8')) <= MAX_SENTENCE_BYTES - 10:
            current_part = test_part
        else:
            if current_part:
                if not current_part.rstrip().endswith(('.', '!', '?')):
                    current_part = current_part.rstrip() + '.'
                parts.append(current_part.strip())
            current_part = word
    
    if current_part:
        if not current_part.rstrip().endswith(('.', '!', '?')):
            current_part = current_part.rstrip() + '.'
        parts.append(current_part.strip())
    
    return parts

def smart_text_splitter(text, max_length=API_CHUNK_SIZE):
    """Metni akıllı şekilde böler"""
    print("🧠 Metin akıllı şekilde bölünüyor...")
    
    text = fix_long_sentences(text)
    
    chunks = []
    remaining_text = text
    
    while len(remaining_text.encode('utf-8')) > max_length:
        split_pos = find_safe_split_position(remaining_text, max_length)
        
        if split_pos <= 0:
            split_pos = len(remaining_text) // 2
        
        chunk = remaining_text[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        
        remaining_text = remaining_text[split_pos:].strip()
    
    if remaining_text.strip():
        chunks.append(remaining_text.strip())
    
    print(f"✅ Metin {len(chunks)} parçaya güvenli şekilde bölündü")
    return chunks

def find_safe_split_position(text, max_length):
    """Güvenli bölme noktası bulur"""
    try:
        if len(text.encode('utf-8')) <= max_length:
            return len(text)
        
        for i in range(min(len(text), max_length), max_length // 2, -1):
            if i < len(text) and text[i-1] in '.!?':
                return i
        
        paragraph_end = text.rfind('\n', 0, max_length)
        if paragraph_end > max_length // 2:
            return paragraph_end
        
        word_end = text.rfind(' ', 0, max_length)
        if word_end > max_length // 2:
            return word_end
        
        return max_length // 2
        
    except Exception as e:
        print(f"❌ Güvenli bölme hatası: {e}")
        return max_length // 2

def test_api_key(api_key, key_number):
    """API anahtarını test eder"""
    try:
        print(f"🔍 API anahtarı {key_number} test ediliyor...")
        
        if not api_key or len(api_key) < 30:
            print(f"❌ API anahtarı {key_number} çok kısa")
            return False
        
        test_url = f"https://texttospeech.googleapis.com/v1/voices?key={api_key}"
        response = requests.get(test_url, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ API anahtarı {key_number} geçerli")
            return True
        else:
            print(f"❌ API anahtarı {key_number} geçersiz - Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ API anahtarı {key_number} test hatası: {e}")
        return False

def process_single_chunk(chunk, api_key, chunk_id, recursion_depth=0):
    """Tek chunk'ı işler"""
    if recursion_depth > MAX_RECURSION_DEPTH:
        print(f"❌ Parça {chunk_id}: Maksimum bölme derinliği aşıldı! Atlanıyor...")
        return None
    
    try:
        chunk_bytes = len(chunk.encode('utf-8'))
        print(f"         📏 Parça {chunk_id} boyutu: {chunk_bytes} byte")
        
        if chunk_bytes > 3000:
            print(f"         🔪 Parça {chunk_id} çok büyük, bölünüyor...")
            smaller_chunks = smart_text_splitter(chunk, 2500)
            
            combined_audio = b''
            for i, small_chunk in enumerate(smaller_chunks):
                small_audio = process_single_chunk(
                    small_chunk, 
                    api_key, 
                    f"{chunk_id}.{i+1}", 
                    recursion_depth + 1
                )
                if small_audio:
                    combined_audio += small_audio
                else:
                    return None
            
            return combined_audio if combined_audio else None
        
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        
        data = {
            "input": {"text": chunk},
            "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Enceladus"},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "speakingRate": 0.99,
                "sampleRateHertz": SAMPLE_RATE
            }
        }
        
        response = requests.post(url, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if 'audioContent' in result:
                audio_data = base64.b64decode(result['audioContent'])
                print(f"         ✅ Parça {chunk_id} başarıyla işlendi")
                return audio_data
            else:
                print(f"         ❌ Parça {chunk_id}: Ses verisi bulunamadı")
                return None
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                error_info = response.json()
                error_msg = error_info.get('error', {}).get('message', error_msg)
            except:
                pass
            
            print(f"         ❌ Parça {chunk_id} API hatası: {error_msg}")
            
            if ("too long" in error_msg.lower() or "900 bytes" in error_msg) and recursion_depth < MAX_RECURSION_DEPTH:
                print(f"         🔪 Parça {chunk_id} daha küçük parçalara bölünüyor...")
                ultra_small_chunks = smart_text_splitter(chunk, 1500)
                
                combined_audio = b''
                for i, tiny_chunk in enumerate(ultra_small_chunks):
                    tiny_audio = process_single_chunk(
                        tiny_chunk, 
                        api_key, 
                        f"{chunk_id}.tiny.{i+1}", 
                        recursion_depth + 1
                    )
                    if tiny_audio:
                        combined_audio += tiny_audio
                    else:
                        continue
                
                return combined_audio if combined_audio else None
            
            return None
            
    except Exception as e:
        print(f"         ❌ Parça {chunk_id} beklenmeyen hata: {e}")
        return None

def text_to_speech_chirp3_only(text, api_keys):
    """Ana TTS fonksiyonu - GÜNCELLENDİ"""
    try:
        print("🔍 API anahtarları test ediliyor...")
        valid_keys = []
        
        for i, key in enumerate(api_keys, 1):
            if test_api_key(key, i):
                valid_keys.append((i, key))
        
        if not valid_keys:
            print("❌ Hiçbir API anahtarı geçerli değil!")
            return None
        
        print(f"✅ {len(valid_keys)} geçerli API anahtarı bulundu")

        text_chunks = smart_text_splitter(text)
        print(f"ℹ️ Metin {len(text_chunks)} parçaya bölündü")

        for key_number, api_key in valid_keys:
            print(f"\n🔄 API anahtarı {key_number} ile deneniyor...")
            combined_audio_content = b''
            successful_chunks = 0
            
            for i, chunk in enumerate(text_chunks, 1):
                print(f"    ➡️ Parça {i}/{len(text_chunks)} işleniyor...")
                
                audio_data = process_single_chunk(chunk, api_key, str(i))
                
                if audio_data:
                    combined_audio_content += audio_data
                    successful_chunks += 1
                    
                    # Parçalar arası kısa sessizlik ekle
                    if i < len(text_chunks):
                        silence_duration = 0.2  # 200ms
                        silence_samples = int(SAMPLE_RATE * silence_duration)
                        silence = b'\x00\x00' * silence_samples
                        combined_audio_content += silence
                else:
                    print(f"    ❌ Parça {i} başarısız")
            
            if successful_chunks == len(text_chunks):
                print(f"✅ Tüm parçalar başarıyla işlendi!")
                
                # --- GÜNCELLEME: DOĞAL BİTİŞ İÇİN FADE-OUT UYGULA ---
                final_audio = apply_fade_out(combined_audio_content)
                
                # --- YENİ EKLEME: SONA 10 SANİYE SESSİZLİK EKLE ---
                print("➕ Sesin sonuna 10 saniye sessizlik ekleniyor...")
                silence_duration_seconds = 10
                num_silence_samples = int(silence_duration_seconds * SAMPLE_RATE)
                silence_bytes = b'\x00\x00' * num_silence_samples
                final_audio += silence_bytes
                # --- YENİ EKLEME SONU ---
                
                return final_audio

            else:
                print(f"⚠️ {successful_chunks}/{len(text_chunks)} parça başarılı, sonraki API anahtarı deneniyor...")
        
        print("❌ Tüm API anahtarları denendi, başarısız!")
        return None
        
    except Exception as e:
        print(f"❌ TTS genel hatası: {e}")
        return None

def save_audio(audio_content, output_dir, filename='ses.wav'):
    """Ses dosyasını kaydet"""
    try:
        if not audio_content:
            print("❌ Kaydedilecek ses verisi yok!")
            return None
        
        full_path = os.path.join(output_dir, filename)
        with wave.open(full_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_content)
        
        file_size = os.path.getsize(full_path)
        print(f"✅ Ses dosyası kaydedildi: {full_path} ({file_size:,} byte)")
        return full_path
        
    except Exception as e:
        print(f"❌ Ses kaydetme hatası: {e}")
        return None

def seconds_to_srt_time(seconds):
    """Saniyeyi SRT formatına çevir"""
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
        print(f"\n🤖 Whisper modeli yükleniyor...")
        model = whisper.load_model("base")  
        print(f"🎤 Ses dosyası deşifre ediliyor...")
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
        print(f"✅ SRT altyazı dosyası oluşturuldu: {srt_file_path}")
        return srt_file_path
    except Exception as e:
        print(f"❌ Altyazı oluşturma hatası: {e}")
        return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_audio_and_srt_process(story_text, output_dir, api_keys_list):
    """Ana ses ve senkronize altyazı üretme iş akışını yönetir."""
    print("--- Ses ve Senkronize Altyazı Üretim Modülü Başlatıldı ---")
    
    target_text = extract_target_sections(story_text)
    if not target_text:
        raise Exception("Hedef bölümler bulunamadı!")
    
    print(f"\n📊 İşlenecek metin bilgileri:")
    print(f"    📝 Karakter: {len(target_text):,}")
    print(f"    📝 Kelime: {len(target_text.split()):,}")
    print(f"    📝 Byte: {len(target_text.encode('utf-8')):,}")
    
    print("\n🎵 Chirp3-HD-Enceladus sesi ile işleniyor...")
    audio_content = text_to_speech_chirp3_only(target_text, api_keys_list)
    if audio_content is None:
        raise Exception("Ses içeriği üretilemedi.")
    
    audio_file_path = save_audio(audio_content, output_dir)
    if not audio_file_path:
        raise Exception("Ses dosyası kaydedilemedi.")
        
    srt_file_path = generate_synchronized_srt(audio_file_path, output_dir)
    
    return audio_file_path, srt_file_path
