# hikayeuretir.py

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import storage, secretmanager
import os
import time

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
            print("❌ Secret Manager'da API anahtarı bulunamadı.")
            return False
        print(f"🔑 {len(API_KEYS)} API anahtarı Secret Manager'dan başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"❌ Secret Manager'dan anahtar okunurken hata: {e}")
        return False

def configure_gemini():
    """Sıradaki API anahtarı ile Gemini'yi yapılandırır."""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        return None
    try:
        api_key = API_KEYS[current_api_key_index]
        print(f"🔄 API anahtarı {current_api_key_index + 1} deneniyor...")
        genai.configure(api_key=api_key)
        generation_config = {"temperature": 0.9, "top_p": 0.95, "top_k": 40, "max_output_tokens": 6000}
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest", generation_config=generation_config)
        print(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        print(f"❌ API anahtarı {current_api_key_index + 1} ile hata: {e}")
        current_api_key_index += 1
        return configure_gemini()

def generate_with_failover(prompt):
    """API'ye istek gönderir, kota hatasında diğer anahtarı dener."""
    global current_api_key_index, model
    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None: return None
            response = model.generate_content(prompt)
            return response
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            print(f"⚠️ API anahtarı {current_api_key_index + 1} kotaya takıldı. Değiştiriliyor...")
            current_api_key_index += 1
            model = None
        except Exception as e:
            print(f"❌ Beklenmedik API hatası: {e}")
            current_api_key_index += 1
            model = None
    return None

# --- SİZİN ORİJİNAL HİKAYE OLUŞTURUCU SINIFINIZ (GÜNCELLENDİ) ---
class YouTubeRevengeStoryGenerator:
    def __init__(self):
        # Sizin ultra-kısaltılmış, 25-29 dakikalık yapılandırmanız
        self.story_structure = {
            1: {"name": "Dramatic Opening", "words": 140}, 2: {"name": "Character Intro", "words": 240},
            3: {"name": "Backstory", "words": 580}, 4: {"name": "Betrayal Process", "words": 680},
            5: {"name": "Calm Reaction", "words": 520}, 6: {"name": "Strategic Move", "words": 1200},
            7: {"name": "Natural Justice", "words": 850}, 8: {"name": "Moral Victory", "words": 450}
        }

    def get_and_update_next_title(self, bucket, source_filename="hikayelerbasligi.txt"):
        try:
            blob = bucket.blob(source_filename)
            if not blob.exists(): return None
            lines = [line.strip() for line in blob.download_as_text(encoding="utf-8").strip().splitlines() if line.strip()]
            if not lines: return None
            title_to_process = lines[0]
            blob.upload_from_string("\n".join(lines[1:]), content_type="text/plain; charset=utf-8")
            print(f"🔹 '{title_to_process}' başlığı GCS'den alındı.")
            return title_to_process
        except Exception as e:
            print(f"❌ GCS'den başlık okunurken hata: {e}")
            return None
    
    def save_current_title(self, title, bucket, target_filename="hikayebasligi.txt"):
        try:
            blob = bucket.blob(f"islenenler/{target_filename}")
            blob.upload_from_string(title, content_type="text/plain; charset=utf-8")
            print(f"💾 İşlenen başlık GCS'e kaydedildi.")
        except Exception as e:
            print(f"❌ Mevcut başlık GCS'e kaydedilirken hata oluştu: {e}")

    def generate_protagonist_profile(self, story_title):
        prompt = f"""Based on this story title: "{story_title}"... (Sizin Orijinal Prompt'unuz)"""
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_single_engagement_prompt(self, story_title, story_content):
        prompt = f"""Based on this story title: "{story_title}"... (Sizin Orijinal Prompt'unuz)"""
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_opening_section(self, story_title, protagonist_profile):
        prompt = f"""Write ONLY the first section (Dramatic Opening)... (Sizin Orijinal Prompt'unuz)"""
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    # --- YENİ VE GÜÇLENDİRİLMİŞ HİKAYE ÜRETME FONKSİYONU ---
    def generate_story_from_title(self, story_title, protagonist_profile):
        """Hikayeyi bölüm bölüm oluşturur."""
        print(f"🔄 '{story_title}' başlığına göre ULTRA KISALTILMIŞ hikaye (25-29 dk) BÖLÜM BÖLÜM oluşturuluyor...")
        
        full_story_parts = []
        story_so_far = ""

        for i, section_info in self.story_structure.items():
            section_name = section_info["name"]
            section_words = section_info["words"]
            
            print(f"\n  ➡️ Bölüm {i}/{len(self.story_structure)}: '{section_name}' (~{section_words} kelime) oluşturuluyor...")
            
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
- Keep dialogue extremely sharp and impactful.
- Every sentence must advance the story.
- Maintain maximum tension with minimum words.

ABSOLUTE LIMIT: Write MAXIMUM {section_words} words for this section. Count every word carefully."""
            
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                section_text = response.text.strip()
                words = section_text.split()
                if len(words) > section_words:
                    print(f"  ⚠️ Bölüm {i} çok uzun ({len(words)} kelime), {section_words} kelimeye kısaltılıyor...")
                    section_text = ' '.join(words[:section_words])
                
                full_story_parts.append(section_text)
                story_so_far += section_text + "\n\n"
                word_count = len(section_text.split())
                print(f"  ✅ Bölüm {i} tamamlandı ({word_count} kelime - Hedef: {section_words}).")
                time.sleep(3)
            else:
                print(f"  ❌ Bölüm {i} oluşturulamadı! Hikaye üretimi durduruluyor.")
                return None
        
        final_story = "\n\n".join(full_story_parts)
        total_words = len(final_story.split())
        estimated_minutes = total_words / 170
        print(f"\n✅ ULTRA KISALTILMIŞ hikaye tamamlandı!")
        print(f"📊 Toplam kelime: {total_words}")
        print(f"⏱️ Tahmini süre: {estimated_minutes:.1f} dakika")
        return final_story

    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        content_parts = ["="*60, f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)", "="*60,
                         f"\nTitle: {title}", "Note: All names, companies, and events are completely fictional.\n",
                         "PROTAGONIST PROFILE:", "-"*30, protagonist_profile, "-"*30 + "\n"]
        if not is_opening_only:
            content_parts.append("STORY STRUCTURE (ULTRA-OPTIMIZED FOR 25-29 MINUTES):")
            for i, section in self.story_structure.items():
                content_parts.append(f"{i}. {section['name']} (~{section['words']} words)")
        else:
            content_parts.append("SECTION: Dramatic Opening (~140 words)")
        content_parts.extend(["-"*60 + "\n\n", "STORY:", story])
        if engagement_prompt:
            content_parts.extend(["\n\n" + "-"*40 + "\n\n", "VIEWER ENGAGEMENT:", engagement_prompt])
        return "\n".join(content_parts)

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_story_generation_process(kaynak_bucket_adi, cikti_bucket_adi):
    print("--- Hikaye Üretim Modülü Başlatıldı (25-29 Dakika ULTRA-OPTIMIZED) ---")
    if not load_api_keys_from_secret_manager():
        raise Exception("API anahtarları yüklenemedi.")

    storage_client = storage.Client()
    kaynak_bucket = storage_client.bucket(kaynak_bucket_adi)
    
    generator = YouTubeRevengeStoryGenerator()
    
    story_title = generator.get_and_update_next_title(kaynak_bucket)
    if not story_title:
        return None, None, None, None, None

    generator.save_current_title(story_title, kaynak_bucket)
    print(f"\n📖 İşlenecek başlık: {story_title}")

    protagonist_profile = generator.generate_protagonist_profile(story_title)
    if not protagonist_profile: raise Exception("Kahraman profili oluşturulamadı!")
    print("✅ Kahraman profili oluşturuldu.")

    story_content = None
    if TEST_MODE:
        story_content = generator.generate_opening_section(story_title, protagonist_profile)
    else:
        story_content = generator.generate_story_from_title(story_title, protagonist_profile)

    if not story_content: raise Exception("Hikaye içeriği oluşturulamadı!")
    
    engagement_prompt = generator.generate_single_engagement_prompt(story_title, story_content)
    
    formatted_text = generator.format_story_for_saving(
        story_content, story_title, protagonist_profile, engagement_prompt, 
        is_opening_only=TEST_MODE
    )

    if not formatted_text:
        raise Exception("Hikaye metni formatlanamadı.")

    return story_content, story_title, protagonist_profile, API_KEYS, formatted_text
