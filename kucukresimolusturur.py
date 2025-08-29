# kucukresimolusturur.py (v6 - The Creator's Blueprint - Tamamen Bulut Uyumlu)

from __future__ import annotations
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
import re
import os

# --- Gerekli Kütüphaneler ---
try:
    import google.generativeai as genai
    from google.cloud import secretmanager
    from google.api_core import exceptions as google_exceptions
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("⚠️ Gerekli kütüphaneler bulunamadı.")
    print("   Lütfen 'pip install google-generativeai google-cloud-secret-manager Pillow' komutunu çalıştırın.")
    sys.exit(1)

# --- Global Değişkenler ---
API_KEYS = []
current_api_key_index = 0
model = None

# --- Kanal Kimliği ve Stil Ayarları (Değişiklik yok) ---
@dataclass(frozen=True)
class ThumbnailStyle:
    width: int = 1280
    height: int = 720
    bg_primary: tuple = (20, 30, 55)
    bg_secondary: tuple = (10, 15, 25)
    text_colour: tuple = (255, 255, 255)
    highlight_colour: tuple = (0, 200, 255)
    tag_bg_colour: tuple = (255, 215, 0) # Altın Sarısı
    tag_text_colour: tuple = (10, 15, 25)
    font_path: Path = Path("LiberationSans-Bold.ttf")
    base_title_font_size: int = 100
    base_subtitle_font_size: int = 60
    tag_font_size: int = 28
    min_title_font_size: int = 40
    min_subtitle_font_size: int = 30
    max_title_font_size: int = 140
    max_subtitle_font_size: int = 80
    left_margin: int = 50
    top_margin: int = 60
    bottom_margin: int = 60
    right_margin: int = 400
    base_line_spacing: int = 10
    min_line_spacing: int = 5
    max_line_spacing: int = 20
    base_section_spacing: int = 25
    min_section_spacing: int = 15
    max_section_spacing: int = 40
    text_stroke_width: int = 5
    text_stroke_color: tuple = (10, 15, 25)

STYLE = ThumbnailStyle()
CHANNEL_NAME = "The Creator's Blueprint"

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(asctime)s | %(message)s", stream=sys.stderr, datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# --- Gemini API Fonksiyonları (Bulut Versiyonu) ---

def load_api_keys_from_secret_manager(project_id):
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
    """Sıradaki API anahtarı ile Gemini'yi yapılandırır."""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS): return None
    try:
        api_key = API_KEYS[current_api_key_index]
        logger.info(f"🔄 API anahtarı {current_api_key_index + 1}/{len(API_KEYS)} deneniyor...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-pro")
        logger.info(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        logger.error(f"❌ API anahtarı {current_api_key_index + 1} ile yapılandırma hatası: {e}")
        current_api_key_index += 1
        return configure_gemini()

def ask_gemini(prompt: str) -> Optional[Mapping[str, str]]:
    """Gemini API çağrısı yapar ve JSON yanıtını doğrular."""
    global current_api_key_index, model
    initial_key_index = current_api_key_index
    while True:
        try:
            if model is None:
                model = configure_gemini()
                if model is None: raise Exception("Yapılandırılacak geçerli API anahtarı kalmadı.")
            
            generation_config = {"temperature": 0.7, "top_p": 0.9, "top_k": 40}
            logger.info("🤖 Gemini'ye thumbnail metni için istek gönderiliyor...")
            response = model.generate_content(prompt, generation_config=generation_config)
            
            if not response.text:
                raise Exception("Gemini'den boş yanıt alındı.")
            
            txt = re.sub(r'^```json\s*|\s*```$', '', response.text.strip(), flags=re.MULTILINE)
            result = json.loads(txt)
            
            required_keys = ["BOLD_TITLE", "INTRIGUING_SUBTITLE"]
            if not all(key in result for key in required_keys):
                raise Exception(f"Gemini yanıtında eksik anahtarlar: {set(required_keys) - set(result.keys())}")
            
            return result
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            logger.warning(f"⚠️ API anahtarı {current_api_key_index + 1} ile ilgili sorun: {type(e).__name__}. Anahtar değiştiriliyor...")
            current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
            model = None
            if current_api_key_index == initial_key_index: raise Exception(f"Tüm API anahtarları denendi ve hepsi başarısız oldu. Son hata: {e}") from e
        except Exception as exc:
            logger.error(f"❌ API Anahtarı {current_api_key_index + 1} ile beklenmedik API hatası: {exc}")
            current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
            model = None
            if current_api_key_index == initial_key_index: raise Exception(f"Tüm API anahtarları denendi. Son hata: {exc}") from exc

# --- Yapay Zeka Komut Üretimi (Değişiklik yok) ---
def clean_script_text(script: str) -> str:
    if not script or not isinstance(script, str): return "A guide for creative professionals."
    script = re.sub(r'^=+\n(.+\n)+=+\n', '', script, flags=re.MULTILINE)
    script = script.replace('---', '')
    if len(script) > 5000: script = script[:5000] + "..."
    script = re.sub(r'\s+', ' ', script).strip()
    return script

def build_prompt(script: str) -> str:
    clean_script = clean_script_text(script)
    return f"""
Analyze this script from the YouTube channel 'The Creator's Blueprint' and create two compelling text sections for a high-click-through-rate thumbnail.
Your host is Leo, an empathetic guide for American creative professionals. The tone should be professional, intriguing, and empowering.

Create 2 text sections:
1.  **BOLD_TITLE:** The most powerful and concise phrase from the script that grabs attention. Should be 3-5 words. It should summarize the core promise or the biggest pain point.
2.  **INTRIGUING_SUBTITLE:** A question or statement that creates curiosity and highlights the core problem or promise of the video. Should be 6-12 words.

CRITICAL REQUIREMENTS:
-   The text must be in ALL CAPS.
-   Do NOT use any special characters like asterisks (*).
-   Return ONLY a valid JSON format with keys: "BOLD_TITLE", "INTRIGUING_SUBTITLE".

Example Output:
{{
  "BOLD_TITLE": "THE ARTIST MYTH",
  "INTRIGUING_SUBTITLE": "WHY YOUR PASSION ISN'T PAYING THE BILLS (YET)"
}}

Script to analyze:
---
{clean_script}
---
""".strip()

# --- Thumbnail Oluşturma Sınıfı (Orijinal Yapı Korunarak Güncellendi) ---
class ThumbnailCanvas:
    def __init__(self, style: ThumbnailStyle = STYLE) -> None:
        self.style = style
        self.image = Image.new("RGB", (style.width, style.height))
        self.draw = ImageDraw.Draw(self.image)
        self._create_gradient_background()
        self.current_title_size = style.base_title_font_size
        self.current_subtitle_size = style.base_subtitle_font_size
        self.current_line_spacing = style.base_line_spacing
        self.current_section_spacing = style.base_section_spacing
        self._load_fonts()

    def _create_gradient_background(self) -> None:
        for y in range(self.style.height):
            ratio = y / self.style.height
            r = int(self.style.bg_primary[0] * (1 - ratio) + self.style.bg_secondary[0] * ratio)
            g = int(self.style.bg_primary[1] * (1 - ratio) + self.style.bg_secondary[1] * ratio)
            b = int(self.style.bg_primary[2] * (1 - ratio) + self.style.bg_secondary[2] * ratio)
            self.draw.line([(0, y), (self.style.width, y)], fill=(r, g, b))

    def _load_fonts(self) -> None:
        # Debian/Linux sistemleri için standart font yolları
        font_options = [
            Path(self.style.font_path), Path("LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("Arial.ttf"),
        ]
        try:
            font_path_str = next(str(p) for p in font_options if p.exists())
            self.font_title = ImageFont.truetype(font_path_str, self.current_title_size)
            self.font_subtitle = ImageFont.truetype(font_path_str, self.current_subtitle_size)
            self.font_tag = ImageFont.truetype(font_path_str, self.style.tag_font_size)
            logger.info(f"✅ Fontlar başarıyla yüklendi: {font_path_str}")
        except (StopIteration, IOError, OSError):
            logger.error("❌ Hiçbir TrueType font bulunamadı! Varsayılan font kullanılıyor.")
            self.font_title = self.font_subtitle = self.font_tag = ImageFont.load_default()

    def _get_text_size(self, text, font):
        if not text: return 0, 0
        try:
            bbox = self.draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            return self.draw.textsize(text, font=font)

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        if not text: return []
        lines = []
        words = text.split()
        while words:
            line = ''
            while words and self._get_text_size(line + words[0], font)[0] <= max_width:
                line += (words.pop(0) + ' ')
            lines.append(line.strip())
        return lines

    def _draw_text_with_outline(self, pos, text, font, fill_color, stroke_color=None, stroke_width=None):
        x, y = pos
        stroke_width = stroke_width or self.style.text_stroke_width
        stroke_color = stroke_color or self.style.text_stroke_color
        self.draw.text((x-stroke_width, y), text, font=font, fill=stroke_color)
        self.draw.text((x+stroke_width, y), text, font=font, fill=stroke_color)
        self.draw.text((x, y-stroke_width), text, font=font, fill=stroke_color)
        self.draw.text((x, y+stroke_width), text, font=font, fill=stroke_color)
        self.draw.text((x, y), text, font=font, fill=fill_color)

    def _calculate_total_height_needed(self, title_lines: list, subtitle_lines: list) -> int:
        tag_height_with_margin = 60 
        total_height = self.style.top_margin + tag_height_with_margin
        if title_lines:
            total_height += len(title_lines) * (self._get_text_size("A", self.font_title)[1] + self.current_line_spacing)
            total_height += self.current_section_spacing
        if subtitle_lines:
            total_height += len(subtitle_lines) * (self._get_text_size("A", self.font_subtitle)[1] + self.current_line_spacing)
        total_height += self.style.bottom_margin
        return total_height
        
    def _scale_sizes(self, factor: float) -> None:
        self.current_title_size = int(self.current_title_size * factor)
        self.current_subtitle_size = int(self.current_subtitle_size * factor)

    def _scale_spacing(self, factor: float) -> None:
        self.current_line_spacing = int(self.current_line_spacing * factor)
        self.current_section_spacing = int(self.current_section_spacing * factor)
        
    def _clamp_and_reload_fonts(self):
        self.current_title_size = max(self.style.min_title_font_size, min(self.style.max_title_font_size, self.current_title_size))
        self.current_subtitle_size = max(self.style.min_subtitle_font_size, min(self.style.max_subtitle_font_size, self.current_subtitle_size))
        self.current_line_spacing = max(self.style.min_line_spacing, min(self.style.max_line_spacing, self.current_line_spacing))
        self.current_section_spacing = max(self.style.min_section_spacing, min(self.style.max_section_spacing, self.current_section_spacing))
        self._load_fonts()

    def _adjust_for_perfect_fill(self, bold_title: str, intriguing_subtitle: str, text_area_width: int) -> None:
        target_height = self.style.height - self.style.top_margin - self.style.bottom_margin
        max_attempts = 30
        for attempt in range(max_attempts):
            title_lines = self._wrap_text(bold_title, self.font_title, text_area_width)
            subtitle_lines = self._wrap_text(intriguing_subtitle, self.font_subtitle, text_area_width)
            current_height = self._calculate_total_height_needed(title_lines, subtitle_lines)
            height_ratio = current_height / target_height
            if 0.95 <= height_ratio <= 1.0:
                logger.info(f"✓ Mükemmel ekran doluluğuna ulaşıldı (Oran: {height_ratio:.2f})")
                break
            if height_ratio < 0.95: self._scale_sizes(1.05); self._scale_spacing(1.05)
            elif height_ratio > 1.0: self._scale_sizes(0.95)
            self._clamp_and_reload_fonts()
        else:
            logger.warning("⚠️ Mükemmel doluluk oranına ulaşılamadı, en yakın sonuç kullanılıyor.")

    def _draw_highlighted_title(self, pos, line: str, font):
        x, y = pos
        if " " in line:
             first_word, rest_of_line = line.split(" ", 1)
             self._draw_text_with_outline((x, y), first_word, font, self.style.highlight_colour)
             x += self._get_text_size(first_word + " ", font)[0]
             self._draw_text_with_outline((x, y), rest_of_line, font, self.style.text_colour)
        else:
             self._draw_text_with_outline((x, y), line, font, self.style.highlight_colour)

    def _draw_profile_section(self, img_path: str) -> None:
        try:
            profile_img = Image.open(img_path).convert("RGBA")
            target_height = int(self.style.height)
            ratio = target_height / profile_img.height
            new_width = int(profile_img.width * ratio)
            profile_img = profile_img.resize((new_width, target_height), Image.Resampling.LANCZOS)
            x_pos = self.style.width - new_width
            self.image.paste(profile_img, (x_pos, 0), profile_img)
        except Exception as e:
            logger.warning(f"⚠️ Profil resmi yüklenemedi: {img_path}. Atlanıyor. Hata: {e}")

    def _draw_target_audience_tag(self):
        tag_text = "FOR CREATIVES"
        padding = 15
        text_width, text_height = self._get_text_size(tag_text, self.font_tag)
        box_width = text_width + (padding * 2)
        box_height = text_height + (padding * 2)
        box_x = self.style.left_margin
        box_y = self.style.top_margin
        box_img = Image.new("RGBA", (box_width, box_height), (0,0,0,0))
        box_draw = ImageDraw.Draw(box_img)
        box_draw.rounded_rectangle((0, 0, box_width, box_height), radius=10, fill=self.style.tag_bg_colour)
        self.image.paste(box_img, (box_x, box_y), box_img)
        text_x = box_x + padding
        text_y = box_y + padding
        self.draw.text((text_x, text_y), tag_text, font=self.font_tag, fill=self.style.tag_text_colour)
        return box_height

    def compose(self, bold_title: str, intriguing_subtitle: str, profile_pic_path: str):
        self._draw_profile_section(profile_pic_path)
        tag_height = self._draw_target_audience_tag()
        
        text_area_width = self.style.width - self.style.left_margin - self.style.right_margin
        self._adjust_for_perfect_fill(bold_title, intriguing_subtitle, text_area_width)

        y = self.style.top_margin + tag_height + 20
        title_lines = self._wrap_text(bold_title, self.font_title, text_area_width)
        for line in title_lines:
            self._draw_highlighted_title((self.style.left_margin, y), line, self.font_title)
            y += self._get_text_size(line, self.font_title)[1] + self.current_line_spacing
            
        y += self.current_section_spacing

        subtitle_lines = self._wrap_text(intriguing_subtitle, self.font_subtitle, text_area_width)
        for line in subtitle_lines:
            self._draw_text_with_outline((self.style.left_margin, y), line, self.font_subtitle, self.style.text_colour)
            y += self._get_text_size(line, self.font_subtitle)[1] + self.current_line_spacing

# --- Ana İş Akışı Fonksiyonu (BULUT VERSİYONU) ---
def run_thumbnail_generation(story_text, profile_photo_path, output_dir, worker_project_id):
    logger.info("--- 'The Creator's Blueprint' Küçük Resim Üretim Modülü Başlatıldı (Bulut) ---")
    
    if not load_api_keys_from_secret_manager(worker_project_id):
        raise Exception("Thumbnail üretimi için Gemini API anahtarları yüklenemedi.")
    
    prompt = build_prompt(story_text)
    
    try:
        parts = ask_gemini(prompt)
    except Exception as e:
        logger.error(f"❌ Tüm denemelere rağmen Gemini ile geçerli metin üretilemedi. Hata: {e}")
        raise
        
    logger.info("\n📋 Başarıyla Üretilen Thumbnail Metinleri:")
    logger.info(f"  BOLD_TITLE: {parts.get('BOLD_TITLE')}")
    logger.info(f"  INTRIGUING_SUBTITLE: {parts.get('INTRIGUING_SUBTITLE')}")
    
    logger.info("\n🎨 Thumbnail canvas oluşturuluyor...")
    
    try:
        canvas = ThumbnailCanvas(STYLE)
        canvas.compose(
            bold_title=parts.get("BOLD_TITLE", "YOUR BLUEPRINT"),
            intriguing_subtitle=parts.get("INTRIGUING_SUBTITLE", "Build a sustainable creative career."),
            profile_pic_path=profile_photo_path,
        )
        
        thumbnail_path = os.path.join(output_dir, "kucuk_resim.png")
        canvas.image.save(thumbnail_path, "PNG", quality=95)
        logger.info(f"💾 Thumbnail başarıyla kaydedildi: {thumbnail_path}")
        
        file_size = os.path.getsize(thumbnail_path)
        logger.info(f"📏 Dosya boyutu: {file_size / 1024:.1f} KB")
        
        return thumbnail_path
        
    except Exception as e:
        logger.error(f"❌ Thumbnail oluşturma/kaydetme aşamasında kritik hata: {e}", exc_info=True)
        raise

