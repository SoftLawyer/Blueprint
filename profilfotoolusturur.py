# profilfotoolusturur.py

import requests
from PIL import Image, ImageEnhance
from io import BytesIO
import re
import os
import time
import random

# --- SİZİN ORİJİNAL YARDIMCI FONKSİYONLARINIZ ---
# Bu fonksiyonlar, sizin yazdığınız gibi prompt'ları ve görselleri oluşturur.
# Bu fonksiyonlara HİÇ dokunulmamıştır.

def extract_protagonist_info(protagonist_profile_text):
    """Metin içeriğinden ana karakter bilgilerini çıkarır."""
    protagonist_info = {}
    match = re.search(r'Protagonist:\s*([^,]+),\s*(\d+)', protagonist_profile_text)
    if match:
        protagonist_info['name'] = match.group(1).strip()
        protagonist_info['age'] = match.group(2).strip()
        return protagonist_info
    print("⚠️ Protagonist bilgileri (isim, yaş) profilden çıkarılamadı.")
    return None

def get_optimal_background_for_removal():
    """Arka plan temizleme için en uygun arka plan açıklaması."""
    backgrounds = [
        "pure white studio background", "light gray seamless studio background",
        "neutral gray professional backdrop", "clean soft white wall"
    ]
    return random.choice(backgrounds)

def get_high_contrast_outfit(background_description):
    """Arka plan rengine göre yüksek kontrastlı kıyafet seçimi."""
    if "white" in background_description:
        return random.choice(["dark navy business suit", "charcoal gray blazer", "black turtleneck"])
    else:
        return random.choice(["crisp white dress shirt with navy blazer", "light blue dress shirt with charcoal blazer", "black dress shirt"])

def get_age_appropriate_hair_style(age):
    """Yaşa uygun temel saç stili."""
    if age >= 50:
        return "distinguished salt-and-pepper hair, well-groomed"
    elif age >= 40:
        return "mature professional haircut with a few gray hairs"
    else:
        return "modern professional business haircut"

def get_minimal_negative_prompt():
    """Mümkün olan en kısa ve etkili negatif istem."""
    return (
        "blurry, low quality, noise, artifacts, "
        "perfect skin, flawless, airbrushed, retouched, CGI, 3D, plastic, beauty filter, "
        "smile, grin, smirk, lip curve, happiness, joy, cheerful, open mouth, teeth, "
        "patterned background, cluttered, outdoor, "
        "shiny skin, glossy, oily"
    )

def generate_minimal_prompt(protagonist_info):
    """Olabildiğince sadeleştirilmiş bir istem metni oluşturur."""
    if not protagonist_info: return None
    age = int(protagonist_info['age'])
    
    background_desc = get_optimal_background_for_removal()
    outfit_desc = get_high_contrast_outfit(background_desc)
    hair_desc = get_age_appropriate_hair_style(age)

    prompt = (
        f"Ultra-sharp professional LinkedIn headshot of {age} year old businessman {protagonist_info['name']}. "
        f"Expression: serious, confident, and professional. A completely neutral facial expression with no hint of a smile. "
        f"Appearance: {hair_desc}, wearing a {outfit_desc}. "
        f"Skin: Realistic, natural skin texture with visible pores and slight imperfections, not airbrushed. "
        f"Lighting and Background: Professional studio lighting, on a {background_desc} for easy background removal. "
        f"Quality: Razor-sharp focus, high definition, no blur."
    )
    return prompt

def generate_image(prompt, max_retries=5):
    """Verilen istem metni ile görsel oluşturur."""
    if not prompt: return None
    
    negative_prompt = get_minimal_negative_prompt()
    full_prompt_for_url = requests.utils.quote(f"{prompt} | {negative_prompt}")
    url = f"https://image.pollinations.ai/prompt/{full_prompt_for_url}"
    
    for attempt in range(max_retries):
        print(f"🖼️ Görsel oluşturma denemesi {attempt + 1}/{max_retries}...")
        try:
            params = {
                'width': 768, 'height': 1024, 'nologo': 'true', 'model': 'flux',
                'seed': int(time.time()) + attempt * 1000, 'quality': 'ultra', 'sharpness': 'maximum',
                'smile': 'none', 'mouth': 'closed', 'teeth': 'none',
                'perfection': 'false', 'flawless': 'false', 'imperfections': 'true'
            }
            response = requests.get(url, params=params, timeout=120)
            
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                if img.size[0] > 300:
                    print("✅ Uygun bir görsel bulundu.")
                    if img.mode != 'RGB': img = img.convert('RGB')
                    return img
            else:
                print(f"  - Hata: Sunucu {response.status_code} durum kodu döndürdü.")
        except Exception as e:
            print(f"  - Bir hata oluştu: {e}")
        if attempt < max_retries - 1:
            time.sleep(5)
    
    print("❌ Maksimum deneme sayısına ulaşıldı, uygun görsel bulunamadı.")
    return None

def create_thumbnail_photo(image, target_width=200, target_height=610):
    """Ana görüntüden küçük resim için fotoğraf oluşturur."""
    if not image: return None
    try:
        original_width, original_height = image.size
        aspect_ratio = original_width / original_height
        target_aspect_ratio = target_width / target_height
        
        if aspect_ratio > target_aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)
        
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        thumbnail = Image.new('RGB', (target_width, target_height), (255, 255, 255))
        
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        
        thumbnail.paste(resized_image, (x_offset, y_offset))
        
        print(f"🖼️ Küçük resim için fotoğraf oluşturuldu: {target_width}x{target_height} piksel")
        return thumbnail
    except Exception as e:
        print(f"❌ Küçük resim için fotoğraf oluşturulurken hata: {e}")
        return None

def save_photo(image, output_dir, filename):
    """Görseli geçici belleğe kaydeder."""
    if not image: return None
    try:
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.1)
        full_path = os.path.join(output_dir, filename)
        image.save(full_path, 'PNG')
        print(f"💾 Fotoğraf başarıyla geçici olarak kaydedildi: {full_path}")
        return full_path
    except Exception as e:
        print(f"❌ Fotoğraf kaydedilirken bir hata oluştu: {e}")
        return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_profile_photo_generation(protagonist_profile, output_dir):
    """
    Bu ana fonksiyon, main.py tarafından çağrılır ve tüm süreci yönetir.
    Sizin orijinal main() fonksiyonunuzun mantığını korur.
    """
    print("--- Profil Fotoğrafı Üretim Modülü Başlatıldı ---")
    
    protagonist_info = extract_protagonist_info(protagonist_profile)
    if not protagonist_info:
        raise Exception("Ana karakter bilgileri (isim, yaş) profilden çıkarılamadı.")

    print(f"👤 Ana karakter bilgileri bulundu: {protagonist_info.get('name')}, Yaş: {protagonist_info.get('age')}")
    
    prompt = generate_minimal_prompt(protagonist_info)
    print(f"\nOluşturulan İstem: {prompt}\n")
    
    image = generate_image(prompt)
    if not image:
        raise Exception("Program, geçerli bir profil fotoğrafı oluşturamadı.")
    
    # Ana profil fotoğrafını kaydet
    profile_photo_path = save_photo(image, output_dir, "profilfoto_orijinal.png")
    if not profile_photo_path:
        raise Exception("Orijinal profil fotoğrafı kaydedilemedi.")
        
    # Küçük resim için fotoğraf oluştur ve kaydet
    thumbnail_image = create_thumbnail_photo(image, 200, 610)
    if not thumbnail_image:
        raise Exception("Küçük resim için fotoğraf oluşturulamadı.")
        
    thumbnail_photo_path = save_photo(thumbnail_image, output_dir, "kucukresimicinfoto.png")
    if not thumbnail_photo_path:
        raise Exception("Küçük resim için fotoğraf kaydedilemedi.")

    return profile_photo_path, thumbnail_photo_path
