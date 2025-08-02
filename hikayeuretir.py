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
TEST_MODE = False # Tam hikaye üretimi için bu False olmalıdır

# --- EMOJİ FİLTRELEME FONKSİYONU ---
def remove_emojis(text):
    """Metinden tüm emojileri temizler."""
    if not text:
        return text
    
    # Unicode emoji pattern - tüm emoji karakterlerini yakalar
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
        "\U00002600-\U000026FF"  # miscellaneous symbols
        "\U00002700-\U000027BF"  # dingbats
        "]+", 
        flags=re.UNICODE
    )
    
    # Emojileri temizle
    cleaned_text = emoji_pattern.sub('', text)
    
    # Çoklu boşlukları tek boşluğa çevir
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    # Başındaki ve sonundaki boşlukları temizle
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text

def clean_response_text(text):
    """API yanıtından emojileri temizler ve metni düzenler."""
    if not text:
        return text
    
    # Emojileri temizle
    cleaned = remove_emojis(text)
    
    # Emoji kalıntılarını ve gereksiz karakterleri temizle
    cleaned = re.sub(r'[👇🤯💯🔥⚡️✨🎯💪🚀❤️💔😱😡🤬😤💀☠️⭐️🌟💫⚠️❌✅🔴🟢🔵⚪️⚫️🟡🟠🟣🟤]', '', cleaned)
    
    # Birden fazla noktalama işaretini düzenle
    cleaned = re.sub(r'[!]{2,}', '!', cleaned)
    cleaned = re.sub(r'[?]{2,}', '?', cleaned)
    cleaned = re.sub(r'[.]{3,}', '...', cleaned)
    
    # Çoklu boşlukları düzelt
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()

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
        model = genai.GenerativeModel(model_name="gemini-2.5-pro", generation_config=generation_config)
        print(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        print(f"❌ API anahtarı {current_api_key_index + 1} ile hata: {e}")
        current_api_key_index += 1
        return configure_gemini()

def generate_with_failover(prompt):
    """API'ye istek gönderir, kota hatasında diğer anahtarı dener ve emojileri temizler."""
    global current_api_key_index, model
    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None: return None
            
            # Prompt'a emoji yasağı ekle
            enhanced_prompt = f"""{prompt}

CRITICAL FORMATTING RULE:
- DO NOT use ANY emojis in your response
- DO NOT use symbols like 👇 🤯 💯 🔥 ⚡️ ✨ 🎯 💪 🚀 ❤️ 💔 😱 😡 🤬 😤 💀 ☠️ ⭐️ 🌟 💫 ⚠️ ❌ ✅ 🔴 🟢 🔵 ⚪️ ⚫️ 🟡 🟠 🟣 🟤
- Use only plain text and standard punctuation
- Write in a professional, clean format without visual symbols"""

            response = model.generate_content(enhanced_prompt)
            
            # Yanıtı temizle
            if response and hasattr(response, 'text'):
                cleaned_text = clean_response_text(response.text)
                # Temizlenmiş metni response objesine geri ata
                response._result.candidates[0].content.parts[0].text = cleaned_text
            
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
            clean_response_text(story_content) if story_content else "Story content not available."
        ])
    else:
        # Mevcut STORY bölümünü koru
        story_match = re.search(r'(STORY:.*?)(?=\n\s*[-]{5,}|\n\s*VIEWER ENGAGEMENT:|\Z)', 
                               formatted_text, re.DOTALL | re.IGNORECASE)
        if story_match:
            fixed_parts.append(clean_response_text(story_match.group(1)))
    
    # VIEWER ENGAGEMENT: bölümünü ekle
    if not has_engagement:
        print("🔧 VIEWER ENGAGEMENT: bölümü ekleniyor...")
        fixed_parts.extend([
            "\n" + "-"*40 + "\n",
            "VIEWER ENGAGEMENT:",
            clean_response_text(engagement_prompt) if engagement_prompt else "What do you think about this story? Let me know in the comments below!"
        ])
    else:
        # Mevcut VIEWER ENGAGEMENT bölümünü koru
        engagement_match = re.search(r'(VIEWER ENGAGEMENT:.*?)(?=\n\s*[-]{5,}|\Z)', 
                                   formatted_text, re.DOTALL | re.IGNORECASE)
        if engagement_match:
            fixed_parts.extend(["\n" + "-"*40 + "\n", clean_response_text(engagement_match.group(1))])
    
    fixed_text = "\n".join(fixed_parts)
    print("✅ Eksik bölümler başarıyla düzeltildi")
    return fixed_text

# --- SİZİN ORİJİNAL HİKAYE OLUŞTURUCU SINIFINIZ (GÜNCELLENDİ) ---
class YouTubeRevengeStoryGenerator:
    def __init__(self):
        # 🆕 ARALIK SİSTEMİ İLE GÜNCELLENMİŞ YAPI
        self.story_structure = {
            1: {"name": "Dramatic Opening", "min_words": 120, "max_words": 140}, 
            2: {"name": "Character Intro", "min_words": 220, "max_words": 240},
            3: {"name": "Backstory", "min_words": 500, "max_words": 580}, 
            4: {"name": "Betrayal Process", "min_words": 640, "max_words": 680},
            5: {"name": "Calm Reaction", "min_words": 450, "max_words": 520}, 
            6: {"name": "Strategic Move", "min_words": 1100, "max_words": 1200},
            7: {"name": "Natural Justice", "min_words": 800, "max_words": 850}, 
            8: {"name": "Moral Victory", "min_words": 400, "max_words": 450}
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
- DO NOT use any emojis or symbols

Example format:
Protagonist: George Chen, 45
Company: TechFlow Systems (software)
Location: Austin
Crisis: Data breach affecting major clients

Write ONLY the 4-line profile, nothing else."""
        
        response = generate_with_failover(prompt)
        return clean_response_text(response.text.strip()) if response and hasattr(response, 'text') else None

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
- DO NOT use any emojis or visual symbols
- Keep it engaging for video viewers
- Make it feel natural and authentic
- Encourage comments and discussion
- Use only plain text and standard punctuation

Write ONLY ONE prompt that fits this specific story perfectly."""
        
        response = generate_with_failover(prompt)
        return clean_response_text(response.text.strip()) if response and hasattr(response, 'text') else None

    # 🆕 YENİ FONKSİYON: Kelime aralığında bölüm üretir
    def validate_and_regenerate_section(self, prompt, section_info, max_attempts=3):
        """Bölümü doğru kelime aralığında gelene kadar üretir."""
        min_words = section_info["min_words"]
        max_words = section_info["max_words"]
        section_name = section_info["name"]
        
        for attempt in range(max_attempts):
            print(f"    🔄 {section_name} deneme {attempt + 1}/{max_attempts} ({min_words}-{max_words} kelime hedefi)")
            
            # Prompt'a aralık bilgisi ekle
            enhanced_prompt = f"""{prompt}

CRITICAL WORD COUNT REQUIREMENT:
- Write between {min_words} and {max_words} words
- This is attempt {attempt + 1} of {max_attempts}
- Count your words carefully before responding
- Stay within the word range for optimal pacing"""

            response = generate_with_failover(enhanced_prompt)
            
            if response and hasattr(response, 'text'):
                section_text = clean_response_text(response.text.strip())
                word_count = len(section_text.split())
                
                if min_words <= word_count <= max_words:
                    print(f"    ✅ {section_name} başarılı! ({word_count} kelime)")
                    return section_text
                else:
                    print(f"    ⚠️ {section_name} aralık dışı: {word_count} kelime (hedef: {min_words}-{max_words})")
                    
                    if attempt == max_attempts - 1:  # Son deneme
                        if word_count > max_words:
                            # Fazlayı kes
                            section_text = ' '.join(section_text.split()[:max_words])
                            print(f"    🔧 Son deneme - {max_words} kelimeye kısaltıldı")
                            return section_text
                        else:
                            # Az bile olsa kabul et
                            print(f"    🔧 Son deneme - {word_count} kelime ile kabul edildi")
                            return section_text
                    
                    time.sleep(2)  # Kısa bekleme
            else:
                print(f"    ❌ {section_name} API yanıtı alınamadı")
                if attempt == max_attempts - 1:
                    return None
                time.sleep(3)
        
        return None

    def generate_opening_section(self, story_title, protagonist_profile):
        """🔄 Aralık sistemi ile açılış bölümü üretir."""
        prompt = f"""Write ONLY the first section (Dramatic Opening) of a revenge story for storytelling purposes.

STORY TITLE: "{story_title}"

PROTAGONIST PROFILE:
{protagonist_profile}

SECTION 1: DRAMATIC OPENING
- Start with dramatic dialogue or action that hooks the listener
- Use the protagonist's name and company from the profile
- Set the tone for a revenge/justice story
- Create immediate tension or conflict
- Use authentic storytelling style perfect for narration
- Make it compelling and engaging for audio/video content
- DO NOT use any emojis or visual symbols

Requirements:
- Hook the audience immediately
- Set up the conflict
- Match the title's theme and protagonist profile
- Use the FICTIONAL names from the profile
- Perfect for storytelling/narration format
- Use only plain text and standard punctuation

Write ONLY this opening section - do not continue with other parts of the story."""
        
        # Açılış için aralık bilgisi
        section_info = self.story_structure[1]  # Dramatic Opening
        
        return self.validate_and_regenerate_section(prompt, section_info)

    # --- YENİ VE GÜÇLENDİRİLMİŞ HİKAYE ÜRETME FONKSİYONU ---
    def generate_story_from_title(self, story_title, protagonist_profile):
        """🎯 ARALIK SİSTEMİ İLE 25-29 DAKİKA İÇİN HİKAYE OLUŞTURUR."""
        print(f"🔄 '{story_title}' başlığına göre ARALIK SİSTEMİ ile hikaye (25-29 dk) BÖLÜM BÖLÜM oluşturuluyor...")
        
        full_story_parts = []
        story_so_far = ""

        for i, section_info in self.story_structure.items():
            section_name = section_info["name"]
            min_words = section_info["min_words"]
            max_words = section_info["max_words"]
            
            print(f"\n  ➡️ Bölüm {i}/{len(self.story_structure)}: '{section_name}' ({min_words}-{max_words} kelime) oluşturuluyor...")
            
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

ULTRA-CRITICAL REQUIREMENTS:
- Write ONLY the content for this specific section.
- DO NOT write section titles like "Section 1: Dramatic Opening".
- Ensure your writing flows naturally from the "STORY SO FAR".
- Maintain a consistent, engaging, and narrative tone perfect for audio.
- Use the protagonist's details from the profile.
- Focus ONLY on essential plot points - eliminate ALL fluff.
- Keep dialogue extremely sharp and impactful.
- Every sentence must advance the story.
- Maintain maximum tension with minimum words.
- DO NOT use any emojis or visual symbols
- Use only plain text and standard punctuation"""
            
            section_text = self.validate_and_regenerate_section(prompt, section_info)
            
            if section_text:
                full_story_parts.append(section_text)
                story_so_far += section_text + "\n\n"
                word_count = len(section_text.split())
                print(f"  ✅ Bölüm {i} tamamlandı ({word_count} kelime - Hedef: {min_words}-{max_words}).")
                time.sleep(3)  # API rate limiting
            else:
                print(f"  ❌ Bölüm {i} oluşturulamadı! Hikaye üretimi durduruluyor.")
                return None
        
        final_story = "\n\n".join(full_story_parts)
        total_words = len(final_story.split())
        estimated_minutes = total_words / 170  # Daha hızlı konuşma hızı varsayımı
        
        # Hedef aralık hesapla
        min_target = sum(section["min_words"] for section in self.story_structure.values())
        max_target = sum(section["max_words"] for section in self.story_structure.values())
        
        print(f"\n✅ ARALIK SİSTEMİ ile hikaye tamamlandı!")
        print(f"📊 Toplam kelime: {total_words} (Hedef: {min_target}-{max_target})")
        print(f"⏱️ Tahmini süre: {estimated_minutes:.1f} dakika")
        
        # 🎯 Aralık kontrolü
        if min_target <= total_words <= max_target:
            print("✅ Hikaye hedef aralıkta!")
        elif total_words < min_target:
            print(f"⚠️ Hikaye hedeften kısa ({min_target - total_words} kelime eksik)")
        else:
            print(f"⚠️ Hikaye hedeften uzun ({total_words - max_target} kelime fazla)")
        
        return final_story

    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        """🆕 Garantili format oluşturur - STORY: ve VIEWER ENGAGEMENT: bölümleri kesinlikle dahil edilir."""
        
        # Tüm içerikleri temizle
        cleaned_story = clean_response_text(story) if story else "Story content not available."
        cleaned_title = clean_response_text(title) if title else "Title not available"
        cleaned_profile = clean_response_text(protagonist_profile) if protagonist_profile else "Profile not available"
        cleaned_engagement = clean_response_text(engagement_prompt) if engagement_prompt else "What do you think about this story? Have you ever experienced something similar? Let me know in the comments below and don't forget to like and subscribe for more stories!"
        
        content_parts = [
            "="*60,
            f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)",
            "="*60,
            f"\nTitle: {cleaned_title}",
            "Note: All names, companies, and events are completely fictional.\n",
            "PROTAGONIST PROFILE:",
            "-"*30,
            cleaned_profile,
            "-"*30 + "\n"
        ]
        
        if not is_opening_only:
            content_parts.append("STORY STRUCTURE (WORD RANGE SYSTEM FOR 25-29 MINUTES):")
            min_total = sum(section['min_words'] for section in self.story_structure.values())
            max_total = sum(section['max_words'] for section in self.story_structure.values())
            estimated_min_minutes = min_total / 170
            estimated_max_minutes = max_total / 170
            content_parts.append(f"Target Range: {min_total}-{max_total} words (~{estimated_min_minutes:.1f}-{estimated_max_minutes:.1f} minutes)")
            for i, section in self.story_structure.items():
                content_parts.append(f"{i}. {section['name']} ({section['min_words']}-{section['max_words']} words)")
        else:
            section_1 = self.story_structure[1]
            content_parts.append(f"SECTION: Dramatic Opening ({section_1['min_words']}-{section_1['max_words']} words)")
        
        content_parts.extend([
            "-"*60 + "\n",
            "STORY:",  # 🎯 GARANTİLİ STORY: bölümü
            cleaned_story
        ])
        
        # 🎯 GARANTİLİ VIEWER ENGAGEMENT: bölümü
        content_parts.extend([
            "\n" + "-"*40 + "\n",
            "VIEWER ENGAGEMENT:",
            cleaned_engagement
        ])
        
        formatted_text = "\n".join(content_parts)
        
        # 🔍 Format doğrulaması yap
        if not validate_story_format(formatted_text):
            print("⚠️ Format doğrulaması başarısız, düzeltiliyor...")
            formatted_text = fix_missing_sections(formatted_text, cleaned_title, cleaned_story, cleaned_engagement)
        
        return formatted_text

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_story_generation_process(kaynak_bucket_adi, cikti_bucket_adi):
    print("--- Hikaye Üretim Modülü Başlatıldı (ARALIK SİSTEMİ - 25-29 Dakika) ---")
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

    
    # Protagonist profili oluştur
    print("\n🎭 Protagonist profili oluşturuluyor...")
    protagonist_profile = generator.generate_protagonist_profile(story_title)
    if not protagonist_profile:
        print("❌ Protagonist profili oluşturulamadı!")
        return None, None, None, None, None
    print(f"✅ Protagonist profili oluşturuldu:\n{protagonist_profile}")

    # TEST_MODE kontrolü
    if TEST_MODE:
        print(f"\n🧪 TEST MODU AKTIF - Sadece açılış bölümü ({generator.story_structure[1]['min_words']}-{generator.story_structure[1]['max_words']} kelime) oluşturuluyor...")
        story_content = generator.generate_opening_section(story_title, protagonist_profile)
        is_opening_only = True
    else:
        print(f"\n📝 TAM HİKAYE MODU - Tüm 8 bölüm oluşturuluyor...")
        story_content = generator.generate_story_from_title(story_title, protagonist_profile)
        is_opening_only = False

    if not story_content:
        print("❌ Hikaye içeriği oluşturulamadı!")
        return None, None, None, None, None

    # Engagement prompt oluştur
    print("\n💬 Viewer engagement prompt oluşturuluyor...")
    engagement_prompt = generator.generate_single_engagement_prompt(story_title, story_content)
    if not engagement_prompt:
        print("⚠️ Engagement prompt oluşturulamadı, varsayılan kullanılıyor...")
        engagement_prompt = "What do you think about this story? Have you ever experienced something similar? Let me know in the comments below!"

    # Final format oluştur
    print("\n📄 Hikaye formatlanıyor...")
    formatted_story = generator.format_story_for_saving(
        story_content, story_title, protagonist_profile, engagement_prompt, is_opening_only
    )

    # Kelime sayısı istatistikleri
    total_words = len(story_content.split()) if story_content else 0
    estimated_minutes = total_words / 170
    
    print(f"\n📊 HİKAYE İSTATİSTİKLERİ:")
    print(f"   📝 Toplam kelime: {total_words}")
    print(f"   ⏱️ Tahmini süre: {estimated_minutes:.1f} dakika")
    
    if not is_opening_only:
        min_target = sum(section['min_words'] for section in generator.story_structure.values())
        max_target = sum(section['max_words'] for section in generator.story_structure.values())
        print(f"   🎯 Hedef aralık: {min_target}-{max_target} kelime")
        
        if min_target <= total_words <= max_target:
            print("   ✅ Hikaye hedef aralıkta!")
        elif total_words < min_target:
            print(f"   ⚠️ Hedeften {min_target - total_words} kelime kısa")
        else:
            print(f"   ⚠️ Hedeften {total_words - max_target} kelime uzun")
    else:
        section_1 = generator.story_structure[1]
        print(f"   🎯 Hedef aralık: {section_1['min_words']}-{section_1['max_words']} kelime")
        
        if section_1['min_words'] <= total_words <= section_1['max_words']:
            print("   ✅ Açılış bölümü hedef aralıkta!")
        elif total_words < section_1['min_words']:
            print(f"   ⚠️ Hedeften {section_1['min_words'] - total_words} kelime kısa")
        else:
            print(f"   ⚠️ Hedeften {total_words - section_1['max_words']} kelime uzun")

    # GCS'e kaydet
    try:
        cikti_bucket = storage_client.bucket(cikti_bucket_adi)
        
        # Dosya adını oluştur
        safe_title = re.sub(r'[^\w\s-]', '', story_title).strip()
        safe_title = re.sub(r'[-\s]+', '-', safe_title)[:50]
        
        mode_suffix = "TEST-OPENING" if TEST_MODE else "FULL-STORY"
        filename = f"revenge-story-{mode_suffix}-{safe_title}-{int(time.time())}.txt"
        
        blob = cikti_bucket.blob(filename)
        blob.upload_from_string(formatted_story, content_type="text/plain; charset=utf-8")
        
        print(f"\n💾 Hikaye GCS'e kaydedildi: gs://{cikti_bucket_adi}/{filename}")
        print(f"📁 Dosya boyutu: {len(formatted_story.encode('utf-8'))} bytes")
        
        return story_title, protagonist_profile, story_content, engagement_prompt, filename
        
    except Exception as e:
        print(f"❌ GCS'e kaydetme hatası: {e}")
        return story_title, protagonist_profile, story_content, engagement_prompt, None

# --- CLOUD FUNCTION ENTRY POINT ---
def hikaye_uret(request):
    """Cloud Function entry point - HTTP tetikleyicisi."""
    try:
        # Bucket adlarını environment variables'dan al
        kaynak_bucket = os.environ.get('KAYNAK_BUCKET', 'videofabrikam-hikaye-basliklari')
        cikti_bucket = os.environ.get('CIKTI_BUCKET', 'videofabrikam-hikayeler')
        
        print(f"🚀 Cloud Function başlatıldı")
        print(f"📂 Kaynak bucket: {kaynak_bucket}")
        print(f"📂 Çıktı bucket: {cikti_bucket}")
        print(f"🧪 Test modu: {'AÇIK' if TEST_MODE else 'KAPALI'}")
        
        # Ana işlemi çalıştır
        title, profile, content, engagement, filename = run_story_generation_process(
            kaynak_bucket, cikti_bucket
        )
        
        if not title:
            return {
                'success': False,
                'message': 'İşlenecek başlık bulunamadı veya hikaye oluşturulamadı',
                'error': 'NO_TITLE_OR_GENERATION_FAILED'
            }, 404
        
        # Başarı yanıtı
        word_count = len(content.split()) if content else 0
        estimated_minutes = word_count / 170
        
        response_data = {
            'success': True,
            'message': f'Hikaye başarıyla oluşturuldu {"(TEST - Sadece açılış)" if TEST_MODE else "(TAM HİKAYE)"}',
            'data': {
                'title': title,
                'filename': filename,
                'word_count': word_count,
                'estimated_minutes': round(estimated_minutes, 1),
                'mode': 'TEST_OPENING' if TEST_MODE else 'FULL_STORY',
                'bucket': cikti_bucket,
                'protagonist_profile': profile[:200] + '...' if len(profile) > 200 else profile,
                'engagement_preview': engagement[:100] + '...' if len(engagement) > 100 else engagement
            }
        }
        
        print(f"✅ İşlem başarıyla tamamlandı!")
        return response_data, 200
        
    except Exception as e:
        print(f"❌ Cloud Function hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'success': False,
            'message': f'Hikaye üretimi sırasında hata oluştu: {str(e)}',
            'error': 'GENERATION_ERROR'
        }, 500

# --- LOKAL TEST FONKSİYONU ---
def test_locally():
    """Lokal test için fonksiyon."""
    print("🧪 LOKAL TEST BAŞLATIYOR...")
    
    # Test için bucket adları
    kaynak_bucket = 'videofabrikam-hikaye-basliklari'
    cikti_bucket = 'videofabrikam-hikayeler'
    
    try:
        result = run_story_generation_process(kaynak_bucket, cikti_bucket)
        
        if result[0]:  # title varsa
            print("\n🎉 LOKAL TEST BAŞARILI!")
            print(f"📖 Başlık: {result[0]}")
            print(f"📄 Dosya: {result[4]}")
        else:
            print("\n❌ LOKAL TEST BAŞARISIZ!")
            
    except Exception as e:
        print(f"\n💥 LOKAL TEST HATASI: {e}")
        import traceback
        traceback.print_exc()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    test_locally()
