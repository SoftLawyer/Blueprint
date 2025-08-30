import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import time
import re
import random
import logging

# --- Global Değişkenler ---
# Bu değişkenler, modülün o anki oturumda kullandığı API anahtarlarını,
# sıradaki anahtarın hangisi olduğunu ve yapılandırılmış Gemini modelini tutar.
API_KEYS = []
current_api_key_index = 0
model = None

# --- Gemini API Entegrasyon Fonksiyonları ---

def initialize_gemini(api_keys_list: list):
    """
    Ana yönetici (worker.py) tarafından çağrılır.
    Secret Manager'dan alınan API anahtar listesi ile Gemini'yi başlatır.
    """
    global API_KEYS, current_api_key_index
    if not api_keys_list:
        logging.critical("❌ Başlatma için hiç API anahtarı sağlanmadı.")
        return False
        
    API_KEYS = api_keys_list
    current_api_key_index = 0
    # İlk anahtarla yapılandırmayı dene
    return configure_gemini() is not None

def configure_gemini():
    """
    Sıradaki API anahtarını kullanarak Gemini modelini yapılandırır.
    Bir anahtar başarısız olursa, listedeki bir sonrakini dener.
    """
    global current_api_key_index, model
    # Kullanılabilir anahtar kalıp kalmadığını kontrol et
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        logging.error("❌ Kullanılabilir Gemini API anahtarı kalmadı.")
        return None
        
    try:
        api_key = API_KEYS[current_api_key_index]
        logging.info(f"🔄 Gemini API anahtarı {current_api_key_index + 1}/{len(API_KEYS)} deneniyor...")
        genai.configure(api_key=api_key)
        
        # Model yapılandırması
        generation_config = {
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048
        }
        # Daha modern ve verimli bir model kullanıyoruz
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash-latest",
            generation_config=generation_config
        )
        logging.info(f"✅ Gemini API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        logging.error(f"❌ API anahtarı {current_api_key_index + 1} ile yapılandırma hatası: {e}")
        # Başarısız olursa bir sonraki anahtarı denemek için indeksi artır
        current_api_key_index += 1
        return configure_gemini()

def generate_with_failover(prompt: str):
    """
    Gemini API'ye güvenli bir şekilde istek gönderir.
    Kota veya izin hatası gibi durumlarda otomatik olarak bir sonraki API anahtarını dener.
    """
    global current_api_key_index, model
    
    while current_api_key_index < len(API_KEYS):
        try:
            # Eğer model henüz yapılandırılmadıysa, şimdi yap
            if model is None:
                if not configure_gemini():
                    return None # Hiç geçerli anahtar bulunamadıysa None dön
            
            # İçerik üretme isteği gönder
            response = model.generate_content(prompt)
            return response
            
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            logging.warning(f"⚠️ API anahtarı {current_api_key_index + 1} kotaya takıldı veya izin sorunu. Değiştiriliyor...")
            current_api_key_index += 1
            model = None # Modeli sıfırla ki sonraki anahtarla yeniden denensin
            
        except Exception as e:
            logging.error(f"❌ Metin üretimi sırasında beklenmedik API hatası: {e}")
            return None # Beklenmedik hatalarda işlemi durdur
            
    logging.error("Tüm API anahtarları denendi ve hiçbiri başarılı olamadı.")
    return None

# --- "The Creator's Blueprint" İçerik Üretici Sınıfı ---

class CreatorsBlueprintGenerator:
    """
    Video metinlerini, belirlenmiş bir yapıya ve stile uygun olarak bölüm bölüm üretir.
    """
    def __init__(self):
        # Kanalın marka kimliğine uygun, dikkat çekici giriş (hook) metinleri için şablonlar
        self.hook_types = [
            {"name": "The Shocking Reality Check", "description": "Start with a surprising industry statistic or harsh truth"},
            {"name": "The Universal Pain Point", "description": "Address the shared struggle all creatives face"},
            {"name": "The Costly Belief", "description": "Reveal how a common belief is secretly expensive"},
            {"name": "The Time Bomb", "description": "Show what happens if they don't act soon"},
            {"name": "The Hidden Truth", "description": "Reveal something the industry doesn't want them to know"}
        ]
        # Videonun baştan sona akışını ve her bölümün amacını belirleyen yapı
        self.script_structure = {
            1: {"name": "The Hook", "words": 100, "task": "Generate a powerful hook using one of the proven hook types."},
            2: {"name": "The Core Problem", "words": 300, "task": "Explain the psychological conflict creatives face."},
            3: {"name": "The Timeless Principle", "words": 450, "task": "Introduce a single, powerful, evergreen financial or business principle."},
            4: {"name": "The Creative Analogy", "words": 250, "task": "Explain the principle using a powerful analogy from the creative world."},
            5: {"name": "The Mindset Shift", "words": 250, "task": "Describe the internal shift the viewer needs to make."},
            6: {"name": "The Blueprint Summary & CTA", "words": 150, "task": "Provide a concise summary and a clear call to action."}
        }

    def get_and_process_next_title(self, titles_list: list) -> tuple[str | None, list]:
        """
        Verilen başlık listesinin en üstündeki başlığı işler.
        İşlenen başlığı ve geriye kalan başlıkların olduğu yeni listeyi döndürür.
        Bu fonksiyon, dosya okuma/yazma işlemini worker.py'a bırakır.
        """
        if not titles_list:
            logging.info("✅ İşlenecek başka başlık kalmadı.")
            return None, []
            
        title_to_process = titles_list[0]
        remaining_titles = titles_list[1:]
        logging.info(f"🔹 Sıradaki başlık: '{title_to_process}'. Listede kalan: {len(remaining_titles)}")
        return title_to_process, remaining_titles

    def generate_full_script(self, video_title: str) -> str | None:
        """
        Verilen bir başlık için, script_structure'ı takip ederek tam bir video metni üretir.
        """
        logging.info(f"--- '{video_title}' için metin üretimi başladı ---")
        full_script_parts = []
        script_so_far = ""

        # Video yapısındaki her bölüm için sırayla metin üret
        for i, section_info in self.script_structure.items():
            section_name = section_info["name"]
            logging.info(f"➡️  Bölüm {i}/{len(self.script_structure)} üretiliyor: '{section_name}'...")
            
            # Her bölüm için Gemini'ye özel bir komut (prompt) oluşturulur
            prompt = f"""
You are a calm, empathetic, and knowledgeable financial educator for a YouTube channel called 'The Creator's Blueprint'.
VIDEO TITLE: "{video_title}"
SCRIPT SO FAR (For context):
---
{script_so_far if script_so_far else "This is the very first part of the script."}
---
Your task is to write ONLY the text for the next single section.
NEXT SECTION: "{section_name}"
GOAL: "{section_info['task']}"
TARGET WORDS: ~{section_info['words']}
CRITICAL INSTRUCTIONS:
- Write ONLY the text for this section. Do NOT add titles or summaries unless the section name is "The Blueprint Summary & CTA".
- If the section is "The Core Problem", you MUST start with this disclaimer: "Before we dive in, I want to be crystal clear: I'm a financial educator, not a licensed financial advisor... Please always consult with a qualified professional for your unique situation. Okay, let's get into it."
"""
            response = generate_with_failover(prompt)
            section_text = response.text.strip() if response and hasattr(response, 'text') else None

            if section_text:
                full_script_parts.append(section_text)
                script_so_far += section_text + "\n\n"
                logging.info(f"✅  Bölüm {i} tamamlandı ({len(section_text.split())} kelime).")
                time.sleep(2) # API'ye aşırı yüklenmemek için kısa bir bekleme
            else:
                logging.error(f"❌  Bölüm {i} üretilemedi! Bu başlık için metin üretimi iptal ediliyor.")
                return None
        
        final_script = "\n\n---\n\n".join(full_script_parts)
        logging.info(f"--- '{video_title}' için metin üretimi başarıyla tamamlandı ---")
        return final_script

    def format_script_for_saving(self, script: str, title: str) -> str | None:
        """
        Üretilen metni, video hakkında bilgiler içeren bir başlık bloğuyla formatlar.
        """
        if not script or not title: return None
        header = [
            "="*60,
            "CHANNEL: The Creator's Blueprint",
            f"VIDEO TITLE: {title}",
            "HOST PERSONA: Leo (Calm, Empathetic Guide)",
            "="*60, "\n"
        ]
        return "\n".join(header) + script

# --- ANA FONKSİYON (worker.py tarafından çağrılır) ---
def run_script_generation_process(api_keys: list, title_list: list) -> tuple[str | None, str | None, list]:
    """
    Tüm hikaye üretim sürecini yönetir.
    
    Args:
        api_keys: Secret Manager'dan alınan Gemini API anahtarları.
        title_list: Cloud Storage'dan okunan mevcut başlık listesi.
        
    Returns:
        Bir tuple döner: (formatlanmış_metin, işlenen_başlık, kalan_başlıklar_listesi)
    """
    logging.info("--- Hikaye Üretim Modülü Başlatıldı ---")
    
    # Gelen API anahtarlarıyla Gemini'yi başlat
    if not initialize_gemini(api_keys):
        logging.critical("❌ Gemini API anahtarlarıyla başlatılamadı.")
        return None, None, title_list

    generator = CreatorsBlueprintGenerator()
    
    # Sıradaki başlığı ve güncel listeyi al
    video_title, remaining_titles = generator.get_and_process_next_title(title_list)
    
    # Eğer işlenecek başlık kalmadıysa, sonucu worker'a bildir
    if not video_title:
        return None, None, remaining_titles

    # Seçilen başlık için tam metni üret
    script_content = generator.generate_full_script(video_title)
    
    # Metin üretimi başarısız olduysa
    if not script_content:
        logging.error(f"❌ '{video_title}' için metin üretilemedi. Başlık tekrar denenecek şekilde listenin sonuna ekleniyor.")
        # Başarısız olan başlığı listenin sonuna ekleyerek tekrar denenmesini sağla
        # ve sonucu worker'a bildir.
        return None, video_title, remaining_titles + [video_title]

    # Başarılı metni formatla
    formatted_script = generator.format_script_for_saving(script_content, video_title)
    if not formatted_script:
        logging.error("❌ Üretilen metin formatlanamadı.")
        return None, video_title, remaining_titles

    logging.info(f"✅ '{video_title}' için tüm işlemler başarıyla tamamlandı.")
    # Formatlanmış metni, işlenen başlığı ve güncel başlık listesini worker'a döndür
    return formatted_script, video_title, remaining_titles

