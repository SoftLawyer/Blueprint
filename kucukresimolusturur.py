# kucukresimolusturur.py (Gemini API Key Uyumlu ve Font Ayarı Güncellenmiş Versiyon)

from __future__ import annotations
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
import re
import os

# --- YENİ: Gemini ve Google Cloud Kütüphaneleri ---
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

# --- SİZİN ORİJİNAL AYARLARINIZ VE SINIFINIZ (İlgili Kısımlar Güncellendi) ---
@dataclass(frozen=True)
class ThumbnailStyle:
    width: int = 1280; height: int = 720; bg_primary: tuple = (15, 15, 25)
    bg_secondary: tuple = (25, 25, 40); text_colour: tuple = (255, 255, 255)
    highlight_colour: tuple = (255, 215, 0); revenge_colour: tuple = (138, 43, 226)
    revenge_bg_colour: tuple = (255, 215, 0); channel_bg: tuple = (0, 0, 0)
    channel_text: tuple = (255, 215, 0); channel_border: tuple = (255, 215, 0)
    font_path: Path = Path("impact.ttf"); base_title_font_size: int = 110
    base_normal_font_size: int = 80; base_revenge_font_size: int = 100
    base_channel_font_size: int = 32
    min_title_font_size: int = 35; min_normal_font_size: int = 28
    min_revenge_font_size: int = 35
    # GÜNCELLENDİ: Kanal adı yazısının sığması için minimum boyut düşürüldü.
    min_channel_font_size: int = 18
    max_title_font_size: int = 150; max_normal_font_size: int = 120
    max_revenge_font_size: int = 140
    # YENİ: Kanal adı için maksimum font boyutu eklendi.
    max_channel_font_size: int = 40
    left_margin: int = 15; top_margin: int = 15; bottom_margin: int = 20
    right_margin: int = 15; base_line_spacing: int = 8; min_line_spacing: int = 3
    max_line_spacing: int = 20; base_section_spacing: int = 15
    min_section_spacing: int = 8; max_section_spacing: int = 30
    text_stroke_width: int = 4; text_stroke_color: tuple = (0, 0, 0)

STYLE = ThumbnailStyle()
CHANNEL_NAME = "REVENGE WITH ROBERT"

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

# --- GÜNCELLENMİŞ: Gemini API Key Fonksiyonları ---

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
            logger.error("❌ Secret Manager'da API anahtarı bulunamadı.")
            return False
        logger.info(f"🔑 {len(API_KEYS)} Gemini API anahtarı başarıyla yüklendi.")
        return True
    except Exception as e:
        logger.error(f"❌ Secret Manager'dan anahtar okunurken hata oluştu: {e}")
        return False

def configure_gemini():
    """Sıradaki API anahtarı ile Gemini'yi yapılandırır."""
    global current_api_key_index, model
    if not API_KEYS or current_api_key_index >= len(API_KEYS):
        return None
    try:
        api_key = API_KEYS[current_api_key_index]
        logger.info(f"🔄 API anahtarı {current_api_key_index + 1} deneniyor...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        logger.info(f"✅ API anahtarı {current_api_key_index + 1} başarıyla yapılandırıldı.")
        return model
    except Exception as e:
        logger.error(f"❌ API anahtarı {current_api_key_index + 1} ile yapılandırma hatası: {e}")
        current_api_key_index += 1
        return configure_gemini()

def ask_gemini(prompt: str) -> Optional[Mapping[str, str]]:
    """Gemini API çağrısı - hata durumunda Exception fırlatır."""
    global current_api_key_index, model
    if current_api_key_index >= len(API_KEYS):
        current_api_key_index = 0
        logger.warning("⚠️ Tüm API anahtarları denendi, baştan başlanıyor.")

    while current_api_key_index < len(API_KEYS):
        try:
            if model is None:
                model = configure_gemini()
                if model is None:
                    raise Exception("Yapılandırılacak geçerli API anahtarı kalmadı.")
            
            generation_config = {"temperature": 0.7, "top_p": 0.8, "top_k": 40, "max_output_tokens": 2048}
            response = model.generate_content(prompt, generation_config=generation_config)
            
            if not response.text:
                raise Exception("Gemini'den boş yanıt alındı")
            
            txt = re.sub(r'^```json\s*|\s*```$', '', response.text.strip(), flags=re.MULTILINE)
            result = json.loads(txt)
            
            required_keys = ["MAIN_HOOK", "SETUP", "REVENGE_LINE", "EXTRA_DETAIL"]
            if not all(key in result for key in required_keys):
                raise Exception(f"Gemini yanıtında eksik anahtarlar: {set(required_keys) - set(result.keys())}")
            
            return result
            
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
            logger.warning(f"⚠️ API anahtarı {current_api_key_index + 1} kotaya takıldı veya izin sorunu: {e}. Değiştiriliyor...")
            current_api_key_index += 1
            model = None
        except Exception as exc:
            logger.error(f"❌ API Anahtarı {current_api_key_index + 1} ile beklenmedik API hatası: {exc}")
            current_api_key_index += 1
            model = None
    
    raise Exception("Tüm API anahtarları denendi ve hepsi başarısız oldu.")

# --- Yardımcı Fonksiyonlar (Orijinal Kodunuz) ---
def count_words(text: str) -> int:
    if not text or not isinstance(text, str): return 0
    return len(re.sub(r'\*', '', text.strip()).split())
def clean_story_text(story: str) -> str:
    if not story or not isinstance(story, str): return "Bir intikam hikayesi anlatılacak."
    if len(story) > 8000: story = story[:8000] + "..."
    story = re.sub(r'[^\w\s.,!?;:\-\'"()[\]{}]', ' ', story)
    story = re.sub(r'\s+', ' ', story).strip()
    if len(story) < 50: story = f"{story} Bu kişi büyük bir intikam planladı ve başarılı oldu."
    return story
def build_prompt(story: str) -> str:
    clean_story = clean_story_text(story)
    return f"""
Analyze this revenge story and create compelling YouTube thumbnail text with a TOTAL WORD COUNT between 80 and 100 words.
Create 4 text sections:
1. MAIN_HOOK: Most dramatic attention-grabber (28-33 words) - mark 4-5 key trigger words with *asterisks*
2. SETUP: Context that builds tension (28-33 words) - mark 4-5 trigger words with *asterisks*
3. REVENGE_LINE: The ultimate revenge payoff (2-5 words, VERY PUNCHY AND SHORT)
4. EXTRA_DETAIL: Additional dramatic impact (22-29 words) - mark 3-4 trigger words with *asterisks*
CRITICAL REQUIREMENTS:
- TOTAL WORD COUNT: Must be between 80-100 words (excluding asterisks)
- Return ONLY valid JSON format with keys: "MAIN_HOOK", "SETUP", "REVENGE_LINE", "EXTRA_DETAIL"
Story:
---
{clean_story}
---
""".strip()
class ThumbnailCanvas:
    def __init__(self, style: ThumbnailStyle = STYLE) -> None:
        self.style = style; self.image = Image.new("RGB", (style.width, style.height), style.bg_primary); self.draw = ImageDraw.Draw(self.image); self._create_gradient_background(); self.current_title_size = style.base_title_font_size; self.current_normal_size = style.base_normal_font_size; self.current_revenge_size = style.base_revenge_font_size; self.current_channel_size = style.base_channel_font_size; self.current_line_spacing = style.base_line_spacing; self.current_section_spacing = style.base_section_spacing; self._load_fonts()
    def _create_gradient_background(self) -> None:
        for y in range(self.style.height): ratio = y / self.style.height; r = int(self.style.bg_primary[0] * (1 - ratio) + self.style.bg_secondary[0] * ratio); g = int(self.style.bg_primary[1] * (1 - ratio) + self.style.bg_secondary[1] * ratio); b = int(self.style.bg_primary[2] * (1 - ratio) + self.style.bg_secondary[2] * ratio); self.draw.line([(0, y), (self.style.width, y)], fill=(r, g, b))
    def _load_fonts(self) -> None:
        font_options = [self.style.font_path, Path("impact.ttf"), Path("arial.ttf"), Path("Impact.ttf"), Path("Arial.ttf"), Path("/usr/share/fonts/truetype/msttcorefonts/Impact.ttf"), Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"), Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")]
        font_loaded = False
        for font_path in font_options:
            if font_path.exists():
                try: self.font_title = ImageFont.truetype(str(font_path), self.current_title_size); self.font_normal = ImageFont.truetype(str(font_path), self.current_normal_size); self.font_revenge = ImageFont.truetype(str(font_path), self.current_revenge_size); self.font_channel = ImageFont.truetype(str(font_path), self.current_channel_size); font_loaded = True; logger.info(f"✅ Font yüklendi: {font_path}"); break
                except (IOError, OSError) as e: logger.warning(f"⚠️ Font yüklenemedi {font_path}: {e}")
        if not font_loaded: logger.warning("⚠️ Hiçbir TrueType font bulunamadı, varsayılan font kullanılıyor"); self.font_title = self.font_normal = self.font_revenge = self.font_channel = ImageFont.load_default()
    def _text_width(self, text: str, font: ImageFont.FreeTypeFont) -> int:
        if not text: return 0
        try: return font.getlength(text)
        except AttributeError: bbox = self.draw.textbbox((0, 0), text, font=font); return bbox[2] - bbox[0]
    def _text_height(self, font: ImageFont.FreeTypeFont) -> int:
        try: bbox = font.getbbox("Ag"); return bbox[3] - bbox[1]
        except: return 20
    def _calculate_total_height_needed(self, main_hook: str, setup: str, revenge_line: str, extra_detail: str, text_area_width: int) -> int:
        total_height = self.style.top_margin; hook_lines = self._wrap_text_smart(main_hook.upper(), self.font_title, text_area_width); total_height += len(hook_lines) * (self._text_height(self.font_title) + self.current_line_spacing); total_height += self.current_section_spacing; setup_lines = self._wrap_text_smart(setup.upper(), self.font_normal, text_area_width); total_height += len(setup_lines) * (self._text_height(self.font_normal) + self.current_line_spacing); total_height += self.current_section_spacing
        if extra_detail: extra_lines = self._wrap_text_smart(extra_detail.upper(), self.font_normal, text_area_width); total_height += len(extra_lines) * (self._text_height(self.font_normal) + self.current_line_spacing); total_height += self.current_section_spacing
        total_height += self.style.bottom_margin; return total_height
    def _adjust_for_perfect_fill(self, main_hook: str, setup: str, revenge_line: str, extra_detail: str, text_area_width: int, total_words: int) -> None:
        revenge_area_height = 140; target_height = self.style.height - self.style.top_margin - self.style.bottom_margin - revenge_area_height; max_attempts = 30; scale_factor = 1.05 if total_words < 85 else 0.95 if total_words > 95 else 1.0; spacing_factor = 1.1 if total_words < 85 else 0.9 if total_words > 95 else 1.0
        self._scale_sizes(scale_factor); self._scale_spacing(spacing_factor); self._clamp_and_reload_fonts()
        for attempt in range(max_attempts):
            current_height = self._calculate_total_height_needed(main_hook, setup, revenge_line, extra_detail, text_area_width); height_ratio = current_height / target_height
            if 0.98 <= height_ratio <= 1.02: logger.info("✓ Perfect screen fill achieved!"); break
            if height_ratio < 0.98:
                if self._can_increase_sizes(): self._scale_sizes(min(1.06, (1.0 / height_ratio)))
                else: self._scale_spacing(1.08)
            elif height_ratio > 1.02: self._scale_sizes(max(0.94, (1.0 / height_ratio)))
            self._clamp_and_reload_fonts()
    def _can_increase_sizes(self) -> bool: return (self.current_title_size < self.style.max_title_font_size or self.current_normal_size < self.style.max_normal_font_size or self.current_revenge_size < self.style.max_revenge_font_size)
    def _scale_sizes(self, factor: float) -> None: self.current_title_size = int(self.current_title_size * factor); self.current_normal_size = int(self.current_normal_size * factor); self.current_revenge_size = int(self.current_revenge_size * factor)
    def _scale_spacing(self, factor: float) -> None: self.current_line_spacing = int(self.current_line_spacing * factor); self.current_section_spacing = int(self.current_section_spacing * factor)
    def _clamp_and_reload_fonts(self): self.current_title_size = max(self.style.min_title_font_size, min(self.style.max_title_font_size, self.current_title_size)); self.current_normal_size = max(self.style.min_normal_font_size, min(self.style.max_normal_font_size, self.current_normal_size)); self.current_revenge_size = max(self.style.min_revenge_font_size, min(self.style.max_revenge_font_size, self.current_revenge_size)); self.current_line_spacing = max(self.style.min_line_spacing, min(self.style.max_line_spacing, self.current_line_spacing)); self.current_section_spacing = max(self.style.min_section_spacing, min(self.style.max_section_spacing, self.current_section_spacing)); self._load_fonts()
    def _draw_text_with_outline(self, pos, text, font, fill_color, outline_color=None, outline_width=None):
        x, y = pos; outline_color = outline_color or self.style.text_stroke_color
        if font is None: self.draw.text((x, y), text, fill=fill_color); return
        outline_width = outline_width or max(3, int(getattr(font, 'size', 30) / 30))
        try: self.draw.text((x, y), text, font=font, fill=fill_color, stroke_width=outline_width, stroke_fill=outline_color)
        except: self.draw.text((x, y), text, font=font, fill=fill_color)
    def _wrap_text_smart(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
        if not text: return []
        parts, current, in_highlight = [], "", False
        for char in text:
            if char == '*':
                if current: parts.append((current, in_highlight))
                current, in_highlight = "", not in_highlight
            else: current += char
        if current: parts.append((current, in_highlight))
        lines, current_line_parts, current_line_width = [], [], 0
        for part_text, is_highlighted in parts:
            for word in part_text.split():
                word_width = self._text_width(word + " ", font)
                if current_line_width + word_width > max_width and current_line_parts: lines.append(current_line_parts); current_line_parts, current_line_width = [], 0
                current_line_parts.append((word, is_highlighted)); current_line_width += word_width
        if current_line_parts: lines.append(current_line_parts)
        return lines
    def _draw_highlighted_text_line(self, line_parts, pos, font):
        x, y = pos
        for word, is_highlighted in line_parts:
            color = self.style.highlight_colour if is_highlighted else self.style.text_colour
            self._draw_text_with_outline((x, y), word, font, color)
            x += self._text_width(word + " ", font)
    def _draw_revenge_text_with_background_bottom(self, text: str, profile_width: int) -> None:
        available_width = self.style.width - profile_width - (self.style.left_margin * 2); revenge_text = text.upper(); best_font_size = self.style.min_revenge_font_size
        for font_size in range(400, self.style.min_revenge_font_size - 1, -2):
            try:
                test_font = ImageFont.truetype(str(self.style.font_path), font_size)
                if self._text_width(revenge_text, test_font) <= available_width - 20: best_font_size = font_size; break
            except (IOError, OSError): continue
        try: revenge_font = ImageFont.truetype(str(self.style.font_path), best_font_size)
        except: revenge_font = self.font_revenge
        text_width = self._text_width(revenge_text, revenge_font); text_height = self._text_height(revenge_font); padding = 20; bg_height = text_height + (padding * 2); bg_y = self.style.height - bg_height - 20; bg_x = self.style.left_margin
        bg_img = Image.new("RGBA", (available_width, bg_height), (0, 0, 0, 0)); bg_draw = ImageDraw.Draw(bg_img); bg_draw.rounded_rectangle([0, 0, available_width, bg_height], radius=15, fill=(*self.style.revenge_bg_colour, 240)); self.image.paste(bg_img, (bg_x, bg_y), bg_img)
        text_x = bg_x + (available_width - text_width) // 2; text_y = bg_y + padding
        self._draw_text_with_outline((text_x, text_y), revenge_text, revenge_font, self.style.revenge_colour, outline_color=(0, 0, 0), outline_width=4)
    def _draw_profile_section(self, img_path: str, channel_name: str) -> int:
        try:
            avatar = Image.open(img_path).convert("RGBA")
        except (FileNotFoundError, Exception) as e:
            logger.warning(f"Profil resmi yüklenemedi: {e}")
            avatar = Image.new("RGBA", (200, 720), (100, 100, 100, 255))
        target_width, target_height = 200, 720; avatar = avatar.resize((target_width, target_height), Image.Resampling.LANCZOS); x = self.style.width - target_width; self.image.paste(avatar, (x, 0), avatar if avatar.mode == 'RGBA' else None)
        channel_text = channel_name.upper(); best_channel_font_size = self.style.min_channel_font_size; padding = 15
        # GÜNCELLENDİ: Font boyutu arama döngüsü artık stilden gelen max ve min değerleri kullanıyor.
        for font_size in range(self.style.max_channel_font_size, self.style.min_channel_font_size - 1, -2):
            try:
                test_font = ImageFont.truetype(str(self.style.font_path), font_size)
                if self._text_width(channel_text, test_font) <= target_width - 20 - (padding * 2): best_channel_font_size = font_size; break
            except (IOError, OSError): continue
        try: channel_font = ImageFont.truetype(str(self.style.font_path), best_channel_font_size)
        except: channel_font = self.font_channel
        text_width = self._text_width(channel_text, channel_font); text_height = self._text_height(channel_font); box_height = text_height + (padding * 2); box_width = target_width - 20
        # Kanal adı kutusunu daha yukarı taşıyoruz (revenge text ile çakışmayı önlemek için)
        box_y = target_height - box_height - 80; box_x = x + 10
        box_img = Image.new("RGBA", (box_width, box_height), (0, 0, 0, 0)); box_draw = ImageDraw.Draw(box_img); box_draw.rounded_rectangle([0, 0, box_width, box_height], radius=12, fill=(*self.style.channel_bg, 230)); box_draw.rounded_rectangle([1, 1, box_width-1, box_height-1], radius=12, outline=(*self.style.channel_border, 255), width=3); self.image.paste(box_img, (box_x, box_y), box_img)
        text_x = box_x + (box_width - text_width) // 2; text_y = box_y + padding
        self._draw_text_with_outline((text_x, text_y), channel_text, channel_font, self.style.channel_text, outline_color=(0, 0, 0), outline_width=2)
        return target_width
    def compose(self, main_hook, setup, revenge_line, extra_detail, profile_pic_path):
        profile_width = self._draw_profile_section(profile_pic_path, CHANNEL_NAME); text_area_width = self.style.width - profile_width - self.style.left_margin - self.style.right_margin; total_words = sum(count_words(t) for t in [main_hook, setup, revenge_line, extra_detail]); self._adjust_for_perfect_fill(main_hook, setup, revenge_line, extra_detail, text_area_width, total_words)
        revenge_area_height = 140; total_height = self._calculate_total_height_needed(main_hook, setup, revenge_line, extra_detail, text_area_width); available_height = self.style.height - self.style.bottom_margin - revenge_area_height; y = max(self.style.top_margin, (available_height - total_height) // 2)
        for line_parts in self._wrap_text_smart(main_hook.upper(), self.font_title, text_area_width): self._draw_highlighted_text_line(line_parts, (self.style.left_margin, y), self.font_title); y += self._text_height(self.font_title) + self.current_line_spacing
        y += self.current_section_spacing
        for line_parts in self._wrap_text_smart(setup.upper(), self.font_normal, text_area_width): self._draw_highlighted_text_line(line_parts, (self.style.left_margin, y), self.font_normal); y += self._text_height(self.font_normal) + self.current_line_spacing
        y += self.current_section_spacing
        if extra_detail:
            for line_parts in self._wrap_text_smart(extra_detail.upper(), self.font_normal, text_area_width): self._draw_highlighted_text_line(line_parts, (self.style.left_margin, y), self.font_normal); y += self._text_height(self.font_normal) + self.current_line_spacing
        self._draw_revenge_text_with_background_bottom(revenge_line, profile_width)

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_thumbnail_generation(story_text, profile_photo_path, output_dir, worker_project_id):
    """Secret Manager'dan anahtar okuyarak Gemini API kullanır."""
    logger.info("--- YouTube Küçük Resmi Üretim Modülü Başlatıldı (Gemini API Key) ---")
    
    if not load_api_keys_from_secret_manager(worker_project_id):
        raise Exception("Thumbnail üretimi için Gemini API anahtarları yüklenemedi.")
    
    clean_story = clean_story_text(story_text)
    logger.info(f"📝 Hikaye metni temizlendi: {len(clean_story)} karakter")
    
    parts = None
    max_retries = 5
    logger.info("🤖 Gemini ile thumbnail metni üretiliyor...")
    
    for attempt in range(max_retries):
        logger.info(f"🔄 Deneme {attempt + 1}/{max_retries}")
        try:
            current_parts = ask_gemini(build_prompt(clean_story))
            if current_parts is None:
                # ask_gemini artık hata durumunda exception fırlatıyor, bu blok nadiren çalışır
                logger.error(f"❌ Gemini'den yanıt alınamadı (deneme {attempt + 1})")
                continue
            
            total_words = sum(count_words(v) for v in current_parts.values())
            logger.info(f"📊 Toplam kelime sayısı: {total_words}")
            
            if 80 <= total_words <= 100:
                parts = current_parts
                logger.info(f"✅ İdeal kelime sayısında metin üretildi: {total_words} kelime")
                break
            elif 70 <= total_words <= 110:
                parts = current_parts
                logger.warning(f"⚠️ Kabul edilebilir kelime sayısında metin: {total_words} kelime")
                break
            else:
                logger.warning(f"⚠️ Kelime sayısı hedef dışında: {total_words} (hedef: 80-100)")
        except Exception as e:
            logger.error(f"❌ Gemini çağrısı sırasında hata (deneme {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise e # Son denemede hatayı yukarıya fırlat
            continue
    
    if parts is None:
        logger.error("❌ Tüm denemelere rağmen Gemini ile metin üretilemedi.")
        raise Exception("Thumbnail metni üretilemedi, video üretimi durduruluyor.")
    
    logger.info("\n📋 Üretilen thumbnail metinleri:")
    for key, value in parts.items():
        word_count = count_words(value)
        logger.info(f"  {key}: {word_count} kelime - {value[:50]}...")
    
    logger.info("\n🎨 Thumbnail canvas oluşturuluyor...")
    
    try:
        canvas = ThumbnailCanvas(STYLE)
        logger.info("✅ Canvas başarıyla oluşturuldu")
        logger.info("🖼️ Thumbnail compose ediliyor...")
        canvas.compose(
            main_hook=parts.get("MAIN_HOOK", ""),
            setup=parts.get("SETUP", ""),
            revenge_line=parts.get("REVENGE_LINE", "REVENGE"),
            extra_detail=parts.get("EXTRA_DETAIL", ""),
            profile_pic_path=profile_photo_path,
        )
        logger.info("✅ Thumbnail compose başarılı")
        
        thumbnail_path = os.path.join(output_dir, "kucuk_resim.png")
        canvas.image.save(thumbnail_path, "PNG", quality=95)
        logger.info(f"💾 Thumbnail kaydedildi: {thumbnail_path}")
        
        file_size = os.path.getsize(thumbnail_path)
        logger.info(f"📏 Dosya boyutu: {file_size / 1024:.1f} KB")
        
        logger.info("✅ Thumbnail üretimi tamamlandı!")
        return thumbnail_path
        
    except Exception as e:
        logger.error(f"❌ Thumbnail oluşturma/kaydetme hatası: {e}", exc_info=True)
        raise Exception(f"Thumbnail oluşturamadı: {e}")
