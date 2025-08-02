# hikayeuretir.py

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import storage, secretmanager
import os
import time
import re

# --- Global Değişkenler ---
API_KEYS = []
current_api_key_index = 0
model = None 
project_id = "videofabrikam"
TEST_MODE = True # Tam hikaye üretimi için bu False olmalıdır

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

# 🆕 YENİ FONKSİYON: Hikaye formatını doğrular
def validate_story_format(formatted_text):
    """Hikayede STORY: ve VIEWER ENGAGEMENT: bölümlerinin varlığını kontrol eder."""
    print("🔍 Hikaye formatı doğrulanıyor...")
    
    # STORY: bölümünü ara
    story_pattern = r'STORY:\s*\n(.+?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)'
    story_match = re.search(story_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    
    # VIEWER ENGAGEMENT: bölümünü ara
    engagement_pattern = r'VIEWER ENGAGEMENT:\s*\n(.+?)(?=\n\s*[-]{5,}|\Z)'
    engagement_match = re.search(engagement_pattern, formatted_text, re.DOTALL | re.IGNORECASE)
    
    issues = []
    
    if not story_match:
        issues.append("❌ STORY: bölümü bulunamadı")
    else:
        story_content = story_match.group(1).strip()
        if len(story_content) < 100:
            issues.append(f"❌ STORY: bölümü çok kısa ({len(story_content)} karakter)")
        else:
            print(f"✅ STORY: bölümü bulundu ({len(story_content)} karakter)")
    
    if not engagement_match:
        issues.append("❌ VIEWER ENGAGEMENT: bölümü bulunamadı")
    else:
        engagement_content = engagement_match.group(1).strip()
        if len(engagement_content) < 20:
            issues.append(f"❌ VIEWER ENGAGEMENT: bölümü çok kısa ({len(engagement_content)} karakter)")
        else:
            print(f"✅ VIEWER ENGAGEMENT: bölümü bulundu ({len(engagement_content)} karakter)")
    
    if issues:
        print("⚠️ Format doğrulama sorunları:")
        for issue in issues:
            print(f"   {issue}")
        return False
    
    print("✅ Hikaye formatı doğrulandı - tüm gerekli bölümler mevcut")
    return True

# 🆕 YENİ FONKSİYON: Eksik bölümleri düzeltir
def fix_missing_sections(formatted_text, story_title, story_content, engagement_prompt):
    """Eksik STORY: ve VIEWER ENGAGEMENT: bölümlerini düzeltir."""
    print("🔧 Eksik bölümler düzeltiliyor...")
    
    # Mevcut formatı kontrol et
    has_story = re.search(r'STORY:\s*\n', formatted_text, re.IGNORECASE)
    has_engagement = re.search(r'VIEWER ENGAGEMENT:\s*\n', formatted_text, re.IGNORECASE)
    
    if has_story and has_engagement:
        return formatted_text
    
    # Yeniden format oluştur
    fixed_parts = [
        "="*60,
        f"YOUTUBE REVENGE STORY - FICTIONAL",
        "="*60,
        f"\nTitle: {story_title}",
        "Note: All names, companies, and events are completely fictional.\n",
        "-"*60 + "\n"
    ]
    
    # STORY: bölümünü ekle
    if not has_story:
        print("🔧 STORY: bölümü ekleniyor...")
        fixed_parts.extend([
            "STORY:",
            story_content if story_content else "Story content not available."
        ])
    else:
        # Mevcut STORY bölümünü koru
        story_match = re.search(r'(STORY:.*?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)', 
                               formatted_text, re.DOTALL | re.IGNORECASE)
        if story_match:
            fixed_parts.append(story_match.group(1))
    
    # VIEWER ENGAGEMENT: bölümünü ekle
    if not has_engagement:
        print("🔧 VIEWER ENGAGEMENT: bölümü ekleniyor...")
        fixed_parts.extend([
            "\n" + "-"*40 + "\n",
            "VIEWER ENGAGEMENT:",
            engagement_prompt if engagement_prompt else "What do you think about this story? Let me know in the comments below!"
        ])
    else:
        # Mevcut VIEWER ENGAGEMENT bölümünü koru
        engagement_match = re.search(r'(VIEWER ENGAGEMENT:.*?)(?=\n\s*[-]{5,}|\Z)', 
                                   formatted_text, re.DOTALL | re.IGNORECASE)
        if engagement_match:
            fixed_parts.extend(["\n" + "-"*40 + "\n", engagement_match.group(1)])
    
    fixed_text = "\n".join(fixed_parts)
    print("✅ Eksik bölümler başarıyla düzeltildi")
    return fixed_text

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
        """🔄 Windows uyumlu versiyondaki ile aynı prompt ve format kullanır."""
        prompt = f"""Based on this story title: "{story_title}"

Create a protagonist profile in this EXACT format:

Protagonist: [FICTIONAL First Name Last Name], [age 32-58]
Company: [FICTIONAL Company Name] ([industry type])
Location: [US City]
Crisis: [Brief description of the main crisis/conflict]

Requirements:
- ALL names must be completely FICTIONAL
- The Protagonist must only be an American male
- Choose appropriate industry based on the title
- Age between 32-58
- US location that fits the story
- Crisis should match the title's theme
- Keep it concise - one line each

Example format:
Protagonist: George Chen, 45
Company: TechFlow Systems (software)
Location: Austin
Crisis: Data breach affecting major clients

Write ONLY the 4-line profile, nothing else."""
        
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_single_engagement_prompt(self, story_title, story_content):
        """🔄 Windows uyumlu versiyondaki ile aynı prompt kullanır."""
        prompt = f"""Based on this story title: "{story_title}" and the story content, create ONE SINGLE engagement prompt for viewers.

Choose ONE of these types:
1. A specific question asking "What would you do?"
2. An invitation to share similar experiences in comments
3. A moral/ethical question about the situation
4. A request for advice/opinions from viewers

Requirements:
- Write ONLY ONE engagement prompt
- Make it specific to this story's theme
- Use casual, conversational tone
- Include 1-2 relevant emojis
- Keep it engaging for video viewers
- Make it feel natural and authentic
- Encourage comments and discussion

Write ONLY ONE prompt that fits this specific story perfectly."""
        
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    def generate_opening_section(self, story_title, protagonist_profile):
        """🔄 Windows uyumlu versiyondaki ile aynı prompt kullanır."""
        prompt = f"""Write ONLY the first section (Dramatic Opening) of a revenge story for storytelling purposes.

STORY TITLE: "{story_title}"

PROTAGONIST PROFILE:
{protagonist_profile}

SECTION 1: DRAMATIC OPENING (~140 words)
- Start with dramatic dialogue or action that hooks the listener
- Use the protagonist's name and company from the profile
- Set the tone for a revenge/justice story
- Create immediate tension or conflict
- Use authentic storytelling style perfect for narration
- Make it compelling and engaging for audio/video content

Requirements:
- Approximately 140 words (VERY CONCISE for optimal pacing)
- Dramatic dialogue or action
- Hook the audience immediately
- Set up the conflict
- Match the title's theme and protagonist profile
- Use the FICTIONAL names from the profile
- Perfect for storytelling/narration format

Write ONLY this opening section - do not continue with other parts of the story."""
        
        response = generate_with_failover(prompt)
        return response.text.strip() if response and hasattr(response, 'text') else None

    # --- YENİ VE GÜÇLENDİRİLMİŞ HİKAYE ÜRETME FONKSİYONU ---
    def generate_story_from_title(self, story_title, protagonist_profile):
        """🎯 25-29 DAKİKA İÇİN ULTRA KISALTILMIŞ HİKAYE OLUŞTURUR."""
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
                
                # 🎯 Kelime sayısını kontrol et ve gerekirse kısalt
                words = section_text.split()
                if len(words) > section_words:
                    print(f"  ⚠️ Bölüm {i} çok uzun ({len(words)} kelime), {section_words} kelimeye kısaltılıyor...")
                    section_text = ' '.join(words[:section_words])
                
                full_story_parts.append(section_text)
                story_so_far += section_text + "\n\n"
                word_count = len(section_text.split())
                print(f"  ✅ Bölüm {i} tamamlandı ({word_count} kelime - Hedef: {section_words}).")
                time.sleep(3)  # Daha hızlı işlem
            else:
                print(f"  ❌ Bölüm {i} oluşturulamadı! Hikaye üretimi durduruluyor.")
                return None
        
        final_story = "\n\n".join(full_story_parts)
        total_words = len(final_story.split())
        estimated_minutes = total_words / 170  # Daha hızlı konuşma hızı varsayımı
        print(f"\n✅ ULTRA KISALTILMIŞ hikaye tamamlandı!")
        print(f"📊 Toplam kelime: {total_words}")
        print(f"⏱️ Tahmini süre: {estimated_minutes:.1f} dakika")
        
        # 🎯 Eğer hala çok uzunsa uyarı ver
        if estimated_minutes > 29:
            print(f"⚠️ UYARI: Hikaye hala {estimated_minutes:.1f} dakika. Daha fazla kısaltma gerekebilir.")
        
        return final_story

    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        """🆕 Garantili format oluşturur - STORY: ve VIEWER ENGAGEMENT: bölümleri kesinlikle dahil edilir."""
        
        content_parts = [
            "="*60,
            f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)",
            "="*60,
            f"\nTitle: {title}",
            "Note: All names, companies, and events are completely fictional.\n",
            "PROTAGONIST PROFILE:",
            "-"*30,
            protagonist_profile,
            "-"*30 + "\n"
        ]
        
        if not is_opening_only:
            content_parts.append("STORY STRUCTURE (ULTRA-OPTIMIZED FOR 25-29 MINUTES):")
            total_target_words = sum(section['words'] for section in self.story_structure.values())
            estimated_minutes = total_target_words / 170
            content_parts.append(f"Target Total: ~{total_target_words} words (~{estimated_minutes:.1f} minutes)")
            for i, section in self.story_structure.items():
                content_parts.append(f"{i}. {section['name']} (~{section['words']} words)")
        else:
            content_parts.append("SECTION: Dramatic Opening (~140 words)")
        
        content_parts.extend([
            "-"*60 + "\n",
            "STORY:",  # 🎯 GARANTİLİ STORY: bölümü
            story if story else "Story content not available."
        ])
        
        # 🎯 GARANTİLİ VIEWER ENGAGEMENT: bölümü
        content_parts.extend([
            "\n" + "-"*40 + "\n",
            "VIEWER ENGAGEMENT:",
            engagement_prompt if engagement_prompt else "What do you think about this story? Have you ever experienced something similar? Let me know in the comments below and don't forget to like and subscribe for more stories!"
        ])
        
        formatted_text = "\n".join(content_parts)
        
        # 🔍 Format doğrulaması yap
        if not validate_story_format(formatted_text):
            print("⚠️ Format doğrulaması başarısız, düzeltiliyor...")
            formatted_text = fix_missing_sections(formatted_text, title, story, engagement_prompt)
        
        return formatted_text

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
        print("✅ Hikaye açılışı oluşturuldu (TEST MODE).")
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

    # 🔍 Son kontrol - format doğrulaması
    if not validate_story_format(formatted_text):
        print("❌ UYARI: Final format doğrulaması başarısız!")
        formatted_text = fix_missing_sections(formatted_text, story_title, story_content, engagement_prompt)
        
        # Tekrar kontrol et
        if not validate_story_format(formatted_text):
            raise Exception("Hikaye formatı düzeltilemedi - STORY: ve VIEWER ENGAGEMENT: bölümleri eksik!")

    print("✅ Hikaye formatı garantili olarak doğrulandı")
    return story_content, story_title, protagonist_profile, API_KEYS, formatted_text
