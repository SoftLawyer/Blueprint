# hikayeuretir.py

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import storage, secretmanager
import os
import time
import re
import logging # Logging kütüphanesini import et

# --- Global Değişkenler ---
API_KEYS = []
current_api_key_index = 0
model = None
project_id = "videofabrikam"
TEST_MODE = False # Tam hikaye üretimi için bu False olmalıdır

# --- Bulut Uyumlu Yardımcı Fonksiyonlar ---

def load_api_keys_from_secret_manager():
    """API anahtarlarını tek seferde Secret Manager'dan yükler."""
    global API_KEYS
    if API_KEYS: return True
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/gemini-api-anahtarlari/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        API_KEYS = [line.strip() for line in payload.splitlines() if line.strip()]
        if not API_KEYS:
            logging.error("❌ Secret Manager'da API anahtarı bulunamadı.")
            return False
        logging.info(f"🔑 {len(API_KEYS)} API anahtarı Secret Manager'dan başarıyla yüklendi.")
        return True
    except Exception as e:
        logging.error(f"❌ Secret Manager'dan anahtar okunurken hata: {e}")
        return False

def configure_gemini():
    """Sıradaki API anahtarı ile Gemini'yi yapılandırır."""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        return None
    try:
        api_key = API_KEYS[current_api_key_index]
        logging.info(f"🔄 API anahtarı {current_api_key_index + 1} deneniyor...")
        genai.configure(api_key=api_key)
        generation_config = {"temperature": 0.9, "top_p": 0.95, "top_k": 40, "max_output_tokens": 8192} # Token limitini artırdık
        # Model adını daha stabil bir versiyonla güncelledik
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config)
        logging.info(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        logging.error(f"❌ API anahtarı {current_api_key_index + 1} ile yapılandırma hatası: {e}")
        current_api_key_index += 1
        return configure_gemini()

# GÜNCELLENMİŞ FONKSİYON: Daha detaylı hata kaydı ekledik
def generate_with_failover(prompt):
    """API'ye istek gönderir, kota hatasında diğer anahtarı dener ve detaylı log tutar."""
    global current_api_key_index, model
    
    # Eğer tüm anahtarlar denendiyse, başa dön
    if current_api_key_index >= len(API_KEYS):
        current_api_key_index = 0
        logging.warning("⚠️ Tüm API anahtarları denendi, baştan başlanıyor.")

    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None: 
                    logging.error("❌ Yapılandırılacak geçerli API anahtarı kalmadı.")
                    return None
            
            logging.info(f"🤖 API Anahtarı {current_api_key_index + 1} ile Gemini'ye istek gönderiliyor...")
            response = model.generate_content(prompt)
            
            # YENİ KONTROL: Yanıtın içeriğini kontrol et
            if response and hasattr(response, 'text') and response.text:
                logging.info("✅ Gemini'den başarılı yanıt alındı.")
                return response
            else:
                # Yanıt boşsa veya text içermiyorsa logla
                logging.warning(f"⚠️ API Anahtarı {current_api_key_index + 1} ile Gemini'den boş veya geçersiz yanıt alındı. Yanıt: {response}")
                # Bu durumu bir hata gibi ele alıp sonraki anahtarı dene
                raise Exception("Boş veya geçersiz yanıt alındı")

        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            logging.warning(f"⚠️ API anahtarı {current_api_key_index + 1} kotaya takıldı veya izin sorunu: {e}. Değiştiriliyor...")
            current_api_key_index += 1
            model = None
        except Exception as e:
            logging.error(f"❌ API Anahtarı {current_api_key_index + 1} ile beklenmedik API hatası: {e}")
            logging.error("   Prompt'un ilk 100 karakteri: %s", prompt[:100])
            current_api_key_index += 1
            model = None
    
    logging.error("❌ Tüm API anahtarları denendi ve hepsi başarısız oldu.")
    return None

def validate_story_format(formatted_text):
    """Hikayede STORY: ve VIEWER ENGAGEMENT: bölümlerinin varlığını kontrol eder."""
    logging.info("🔍 Hikaye formatı doğrulanıyor...")
    story_pattern = r'STORY:\s*\n(.+?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)'
    story_match = re.search(story_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    engagement_pattern = r'VIEWER ENGAGEMENT:\s*\n(.+?)(?=\n\s*[-]{5,}|\Z)'
    engagement_match = re.search(engagement_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    
    issues = []
    if not story_match or len(story_match.group(1).strip()) < 100:
        issues.append("STORY bölümü eksik veya çok kısa.")
    if not engagement_match or len(engagement_match.group(1).strip()) < 20:
        issues.append("VIEWER ENGAGEMENT bölümü eksik veya çok kısa.")
    
    if issues:
        logging.warning("⚠️ Format doğrulama sorunları: %s", " | ".join(issues))
        return False
    
    logging.info("✅ Hikaye formatı doğrulandı.")
    return True

def fix_missing_sections(formatted_text, story_title, story_content, engagement_prompt):
    """Eksik STORY: ve VIEWER ENGAGEMENT: bölümlerini düzeltir."""
    logging.info("🔧 Eksik bölümler düzeltiliyor...")
    has_story = re.search(r'STORY:\s*\n', formatted_text, re.IGNORECASE)
    has_engagement = re.search(r'VIEWER ENGAGEMENT:\s*\n', formatted_text, re.IGNORECASE)
    
    if has_story and has_engagement:
        return formatted_text
    
    fixed_parts = [f"Title: {story_title}\n", "STORY:", story_content, "\n\nVIEWER ENGAGEMENT:", engagement_prompt]
    fixed_text = "\n".join(fixed_parts)
    logging.info("✅ Eksik bölümler başarıyla düzeltildi.")
    return fixed_text

class YouTubeRevengeStoryGenerator:
    def __init__(self):
        self.story_structure = {
            1: {"name": "Dramatic Opening", "words": 130}, 2: {"name": "Character Intro", "words": 230},
            3: {"name": "Backstory", "words": 570}, 4: {"name": "Betrayal Process", "words": 670},
            5: {"name": "Calm Reaction", "words": 510}, 6: {"name": "Strategic Move", "words": 1100},
            7: {"name": "Natural Justice", "words": 840}, 8: {"name": "Moral Victory", "words": 440}
        }

    def get_and_update_next_title(self, bucket, source_filename="hikayelerbasligi.txt"):
        try:
            blob = bucket.blob(source_filename)
            if not blob.exists(): return None
            lines = [line.strip() for line in blob.download_as_text(encoding="utf-8").strip().splitlines() if line.strip()]
            if not lines: return None
            title_to_process = lines[0]
            blob.upload_from_string("\n".join(lines[1:]), content_type="text/plain; charset=utf-8")
            logging.info(f"🔹 '{title_to_process}' başlığı GCS'den alındı.")
            return title_to_process
        except Exception as e:
            logging.error(f"❌ GCS'den başlık okunurken hata: {e}")
            return None
    
    def save_current_title(self, title, bucket, target_filename="hikayebasligi.txt"):
        try:
            blob = bucket.blob(f"islenenler/{target_filename}")
            blob.upload_from_string(title, content_type="text/plain; charset=utf-8")
            logging.info(f"💾 İşlenen başlık GCS'e kaydedildi.")
        except Exception as e:
            logging.error(f"❌ Mevcut başlık GCS'e kaydedilirken hata oluştu: {e}")

    def generate_protagonist_profile(self, story_title):
        prompt = f"""Based on this story title: "{story_title}"
Create a protagonist profile in this EXACT format:
Protagonist: [FICTIONAL First Name Last Name], [age 32-58]
Company: [FICTIONAL Company Name] ([industry type])
Location: [US City]
Crisis: [Brief description of the main crisis/conflict]
Requirements:
- ALL names must be completely FICTIONAL
- The Protagonist must only be an American male
- Age between 32-58
- US location that fits the story
- Crisis should match the title's theme
- Keep it concise - one line each
Write ONLY the 4-line profile, nothing else."""
        
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_single_engagement_prompt(self, story_title, story_content):
        prompt = f"""Based on this story title: "{story_title}" and the story content, create ONE SINGLE engagement prompt for viewers.
Choose ONE of these types:
1. A specific question asking "What would you do?"
2. An invitation to share similar experiences in comments
3. A moral/ethical question about the situation
Requirements:
- Write ONLY ONE engagement prompt.
- Make it specific to this story's theme.
- Use casual, conversational tone.
- DO NOT include any emojis.
Write ONLY ONE prompt that fits this specific story perfectly."""
        
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_story_from_title(self, story_title, protagonist_profile):
        logging.info(f"🔄 '{story_title}' başlığına göre ULTRA KISALTILMIŞ hikaye (25-29 dk) BÖLÜM BÖLÜM oluşturuluyor...")
        full_story_parts = []
        story_so_far = ""

        for i, section_info in self.story_structure.items():
            section_name, section_words = section_info["name"], section_info["words"]
            logging.info(f"\n   ➡️  Bölüm {i}/{len(self.story_structure)}: '{section_name}' (~{section_words} kelime) oluşturuluyor...")
            
            prompt = f"""You are a master storyteller writing a compelling revenge story for a YouTube video.
CRITICAL: This story MUST be ULTRA-CONCISE for exactly 25-29 minutes of audio narration.
STORY TITLE: "{story_title}"
PROTAGONIST PROFILE:
{protagonist_profile}
STORY SO FAR (previous sections):
---
{story_so_far if story_so_far else "This is the first section."}
---
Your task is to write ONLY the NEXT section of the story.
NEXT SECTION TO WRITE:
- Section {i}: {section_name}
- MAXIMUM word count: {section_words} words (DO NOT EXCEED THIS)
ULTRA-CRITICAL REQUIREMENTS:
- Write ONLY the content for this specific section.
- DO NOT write section titles like "Section 1: Dramatic Opening".
- Ensure your writing flows naturally from the "STORY SO FAR".
- Maintain a consistent, engaging, and narrative tone perfect for audio.
- Use the protagonist's details from the profile.
- NEVER exceed the word count limit - be ruthlessly concise.
- Focus ONLY on essential plot points - eliminate ALL fluff.
ABSOLUTE LIMIT: Write MAXIMUM {section_words} words for this section. Count every word carefully."""
            
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                section_text = response.text.strip()
                words = section_text.split()
                if len(words) > section_words:
                    logging.warning(f"   ⚠️  Bölüm {i} çok uzun ({len(words)} kelime), {section_words} kelimeye kısaltılıyor...")
                    section_text = ' '.join(words[:section_words])
                
                full_story_parts.append(section_text)
                story_so_far += section_text + "\n\n"
                word_count = len(section_text.split())
                logging.info(f"   ✅  Bölüm {i} tamamlandı ({word_count} kelime - Hedef: {section_words}).")
                time.sleep(1)
            else:
                logging.error(f"   ❌  Bölüm {i} oluşturulamadı! Hikaye üretimi durduruluyor.")
                return None
        
        final_story = "\n\n".join(full_story_parts)
        total_words = len(final_story.split())
        estimated_minutes = total_words / 170
        logging.info(f"\n✅ ULTRA KISALTILMIŞ hikaye tamamlandı!")
        logging.info(f"📊 Toplam kelime: {total_words}")
        logging.info(f"⏱️ Tahmini süre: {estimated_minutes:.1f} dakika")
        return final_story

    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        content_parts = [
            "="*60,
            f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)",
            "="*60,
            f"\nTitle: {title}",
            "Note: All names, companies, and events are completely fictional.\n",
            "PROTAGONIST PROFILE:",
            "-"*30,
            protagonist_profile,
            "-"*30 + "\n",
            "STORY:",
            story if story else "Story content not available.",
            "\n" + "-"*40 + "\n",
            "VIEWER ENGAGEMENT:",
            engagement_prompt if engagement_prompt else "What do you think about this story?"
        ]
        
        formatted_text = "\n".join(content_parts)
        if not validate_story_format(formatted_text):
            logging.warning("⚠️ Format doğrulaması başarısız, düzeltiliyor...")
            formatted_text = fix_missing_sections(formatted_text, title, story, engagement_prompt)
        
        logging.info("✅ Hikaye formatı garantili olarak doğrulandı")
        return formatted_text

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_story_generation_process(kaynak_bucket_adi, cikti_bucket_adi):
    logging.info("--- Hikaye Üretim Modülü Başlatıldı (v2 - Gelişmiş Hata Kaydı) ---")
    if not load_api_keys_from_secret_manager():
        raise Exception("API anahtarları yüklenemedi.")

    storage_client = storage.Client()
    kaynak_bucket = storage_client.bucket(kaynak_bucket_adi)
    
    generator = YouTubeRevengeStoryGenerator()
    
    story_title = generator.get_and_update_next_title(kaynak_bucket)
    if not story_title:
        return None, None, None, None, None

    generator.save_current_title(story_title, kaynak_bucket)
    logging.info(f"\n📖 İşlenecek başlık: {story_title}")

    protagonist_profile = generator.generate_protagonist_profile(story_title)
    if not protagonist_profile: 
        raise Exception("Kahraman profili oluşturulamadı!")
    logging.info("✅ Kahraman profili oluşturuldu.")

    story_content = None
    if TEST_MODE:
        story_content = "This is a test story for TEST MODE." # Test modu için basit metin
    else:
        story_content = generator.generate_story_from_title(story_title, protagonist_profile)

    if not story_content: 
        raise Exception("Hikaye içeriği oluşturulamadı!")
    
    engagement_prompt = generator.generate_single_engagement_prompt(story_title, story_content)
    
    formatted_text = generator.format_story_for_saving(
        story_content, story_title, protagonist_profile, engagement_prompt, 
        is_opening_only=TEST_MODE
    )

    if not formatted_text:
        raise Exception("Hikaye metni formatlanamadı.")

    return story_content, story_title, protagonist_profile, API_KEYS, formatted_text
