# hikayeuretir.py (v3 - Secret Manager'dan Güvenli Anahtar Okuyan Versiyon)

import os
import time
import re
import logging
import tempfile
from google.api_core import exceptions as google_exceptions

# --- Vertex AI Kütüphaneleri ---
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    from google.cloud import storage, secretmanager
    from google.oauth2 import service_account
except ImportError:
    print("⚠️ Gerekli Google Cloud kütüphaneleri bulunamadı.")
    print("   Lütfen 'pip install google-cloud-aiplatform google-cloud-storage google-auth google-cloud-secret-manager' komutunu çalıştırın.")
    exit()

# --- Global Değişkenler ---
PROJECT_ID = "gen-lang-client-0738578499"
LOCATION = "us-central1"
# YENİ: Secret Manager'da saklanacak anahtarın adı
SERVICE_ACCOUNT_SECRET_NAME = "vertex-ai-sa-key" 

model = None
temp_key_path = None # İndirilen anahtarın geçici yolunu tutacak
TEST_MODE = False

# --- YENİ ve GÜVENLİ: Vertex AI Yapılandırma ---

def load_sa_key_from_secret_manager(project_id):
    """Servis hesabı anahtarını Secret Manager'dan indirip geçici bir dosyaya yazar."""
    global temp_key_path
    if temp_key_path and os.path.exists(temp_key_path):
        return temp_key_path
    try:
        logging.info(f"🔄 Servis hesabı anahtarı '{SERVICE_ACCOUNT_SECRET_NAME}' Secret Manager'dan okunuyor...")
        client = secretmanager.SecretManagerServiceClient()
        # ÖNEMLİ: Anahtar, fabrikanın çalıştığı projedeki Secret Manager'da olmalıdır.
        name = f"projects/{project_id}/secrets/{SERVICE_ACCOUNT_SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        key_payload = response.payload.data

        # Anahtarı geçici bir dosyaya yaz
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_file.write(key_payload.decode('utf-8'))
            temp_key_path = temp_file.name
        
        logging.info(f"✅ Servis hesabı anahtarı başarıyla geçici dosyaya yazıldı: {temp_key_path}")
        return temp_key_path
    except Exception as e:
        logging.error(f"❌ Secret Manager'dan servis hesabı anahtarı okunurken hata oluştu: {e}")
        return None

def configure_vertex_ai(worker_project_id):
    """Vertex AI'ı Secret Manager'dan indirilen servis hesabı anahtarı ile başlatır."""
    global model
    if model:
        return True
    
    key_path = load_sa_key_from_secret_manager(worker_project_id)
    if not key_path:
        return False

    try:
        credentials = service_account.Credentials.from_service_account_file(key_path)
        logging.info(f"✅ Kimlik doğrulama, Secret Manager'dan indirilen anahtar ile ayarlandı.")

        logging.info(f"🔄 Vertex AI, '{PROJECT_ID}' projesi için '{LOCATION}' konumunda başlatılıyor...")
        vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)

        generation_config = {"temperature": 0.9, "top_p": 0.95, "top_k": 40, "max_output_tokens": 8192}
        model = GenerativeModel(model_name="gemini-2.5-pro", generation_config=generation_config)
        
        logging.info("✅ Vertex AI başarıyla yapılandırıldı.")
        return True
    except Exception as e:
        logging.error(f"❌ Vertex AI başlatılırken bir hata oluştu: {e}")
        return False

def generate_content_with_vertex(prompt):
    """Vertex AI kullanarak içerik üretir."""
    global model
    if not model:
        logging.error("❌ Model yapılandırılmamış. İçerik üretilemiyor.")
        return None
    try:
        logging.info("🤖 Vertex AI ile içerik üretiliyor...")
        response = model.generate_content(prompt)
        if response and hasattr(response, 'text') and response.text:
            logging.info("✅ Vertex AI'dan başarılı yanıt alındı.")
            return response
        else:
            logging.warning(f"⚠️ Vertex AI'dan boş veya geçersiz yanıt alındı. Yanıt: {response}")
            return None
    except Exception as e:
        logging.error(f"❌ Vertex AI ile içerik üretilirken beklenmedik bir hata oluştu: {e}")
        return None

# --- Mevcut Yardımcı Fonksiyonlar (Mantık Değiştirilmedi) ---
# ... (validate_story_format, fix_missing_sections, YouTubeRevengeStoryGenerator class'ı aynı kalacak) ...
def validate_story_format(formatted_text):
    logging.info("🔍 Hikaye formatı doğrulanıyor...")
    story_pattern = r'STORY:\s*\n(.+?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)'
    story_match = re.search(story_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    engagement_pattern = r'VIEWER ENGAGEMENT:\s*\n(.+?)(?=\n\s*[-]{5,}|\Z)'
    engagement_match = re.search(engagement_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    issues = []
    if not story_match or len(story_match.group(1).strip()) < 100: issues.append("STORY bölümü eksik veya çok kısa.")
    if not engagement_match or len(engagement_match.group(1).strip()) < 20: issues.append("VIEWER ENGAGEMENT bölümü eksik veya çok kısa.")
    if issues: logging.warning("⚠️ Format doğrulama sorunları: %s", " | ".join(issues)); return False
    logging.info("✅ Hikaye formatı doğrulandı."); return True

def fix_missing_sections(formatted_text, story_title, story_content, engagement_prompt):
    logging.info("🔧 Eksik bölümler düzeltiliyor..."); has_story = re.search(r'STORY:\s*\n', formatted_text, re.IGNORECASE); has_engagement = re.search(r'VIEWER ENGAGEMENT:\s*\n', formatted_text, re.IGNORECASE)
    if has_story and has_engagement: return formatted_text
    fixed_parts = [f"Title: {story_title}\n", "STORY:", story_content, "\n\nVIEWER ENGAGEMENT:", engagement_prompt]; fixed_text = "\n".join(fixed_parts); logging.info("✅ Eksik bölümler başarıyla düzeltildi."); return fixed_text

class YouTubeRevengeStoryGenerator:
    def __init__(self):
        self.story_structure = {1: {"name": "Dramatic Opening", "words": 130}, 2: {"name": "Character Intro", "words": 230}, 3: {"name": "Backstory", "words": 570}, 4: {"name": "Betrayal Process", "words": 670}, 5: {"name": "Calm Reaction", "words": 510}, 6: {"name": "Strategic Move", "words": 1100}, 7: {"name": "Natural Justice", "words": 840}, 8: {"name": "Moral Victory", "words": 440}}
    def get_and_update_next_title(self, bucket, source_filename="hikayelerbasligi.txt"):
        try:
            blob = bucket.blob(source_filename);
            if not blob.exists(): return None
            lines = [line.strip() for line in blob.download_as_text(encoding="utf-8").strip().splitlines() if line.strip()]
            if not lines: return None
            title_to_process = lines[0]; blob.upload_from_string("\n".join(lines[1:]), content_type="text/plain; charset=utf-8"); logging.info(f"🔹 '{title_to_process}' başlığı GCS'den alındı."); return title_to_process
        except Exception as e: logging.error(f"❌ GCS'den başlık okunurken hata: {e}"); return None
    def save_current_title(self, title, bucket, target_filename="hikayebasligi.txt"):
        try: blob = bucket.blob(f"islenenler/{target_filename}"); blob.upload_from_string(title, content_type="text/plain; charset=utf-8"); logging.info(f"💾 İşlenen başlık GCS'e kaydedildi.")
        except Exception as e: logging.error(f"❌ Mevcut başlık GCS'e kaydedilirken hata oluştu: {e}")
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
        response = generate_content_with_vertex(prompt); return response.text.strip() if response and hasattr(response, 'text') else None
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
        response = generate_content_with_vertex(prompt); return response.text.strip() if response and hasattr(response, 'text') else None
    def generate_story_from_title(self, story_title, protagonist_profile):
        logging.info(f"🔄 '{story_title}' başlığına göre ULTRA KISALTILMIŞ hikaye (25-29 dk) BÖLÜM BÖLÜM oluşturuluyor...")
        full_story_parts = []; story_so_far = ""
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
            response = generate_content_with_vertex(prompt)
            if response and hasattr(response, 'text'):
                section_text = response.text.strip(); words = section_text.split()
                if len(words) > section_words: logging.warning(f"   ⚠️  Bölüm {i} çok uzun ({len(words)} kelime), {section_words} kelimeye kısaltılıyor..."); section_text = ' '.join(words[:section_words])
                full_story_parts.append(section_text); story_so_far += section_text + "\n\n"; word_count = len(section_text.split()); logging.info(f"   ✅  Bölüm {i} tamamlandı ({word_count} kelime - Hedef: {section_words})."); time.sleep(1)
            else: logging.error(f"   ❌  Bölüm {i} oluşturulamadı! Hikaye üretimi durduruluyor."); return None
        final_story = "\n\n".join(full_story_parts); total_words = len(final_story.split()); estimated_minutes = total_words / 170; logging.info(f"\n✅ ULTRA KISALTILMIŞ hikaye tamamlandı!"); logging.info(f"📊 Toplam kelime: {total_words}"); logging.info(f"⏱️ Tahmini süre: {estimated_minutes:.1f} dakika"); return final_story
    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        content_parts = ["="*60, f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)", "="*60, f"\nTitle: {title}", "Note: All names, companies, and events are completely fictional.\n", "PROTAGONIST PROFILE:", "-"*30, protagonist_profile, "-"*30 + "\n", "STORY:", story if story else "Story content not available.", "\n" + "-"*40 + "\n", "VIEWER ENGAGEMENT:", engagement_prompt if engagement_prompt else "What do you think about this story?"]
        formatted_text = "\n".join(content_parts)
        if not validate_story_format(formatted_text): logging.warning("⚠️ Format doğrulaması başarısız, düzeltiliyor..."); formatted_text = fix_missing_sections(formatted_text, title, story, engagement_prompt)
        logging.info("✅ Hikaye formatı garantili olarak doğrulandı"); return formatted_text

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_story_generation_process(kaynak_bucket_adi, cikti_bucket_adi, worker_project_id):
    logging.info("--- Hikaye Üretim Modülü Başlatıldı (Vertex AI - Güvenli Versiyon) ---")
    if not configure_vertex_ai(worker_project_id):
        raise Exception("Vertex AI başlatılamadı. Servis hesabı anahtarını ve proje ayarlarını kontrol edin.")

    storage_client = storage.Client()
    kaynak_bucket = storage_client.bucket(kaynak_bucket_adi)
    
    generator = YouTubeRevengeStoryGenerator()
    
    story_title = generator.get_and_update_next_title(kaynak_bucket)
    if not story_title:
        return None, None, None, None

    generator.save_current_title(story_title, kaynak_bucket)
    logging.info(f"\n📖 İşlenecek başlık: {story_title}")

    protagonist_profile = generator.generate_protagonist_profile(story_title)
    if not protagonist_profile: 
        raise Exception("Kahraman profili oluşturulamadı!")
    logging.info("✅ Kahraman profili oluşturuldu.")

    story_content = None
    if TEST_MODE:
        story_content = "This is a test story for TEST MODE."
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

    return story_content, story_title, protagonist_profile, formatted_text
