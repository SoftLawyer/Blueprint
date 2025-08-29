# icerik_uretici_local_v3.py (Secret Manager Entegrasyonlu)

from __future__ import annotations
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.cloud import secretmanager
import os
import time
import re
import random
import logging
import sys

# --- Logging Ayarları ---
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(asctime)s | %(message)s", stream=sys.stderr, datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# --- Global Ayarlar ---
API_KEYS = []
current_api_key_index = 0
model = None

# --- YENİ: Secret Manager Entegrasyon Fonksiyonları ---
def load_api_keys_from_secret_manager(project_id: str) -> bool:
    """API anahtarlarını Secret Manager'dan yükler."""
    global API_KEYS
    if API_KEYS: return True
    try:
        logger.info("🔄 Gemini API anahtarları Secret Manager'dan okunuyor...")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/gemini-api-anahtarlari/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        API_KEYS = [line.strip() for line in payload.splitlines() if line.strip()]
        if not API_KEYS:
            logger.error("❌ Secret Manager'da 'gemini-api-anahtarlari' secret'ı içinde API anahtarı bulunamadı.")
            return False
        logger.info(f"🔑 {len(API_KEYS)} Gemini API anahtarı başarıyla yüklendi.")
        return True
    except google_exceptions.NotFound:
        logger.error(f"❌ Secret Manager'da 'gemini-api-anahtarlari' secret'ı bulunamadı (Proje: {project_id}).")
        return False
    except Exception as e:
        logger.error(f"❌ Secret Manager'dan anahtar okunurken kritik hata oluştu: {e}")
        return False

def configure_gemini():
    """Sıradaki API anahtarı ile Gemini modelini yapılandırır."""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        logger.error("❌ Kullanılabilir API anahtarı kalmadı.")
        return None
    try:
        api_key = API_KEYS[current_api_key_index]
        logger.info(f"🔄 API anahtarı {current_api_key_index + 1} deneniyor...")
        genai.configure(api_key=api_key)
        generation_config = {
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048
        }
        model = genai.GenerativeModel(
            model_name="gemini-2.5-pro",
            generation_config=generation_config
        )
        logger.info(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        logger.error(f"❌ API anahtarı {current_api_key_index + 1} ile hata: {e}")
        current_api_key_index += 1
        return configure_gemini()

def generate_with_failover(prompt):
    """API'ye istek gönderir ve kota hatasında diğer anahtarı dener."""
    global current_api_key_index, model
    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None: return None
            response = model.generate_content(prompt)
            return response
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            logger.warning(f"⚠️ API anahtarı {current_api_key_index + 1} kotaya takıldı veya izin sorunu. Değiştiriliyor...")
            current_api_key_index += 1
            model = None
        except Exception as e:
            logger.error(f"❌ Beklenmedik API hatası: {e}")
            current_api_key_index += 1
            model = None
    return None

# --- "The Creator's Blueprint" İçerik Üretici Sınıfı ---

class CreatorsBlueprintGenerator:
    """
    "The Creator's Blueprint" kanalı için, zamansız finansal prensipleri
    açıklayan 8-12 dakikalık video metinleri üretir.
    Bu versiyon çeşitli hook türleri kullanır ve güçlü hook validasyonu yapar.
    """
    def __init__(self):
        # 5 farklı hook türü
        self.hook_types = [
            {
                "name": "The Shocking Reality Check",
                "description": "Start with a surprising industry statistic or harsh truth",
                "example": "'95% of creative professionals undercharge by at least 40%. If that number doesn't shock you, you're probably one of them.'"
            },
            {
                "name": "The Universal Pain Point",
                "description": "Address the shared struggle all creatives face",
                "example": "'That sinking feeling when you send an invoice and immediately wonder if you charged too much? Every creative knows that feeling.'"
            },
            {
                "name": "The Costly Belief",
                "description": "Reveal how a common belief is secretly expensive",
                "example": "'The most expensive thing in your creative business isn't your equipment—it's the belief that good work sells itself.'"
            },
            {
                "name": "The Time Bomb",
                "description": "Show what happens if they don't act soon",
                "example": "'Every month you delay learning to price properly costs you thousands. By year's end, that hesitation becomes a five-figure mistake.'"
            },
            {
                "name": "The Hidden Truth",
                "description": "Reveal something the industry doesn't want them to know",
                "example": "'Here's what successful creatives won't tell you: They don't just make great work—they think like businesses first, artists second.'"
            }
        ]
        
        self.script_structure = {
            1: {"name": "The Hook", "words": 100, "task": "Generate a powerful hook using one of the 5 proven hook types. Create immediate emotional tension and curiosity."},
            2: {"name": "The Core Problem", "words": 300, "task": "Explain the psychological conflict creatives face, like the separation of art and commerce. Describe how this mindset leads to undervaluing their work. **End with a compelling transition question that smoothly leads into the next section, 'The Timeless Principle'.**"},
            3: {"name": "The Timeless Principle", "words": 450, "task": "Introduce a single, powerful, evergreen financial or business principle (e.g., Value Exchange). Explain why it's crucial for a sustainable creative career. **End with a transition that introduces the upcoming 'Creative Analogy', like 'To make this principle tangible, let's use an analogy from a world we all understand...'**"},
            4: {"name": "The Creative Analogy", "words": 250, "task": "Explain the timeless principle using a powerful analogy from the creative world. Compare a financial practice to a fundamental part of the creative process. **End your analogy with a transition question that prompts the viewer to think about the internal change required, leading into 'The Mindset Shift'.**"},
            5: {"name": "The Mindset Shift", "words": 250, "task": "Describe the internal shift the viewer needs to make. Reframe their identity from a passive 'artist' to a proactive 'creative professional'. **End this section by summarizing the shift and creating a smooth transition into the final summary of the entire video, 'The Blueprint Summary & CTA'.**"},
            6: {"name": "The Blueprint Summary & CTA", "words": 150, "task": "Provide a concise summary of the video's core message and the new mindset. End with a specific call to action: ask a question for the comments and invite them to subscribe to continue building their blueprint."}
        }
        self.total_target_words = sum(section['words'] for section in self.script_structure.values())

    def get_random_hook_type(self):
        """Rastgele bir hook türü seçer"""
        return random.choice(self.hook_types)

    def validate_hook_power(self, hook_text):
        """Hook'un gücünü değerlendirir - 5 farklı hook türü için optimize edilmiş"""
        power_indicators = [
            # Sayısal veriler - AĞIRLIKLI
            r'\d+%',  # Yüzde (90%)
            r'\$[\d,]+',  # Para miktarı
            r'\d+[kK]',  # Binlik sayılar (10k, 20K)
            r'\d+\s*(year|month|day|week|dollar|thousand)',  # Zaman/para referansı
            
            # Güçlü kelimeler - Gerçek/Sır
            r'(truth|reality|fact|secret|hide|hidden|myth)',  # Gerçek/sır kelimeleri
            
            # Güçlü kelimeler - Problem/Çözüm
            r'(struggle|problem|mistake|wrong|fail|cost)',  # Problem kelimeleri
            r'(success|thrive|master|solution|transform)',  # Çözüm kelimeleri
            
            # Duyusal/Duygusal dil
            r'(feel|imagine|wonder|realize|discover)',  # Duyusal dil
            r'(stop|start|ready|time to|let\'s)',  # Eylem çağrısı
            
            # Evrensellik belirteçleri
            r'(everyone|every|all|most|many)',  # Genelleme
            r'(artist|creative|professional)',  # Hedef kitle
            
            # Merak uyandırma
            r'(why|how|what|here\'s|I\'ll show)',  # Merak gap
            r'(this|today|now)',  # Şimdiki zaman vurgusu
            
            # Negatif duygular (güçlü motivasyon)
            r'(accept|chip away|left on the table|delay)',  # Kayıp/erteleme
        ]
        
        score = 0
        for pattern in power_indicators:
            matches = len(re.findall(pattern, hook_text, re.IGNORECASE))
            if matches > 0:
                if pattern in power_indicators[:4]:
                    score += matches * 2
                else:
                    score += matches
        
        bonus_score = 0
        
        strong_openings = ['every day', 'stop', 'the most expensive', 'here\'s the truth', 'delay', 'accept', 'chip away', 'left on the table']
        for opening in strong_openings:
            if opening.lower() in hook_text.lower():
                bonus_score += 2
                break
        
        promises = ['let\'s', 'I\'ll show', 'this video', 'we\'ll', 'together']
        for promise in promises:
            if promise.lower() in hook_text.lower():
                bonus_score += 1
                break
        
        if re.search(r'\$\d{2,3},\d{3}', hook_text):
            bonus_score += 3
        
        time_pressure = ['delay', 'another year', 'every day', 'by year\'s end']
        for pressure in time_pressure:
            if pressure.lower() in hook_text.lower():
                bonus_score += 2
                break
        
        total_score = score + bonus_score
        
        hook_power = "🔥 KILLER" if total_score >= 12 else "⚡ STRONG" if total_score >= 8 else "💪 DECENT" if total_score >= 5 else "⚠️ WEAK"
        logger.info(f"  📊 Hook Power Analysis: {hook_power} (Score: {total_score}/20+)")
        logger.info(f"      Base indicators: {score}, Bonus points: {bonus_score}")
        
        if total_score < 8:
            logger.warning(f"  🔄 Hook power below threshold ({total_score}/20+). Regenerating...")
            return False
        
        return True

    def generate_killer_hook(self, video_title, max_attempts=3):
        """Güçlü bir hook üretir, gerekirse birkaç deneme yapar"""
        hook_text = ""
        for attempt in range(max_attempts):
            logger.info(f"  🎯 Hook generation attempt {attempt + 1}/{max_attempts}")
            
            selected_hook = self.get_random_hook_type()
            logger.info(f"  🎲 Selected Hook Type: {selected_hook['name']}")
            
            prompt = f"""
You are an expert financial educator for a YouTube channel called 'The Creator's Blueprint'.
Your host persona is "Leo", a calm, empathetic, and knowledgeable guide.
Your target audience is American creative professionals. The tone is like a wise mentor, not a corporate guru.

VIDEO TITLE: "{video_title}"

HOOK TYPE TO USE: {selected_hook['name']}
HOOK DESCRIPTION: {selected_hook['description']}
EXAMPLE STYLE: {selected_hook['example']}

Your task is to write a KILLER HOOK using the selected hook type that makes it IMPOSSIBLE for viewers to click away.

REQUIREMENTS FOR MAXIMUM HOOK POWER (Target: 12+ points):
- Include SPECIFIC numbers, percentages, or dollar amounts (e.g., "$10,000-$20,000", "95%", "5-figure")
- Use powerful action words like "delay", "accept", "chip away", "left on the table"
- Create immediate time pressure or urgency
- Address universal creative professional pain points
- Use concrete, tangible language (avoid abstract concepts)
- End with a promise or transition that hooks into the next section
- Start with high-impact words like "Every day", "Stop", "Here's the truth"
- Make every word count - no fluff, pure impact
- Keep it under 100 words but pack maximum punch

POWER WORDS TO INCLUDE:
- Numbers: "$10,000+", "95%", "every month", "by year's end"
- Action: "delay", "accept", "stop", "chip away"
- Consequences: "left on the table", "costs you", "mistake"
- Promise: "let's", "together", "I'll show you"

IMPORTANT: Do NOT use Leo's personal story. Focus on universal truths and shared experiences.

Write ONLY the hook text (no titles, no explanations). Make it KILLER:
"""
            
            response = generate_with_failover(prompt)
            
            if response and response.parts:
                hook_text = response.text.strip()
                if self.validate_hook_power(hook_text):
                    logger.info(f"  ✅ KILLER hook generated on attempt {attempt + 1}!")
                    return hook_text
                else:
                    logger.warning(f"  ⚠️ Hook attempt {attempt + 1} didn't meet power threshold, trying again...")
                    time.sleep(1)
            else:
                logger.error(f"  ❌ Hook attempt {attempt + 1} failed to generate")
        
        logger.warning(f"  ⚠️ Using best available hook after {max_attempts} attempts")
        return hook_text if hook_text else None

    def get_and_update_next_title(self, source_filename="creator_blueprint_titles.txt"):
        """Yerel başlık listesinden sıradaki başlığı alır ve listeyi günceller."""
        try:
            # Docker içindeki çalışma dizini /app olduğu için doğrudan dosya adını kullanabiliriz.
            file_path = os.path.join("/app", source_filename)
            if not os.path.exists(file_path):
                 logger.error(f"❌ HATA: Başlık dosyası bulunamadı: {file_path}")
                 return None
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            if not lines:
                logger.info("✅ Başlık listesi tamamlandı.")
                return None
            title_to_process = lines[0]
            remaining_titles = lines[1:]
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(remaining_titles))
            logger.info(f"🔹 '{title_to_process}' başlığı yerel dosyadan alındı. Kalan başlık sayısı: {len(remaining_titles)}")
            return title_to_process
        except Exception as e:
            logger.error(f"❌ Yerel başlık dosyasını okurken/yazarken hata: {e}")
            return None

    def generate_script_by_section(self, video_title):
        """
        Verilen başlığa göre, belirlenen yapıya uygun olarak bölüm bölüm video metni üretir.
        Hook bölümü için özel killer hook üretimi yapar.
        """
        logger.info(f"\nSCRIPT GENERATION STARTED FOR: '{video_title}'")
        logger.info(f"Targeting {len(self.script_structure)} sections, ~{self.total_target_words} words, for an 8-12 minute video.")

        full_script_parts = []
        script_so_far = ""

        for i, section_info in self.script_structure.items():
            section_name = section_info["name"]
            section_words = section_info["words"]
            section_task = section_info["task"]
            
            logger.info(f"\n  ➡️  Generating Part {i}/{len(self.script_structure)}: '{section_name}' (~{section_words} words)...")

            if section_name == "The Hook":
                section_text = self.generate_killer_hook(video_title)
                if not section_text:
                    logger.critical(f"  ❌  Hook generation completely failed! Aborting script generation.")
                    return None
            else:
                prompt = f"""
You are an expert financial educator for a YouTube channel called 'The Creator's Blueprint'.
Your host persona is "Leo", a calm, empathetic, and knowledgeable guide.
Your target audience is American creative professionals. The tone is like a wise mentor, not a corporate guru.

VIDEO TITLE: "{video_title}"

SCRIPT SO FAR (For context. Do NOT repeat this content):
---
{script_so_far if script_so_far else "This is the very first part of the script."}
---

Your task is to write ONLY the text for the next single section of the script.

NEXT SECTION TO WRITE:
- Section Name: "{section_name}"
- Section Goal: "{section_task}"
- Target Word Count: Approximately {section_words} words.

ULTRA-CRITICAL INSTRUCTIONS:
1.  **WRITE ONLY THE TEXT FOR THIS SECTION.** Do NOT write a title for the section (e.g., "The Hook").
2.  **FOCUS ONLY ON THE SECTION GOAL:** Fulfill the task described in "{section_task}" and nothing else.
3.  **DO NOT ADD YOUR OWN HOOK, SUMMARY, OR CTA.** Only write a summary and CTA if the section name is EXACTLY "The Blueprint Summary & CTA".
4.  **DO NOT REPEAT** any ideas or analogies already present in the "SCRIPT SO FAR".
5.  If the section name is "The Core Problem", you **MUST** start your response with the mandatory disclaimer: "Before we dive in, I want to be crystal clear: I'm a financial educator, not a licensed financial advisor. The ideas we talk about here are for educational purposes—to help you build awareness and ask better questions. This isn't personalized financial advice, so please always consult with a qualified professional for your unique situation. Okay, let's get into it."
6.  Ensure your writing flows naturally from the "SCRIPT SO FAR" as a direct continuation.

Your entire response must be ONLY the text for the "{section_name}" section. Begin writing now:
"""
                
                response = generate_with_failover(prompt)
                
                section_text = None
                try:
                    if response and response.parts:
                        section_text = response.text.strip()
                    else:
                        finish_reason = "UNKNOWN"
                        if response and hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                            finish_reason = response.candidates[0].finish_reason.name
                        logger.error(f"  ❌  Part {i} generation blocked or returned empty. Finish Reason: {finish_reason}")
                        return None
                except ValueError:
                    finish_reason = "SAFETY_BLOCK"
                    if response and hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                        finish_reason = response.candidates[0].finish_reason.name
                    logger.error(f"  ❌  Part {i} generation blocked by safety filters. Finish Reason: {finish_reason}")
                    return None

            if section_text is not None:
                full_script_parts.append(section_text)
                script_so_far += section_text + "\n\n"
                
                word_count = len(section_text.split())
                logger.info(f"  ✅  Part {i} completed ({word_count} words).")
                time.sleep(2)
            else:
                logger.error(f"  ❌  Part {i} could not be generated! Aborting script generation for this title.")
                return None
        
        final_script = "\n\n---\n\n".join(full_script_parts)
        total_words = len(final_script.split())
        estimated_minutes = total_words / 150
        
        logger.info("\n✅ SCRIPT GENERATION COMPLETED!")
        logger.info(f"  📊 Total Words: {total_words}")
        logger.info(f"  ⏱️ Estimated Narration Time: {estimated_minutes:.1f} minutes")
        
        return final_script

    def format_script_for_saving(self, script, title):
        """Üretilen metni, yerel dosyaya kaydedilecek son formata getirir."""
        if not script or not title:
            return None
        header = [
            "="*60,
            "CHANNEL: The Creator's Blueprint",
            f"VIDEO TITLE: {title}",
            "TARGET AUDIENCE: American Creative Professionals",
            "HOST PERSONA: Leo (Calm, Empathetic Guide)",
            "HOOK OPTIMIZATION: 5 Dynamic Hook Types + Power Validation",
            "="*60,
            "\n"
        ]
        formatted_text = "\n".join(header) + script
        return formatted_text

# --- Worker İçin Özel Fonksiyon ---

def run_script_generation_process_for_worker(project_id: str):
    """
    Worker.py tarafından çağrılan özel fonksiyon.
    Tek bir video için metin üretir.
    
    Returns:
        tuple: (formatted_text, story_title) - Başarılıysa metin ve başlık, başarısızsa (None, None)
    """
    logger.info("--- 'The Creator's Blueprint' İçerik Üretim Modülü Worker İçin Başlatıldı (Secret Manager Uyumlu) ---")
    
    if not load_api_keys_from_secret_manager(project_id):
        logger.critical("❌ API anahtarları Secret Manager'dan yüklenemedi.")
        return None, None

    generator = CreatorsBlueprintGenerator()
    
    video_title = generator.get_and_update_next_title()
    if not video_title:
        logger.info("✅ Tüm başlıklar işlendi. Yeni konu bulunamadı.")
        return None, None

    script_content = generator.generate_script_by_section(video_title)
    if not script_content:
        logger.error(f"\n❌ BAŞARISIZ: '{video_title}' için metin üretilemedi.")
        return None, None

    formatted_script = generator.format_script_for_saving(script_content, video_title)
    if not formatted_script:
        logger.error("❌ Metin formatlanamadı.")
        return None, None

    logger.info(f"\n✅ İçerik üretimi başarıyla tamamlandı: '{video_title}'")
    return formatted_script, video_title

