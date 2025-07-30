# hikayeuretir.py

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import storage, secretmanager
import os

# --- Global Değişkenler (Sizin orijinalinizdeki gibi) ---
API_KEYS = []
current_api_key_index = 0
model = None 
project_id = "videofabrikam"
TEST_MODE = True 

# --- Bulut Uyumlu Yardımcı Fonksiyonlar ---
# Bu fonksiyonlar, yerel dosya işlemleri yerine bulut servislerini kullanır.

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
    """Sıradaki API anahtarı ile Gemini'yi yapılandırır. (Orijinal kodunuz)"""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        print("❌ Tüm API anahtarları denendi ve hiçbiri çalışmadı.")
        return None
    try:
        api_key = API_KEYS[current_api_key_index]
        print(f"🔄 API anahtarı {current_api_key_index + 1}/{len(API_KEYS)} deneniyor...")
        genai.configure(api_key=api_key)
        generation_config = {"temperature": 0.9, "top_p": 0.95, "top_k": 40, "max_output_tokens": 8192}
        model = genai.GenerativeModel(model_name="gemini-2.5-pro", generation_config=generation_config)
        print(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        print(f"❌ API anahtarı {current_api_key_index + 1} ile yapılandırma hatası: {e}")
        current_api_key_index += 1
        return configure_gemini()

def generate_with_failover(prompt):
    """API'ye istek gönderir, kota hatasında diğer anahtarı dener. (Orijinal kodunuz)"""
    global current_api_key_index, model
    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None:
                    return None
            response = model.generate_content(prompt)
            return response
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            print(f"⚠️ API anahtarı {current_api_key_index + 1} kota sınırına ulaştı veya izin reddedildi.")
            current_api_key_index += 1
            model = None
            print("➡️ Bir sonraki API anahtarı denenecek.")
        except Exception as e:
            print(f"❌ Beklenmedik bir API hatası oluştu: {e}")
            current_api_key_index += 1
            model = None
            print("➡️ Bir sonraki API anahtarı denenecek.")
    print("❌ Tüm API anahtarları denendi ancak istek başarılı olamadı.")
    return None

# --- SİZİN ORİJİNAL HİKAYE OLUŞTURUCU SINIFINIZ ---
# Bu sınıfın içindeki mantığa ve prompt'lara dokunulmamıştır.
# Sadece dosya işlemleri GCS kullanacak şekilde güncellenmiştir.
class YouTubeRevengeStoryGenerator:
    def __init__(self):
        self.story_structure = {
            1: {"name": "Dramatic Opening", "words": 180}, 2: {"name": "Character Intro", "words": 320},
            3: {"name": "Backstory", "words": 850}, 4: {"name": "Betrayal Process", "words": 980},
            5: {"name": "Calm Reaction", "words": 720}, 6: {"name": "Strategic Move", "words": 1850},
            7: {"name": "Natural Justice", "words": 1240}, 8: {"name": "Moral Victory", "words": 650}
        }

    def get_and_update_next_title(self, bucket, source_filename="hikayelerbasligi.txt"):
        try:
            blob = bucket.blob(source_filename)
            if not blob.exists():
                print(f"❌ HATA: GCS'de kaynak başlık dosyası '{source_filename}' bulunamadı.")
                return None
            lines = [line.strip() for line in blob.download_as_text(encoding="utf-8").strip().splitlines() if line.strip()]
            if not lines:
                print(f"✅ BİLGİ: '{source_filename}' dosyasında işlenecek başlık kalmadı.")
                return None
            title_to_process = lines[0]
            blob.upload_from_string("\n".join(lines[1:]), content_type="text/plain; charset=utf-8")
            print(f"🔹 '{source_filename}' dosyasından '{title_to_process}' başlığı alındı.")
            return title_to_process
        except Exception as e:
            print(f"❌ GCS'den başlık okunurken hata: {e}")
            return None
    
    def save_current_title(self, title, bucket, target_filename="hikayebasligi.txt"):
        try:
            blob = bucket.blob(f"islenenler/{target_filename}")
            blob.upload_from_string(title, content_type="text/plain; charset=utf-8")
            print(f"💾 İşlenen başlık '{target_filename}' dosyasına GCS'de kaydedildi.")
        except Exception as e:
            print(f"❌ Mevcut başlık GCS'e kaydedilirken hata oluştu: {e}")

    def generate_protagonist_profile(self, story_title):
        prompt = f"""Based on this story title: "{story_title}"

Create a protagonist profile in this EXACT format:

Protagonist: [FICTIONAL First Name Last Name], [age 42-58]
Company: [FICTIONAL Company Name] ([industry type])
Location: [US City]
Crisis: [Brief description of the main crisis/conflict]

Requirements:
- ALL names must be completely FICTIONAL
- The Protagonist must only be an American male
- Choose appropriate industry based on the title
- Age between 42-58
- US location that fits the story
- Crisis should match the title's theme
- Keep it concise - one line each

Example format:
Protagonist: George Chen, 45
Company: TechFlow Systems (software)
Location: Austin
Crisis: Data breach affecting major clients

Write ONLY the 4-line profile, nothing else."""
        try:
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                return response.text.strip()
            return None
        except Exception as e:
            print(f"❌ Profil oluşturma hatası: {str(e)}")
            return None

    def generate_single_engagement_prompt(self, story_title, story_content):
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
        try:
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                return response.text.strip()
            return None
        except Exception as e:
            print(f"❌ Etkileşim mesajı oluşturma hatası: {str(e)}")
            return None

    def generate_opening_section(self, story_title, protagonist_profile):
        prompt = f"""Write ONLY the first section (Dramatic Opening) of a revenge story for storytelling purposes.

STORY TITLE: "{story_title}"

PROTAGONIST PROFILE:
{protagonist_profile}

SECTION 1: DRAMATIC OPENING (~180 words)
- Start with dramatic dialogue or action that hooks the listener
- Use the protagonist's name and company from the profile
- Set the tone for a revenge/justice story
- Create immediate tension or conflict
- Use authentic storytelling style perfect for narration
- Make it compelling and engaging for audio/video content

Requirements:
- Approximately 180 words
- Dramatic dialogue or action
- Hook the audience immediately
- Set up the conflict
- Match the title's theme and protagonist profile
- Use the FICTIONAL names from the profile
- Perfect for storytelling/narration format

Write ONLY this opening section - do not continue with other parts of the story."""
        try:
            print(f"🔄 TEST MODU: '{story_title}' için giriş bölümü oluşturuluyor...")
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                opening = response.text.strip()
                word_count = len(opening.split())
                print(f"✅ Giriş bölümü tamamlandı ({word_count} kelime)")
                return opening
            else:
                print(f"❌ Giriş bölümü oluşturulamadı")
                return None
        except Exception as e:
            print(f"❌ Giriş bölümü oluşturulurken hata: {str(e)}")
            return None

    def generate_story_from_title(self, story_title, protagonist_profile):
        total_words = sum(section["words"] for section in self.story_structure.values())
        prompt = f"""Write a complete revenge story for storytelling purposes.

STORY TITLE: "{story_title}"

PROTAGONIST PROFILE:
{protagonist_profile}

STORY STRUCTURE (MUST FOLLOW EXACTLY):
The story must be written in 8 sections with specific word counts:
1. DRAMATIC OPENING (~180 words)
2. CHARACTER INTRO (~320 words)
3. BACKSTORY (~850 words)
4. BETRAYAL PROCESS (~980 words)
5. CALM REACTION (~720 words)
6. STRATEGIC MOVE (~1850 words)
7. NATURAL JUSTICE (~1240 words)
8. MORAL VICTORY (~650 words)

REQUIREMENTS:
- Total story: approximately {total_words} words
- Use the protagonist profile details consistently
- ALL names and companies FICTIONAL
- Match the title's theme perfectly
- Authentic conversational storytelling style
- Perfect for narration/video content
- Each section should flow naturally into the next

Write the complete story following this exact structure and word counts."""
        try:
            print(f"🔄 '{story_title}' başlığına göre tam hikaye oluşturuluyor...")
            print(f"📊 Hedef: {total_words} kelime, 8 bölüm")
            response = generate_with_failover(prompt)
            if response and hasattr(response, 'text'):
                story = response.text.strip()
                word_count = len(story.split())
                print(f"✅ Hikaye tamamlandı ({word_count} kelime)")
                return story
            else:
                print(f"❌ Hikaye oluşturulamadı")
                return None
        except Exception as e:
            print(f"❌ Hikaye oluşturulurken hata: {str(e)}")
            return None

    def format_story_for_saving(self, story, title, protagonist_profile, engagement_prompt, is_opening_only=False):
        """
        Hikayeyi GCS'e kaydetmek yerine, formatlanmış metin olarak döndürür.
        """
        content_parts = ["="*60, f"YOUTUBE REVENGE STORY ({'OPENING SECTION - ' if is_opening_only else ''}FICTIONAL)", "="*60,
                         f"\nTitle: {title}", "Note: All names, companies, and events are completely fictional.\n",
                         "PROTAGONIST PROFILE:", "-"*30, protagonist_profile, "-"*30 + "\n"]
        if not is_opening_only:
            content_parts.append("STORY STRUCTURE:")
            for i, section in self.story_structure.items():
                content_parts.append(f"{i}. {section['name']} (~{section['words']} words)")
        else:
            content_parts.append("SECTION: Dramatic Opening (~180 words)")
        content_parts.extend(["-"*60 + "\n\n", "STORY:", story])
        if engagement_prompt:
            content_parts.extend(["\n\n" + "-"*40 + "\n\n", "VIEWER ENGAGEMENT:", engagement_prompt])

        return "\n".join(content_parts)

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_story_generation_process(kaynak_bucket_adi, cikti_bucket_adi):
    """Bu ana fonksiyon, main.py tarafından çağrılır ve tüm süreci yönetir."""
    print("--- Hikaye Üretim Modülü Başlatıldı ---")
    if not load_api_keys_from_secret_manager():
        raise Exception("API anahtarları Secret Manager'dan yüklenemedi.")

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
    
    # Hikayeyi GCS'e kaydetmek yerine, formatlanmış metni al
    formatted_text = generator.format_story_for_saving(
        story_content, story_title, protagonist_profile, engagement_prompt, 
        is_opening_only=TEST_MODE
    )

    if not formatted_text:
        raise Exception("Hikaye metni formatlanamadı.")

    # Sonraki modülün kullanması için gerekli tüm bilgileri döndür
    return story_content, story_title, protagonist_profile, API_KEYS, formatted_text
