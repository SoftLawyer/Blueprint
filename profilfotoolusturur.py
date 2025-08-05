# profilfotoolusturur_v2.py

import requests
from PIL import Image, ImageEnhance
from io import BytesIO
import re
import os
import time
import random

# --- GÜÇLENDİRİLMİŞ PROTAGONIST BİLGİ ÇIKARMA FONKSİYONU ---
# Bu fonksiyon değiştirilmedi, orijinal haliyle çalışıyor.
def extract_protagonist_info(protagonist_profile):
    """Protagonist profilinden isim ve yaş bilgilerini çıkarır - GÜÇLENDİRİLMİŞ VERSİYON"""
    try:
        print("🔍 Protagonist bilgileri çıkarılıyor...")
        print(f"📋 Profil metni (ilk 300 karakter):")
        print(repr(protagonist_profile[:300]))
        
        # ÇOK DAHA ESNEK REGEX PATTERN'LERİ
        name_patterns = [
            r'Name:\s*([A-Za-z\s]+?)(?:\n|Age:|Gender:|Occupation:)',
            r'name:\s*([A-Za-z\s]+?)(?:\n|age:|gender:|occupation:)',
            r'Character Name:\s*([A-Za-z\s]+?)(?:\n|Age:|Gender:)',
            r'Protagonist:\s*([A-Za-z\s]+?)(?:\n|Age:|Gender:|,\s*\d+)',
            r'Main Character:\s*([A-Za-z\s]+?)(?:\n|Age:|Gender:)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:is a|was a|\(age|\,\s*age|\,\s*\d+)',
            r'Meet\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'This is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[\-\,]',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*is\s*(?:a|an)\s*\d+',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(\s*\d+',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*-\s*\d+',
            r'Our protagonist\s*(?:is\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'The main character\s*(?:is\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\w+\s*(?:year|age)',
            r'Protagonist:\s*([^,\n]+)',  # Orijinal pattern - daha esnek
            r'(?:^|\n)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:is|was)',
        ]
        
        age_patterns = [
            r'Age:\s*(\d+)',
            r'age:\s*(\d+)', 
            r'(\d+)\s*years?\s*old',
            r'(\d+)-year-old',
            r'\(age\s*(\d+)\)',
            r'\(\s*(\d+)\s*\)',
            r'\,\s*(\d+)\s*years?\s*old',
            r'\,\s*age\s*(\d+)',
            r'is\s*(\d+)\s*years?\s*old',
            r'was\s*(\d+)\s*years?\s*old',
            r'Protagonist:\s*[^,]+,\s*(\d+)',  # Orijinal pattern
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*,\s*(\d+)',
            r'(\d+)\s*year\s*old',
            r'aged?\s*(\d+)',
            r'at\s*(\d+)\s*years?\s*old',
            r'-\s*(\d+)\s*years?\s*old',
            r'(\d+)\s*yo\b',  # "yo" = years old abbreviation
        ]
        
        # İSİM ARAMA
        extracted_name = None
        for i, pattern in enumerate(name_patterns):
            match = re.search(pattern, protagonist_profile, re.IGNORECASE | re.MULTILINE)
            if match:
                candidate_name = match.group(1).strip()
                # Geçerli isim kontrolü
                if len(candidate_name) >= 2 and len(candidate_name) <= 50 and candidate_name.replace(' ', '').replace('-', '').isalpha():
                    extracted_name = candidate_name
                    print(f"✅ İsim bulundu: '{extracted_name}' (Pattern {i+1})")
                    break
                else:
                    print(f"    ⚠️ Geçersiz isim adayı: '{candidate_name}' (Pattern {i+1})")
        
        # YAŞ ARAMA
        extracted_age = None
        for i, pattern in enumerate(age_patterns):
            match = re.search(pattern, protagonist_profile, re.IGNORECASE)
            if match:
                # Bazı pattern'lerde yaş 2. grupta olabilir
                age_groups = match.groups()
                for group in age_groups:
                    if group and group.isdigit():
                        age_candidate = int(group)
                        # Mantıklı yaş aralığı kontrolü
                        if 18 <= age_candidate <= 80:
                            extracted_age = str(age_candidate)
                            print(f"✅ Yaş bulundu: {extracted_age} (Pattern {i+1})")
                            break
                if extracted_age:
                    break
        
        # SONUÇ DEĞERLENDİRMESİ
        if extracted_name and extracted_age:
            protagonist_info = {
                'name': extracted_name,
                'age': extracted_age
            }
            print(f"✅ Protagonist bilgileri başarıyla çıkarıldı: {protagonist_info}")
            return protagonist_info
        
        # FALLBACK - Manuel arama
        print("⚠️ Regex ile bulunamadı, manuel arama yapılıyor...")
        
        # Basit manuel isim arama
        if not extracted_name:
            # Büyük harfle başlayan kelimeler ara
            words = protagonist_profile.split()
            for i, word in enumerate(words):
                if word and word[0].isupper() and word.isalpha() and len(word) >= 3:
                    # Sonraki kelime de büyük harfle başlıyorsa tam isim olabilir
                    if i + 1 < len(words) and words[i + 1][0].isupper() and words[i + 1].isalpha():
                        candidate_name = f"{word} {words[i + 1]}"
                        if len(candidate_name) <= 30:
                            extracted_name = candidate_name
                            print(f"✅ Manuel isim bulundu: '{extracted_name}'")
                            break
                    elif len(word) >= 4:  # Tek kelime isim
                        extracted_name = word
                        print(f"✅ Manuel tek kelime isim bulundu: '{extracted_name}'")
                        break
        
        # Basit manuel yaş arama
        if not extracted_age:
            # Sayıları ara
            numbers = re.findall(r'\b(\d+)\b', protagonist_profile)
            for num in numbers:
                age_candidate = int(num)
                if 18 <= age_candidate <= 80:
                    extracted_age = num
                    print(f"✅ Manuel yaş bulundu: {extracted_age}")
                    break
        
        # SON KONTROL
        if extracted_name and extracted_age:
            protagonist_info = {
                'name': extracted_name,
                'age': extracted_age
            }
            print(f"✅ Manuel arama ile protagonist bilgileri bulundu: {protagonist_info}")
            return protagonist_info
        
        # ULTRA FALLBACK - Varsayılan değerler
        print("❌ Hiçbir yöntemle protagonist bilgileri bulunamadı!")
        print("🔧 ULTRA FALLBACK: Varsayılan değerler kullanılıyor...")
        
        # Metinde en az bir büyük harf var mı?
        fallback_name = "John Smith"  # Varsayılan isim
        fallback_age = "35"  # Varsayılan yaş
        
        # Son bir deneme - metindeki ilk büyük harfli kelimeyi al
        first_cap_word = re.search(r'\b[A-Z][a-z]+\b', protagonist_profile)
        if first_cap_word:
            fallback_name = first_cap_word.group(0)
        
        protagonist_info = {
            'name': fallback_name,
            'age': fallback_age
        }
        
        print(f"⚠️ FALLBACK protagonist bilgileri: {protagonist_info}")
        print("    (Bu varsayılan değerlerdir - profil formatı tanınmadı)")
        
        return protagonist_info
        
    except Exception as e:
        print(f"❌ Protagonist bilgi çıkarma hatası: {e}")
        print("🔧 HATA FALLBACK: Varsayılan değerler kullanılıyor...")
        return {
            'name': 'John Smith',
            'age': '35'
        }

# --- ÇEŞİTLİLİĞİ ARTIRMAK İÇİN YENİ VE GÜNCELLENMİŞ FONKSİYONLAR ---

def get_optimal_background_for_removal():
    """Arka plan temizleme için en uygun arka plan açıklaması. (Seçenekler artırıldı)"""
    backgrounds = [
        "pure white studio background", "light gray seamless studio background",
        "neutral gray professional backdrop", "clean soft white wall",
        "a slightly out-of-focus office background with soft light",
        "a solid light-blue backdrop"
    ]
    return random.choice(backgrounds)

def get_high_contrast_outfit(background_description):
    """Arka plan rengine göre yüksek kontrastlı kıyafet seçimi. (Seçenekler artırıldı)"""
    if "white" in background_description or "light" in background_description:
        outfits = [
            "dark navy business suit", "charcoal gray blazer with a white shirt", 
            "black turtleneck sweater", "a crisp dark blue dress shirt",
            "a textured charcoal wool suit", "a burgundy v-neck sweater over a collared shirt"
        ]
        return random.choice(outfits)
    else:
        outfits = [
            "crisp white dress shirt with a navy blazer", "light blue dress shirt with a charcoal blazer",
            "a classic black suit with a light gray shirt", "a stylish beige blazer",
            "a light gray business shirt"
        ]
        return random.choice(outfits)

def get_age_appropriate_hair_style(age):
    """Yaşa uygun saç stili. (Seçenekler artırıldı)"""
    if age >= 50:
        styles = [
            "distinguished salt-and-pepper hair, well-groomed",
            "short graying hair, neatly combed",
            "fully gray hair with a professional cut",
            "slightly receding but distinguished hairline"
        ]
        return random.choice(styles)
    elif age >= 40:
        styles = [
            "mature professional haircut with a few gray hairs at the temples",
            "dark hair showing early signs of graying, professionally styled",
            "short, neat haircut, looking experienced",
            "a classic side-parted business haircut"
        ]
        return random.choice(styles)
    else:
        styles = [
            "modern professional business haircut",
            "short dark brown hair, side-parted",
            "neatly styled blonde hair",
            "classic short back and sides haircut",
            "a stylish textured crop haircut"
        ]
        return random.choice(styles)

# YENİ FONKSİYON: Farklı yüz ifadeleri seçer
def get_professional_expression():
    """Profesyonel ama çeşitli yüz ifadeleri listesinden rastgele birini seçer."""
    expressions = [
        "a calm and confident expression",
        "a thoughtful and serious look",
        "a neutral but approachable expression",
        "a focused gaze directly at the camera",
        "a slight, closed-mouth smile suggesting confidence",
        "an engaging and professional expression",
        "a friendly yet professional look"
    ]
    return random.choice(expressions)

# YENİ FONKSİYON: Yüz yapılarında çeşitlilik için etnik köken ekler
def get_random_ethnicity():
    """Farklı coğrafi/etnik köken tanımları listesinden rastgele birini seçer."""
    ethnicities = [
        "a Turkish businessman", "a Mediterranean entrepreneur", "a Northern European professional",
        "an East Asian executive", "a businessman of South Asian descent", "a Black professional",
        "a Latino businessman", "a man with Middle Eastern features", "a Caucasian professional"
    ]
    return random.choice(ethnicities)

def get_minimal_negative_prompt():
    """Mümkün olan en kısa ve etkili negatif istem."""
    # Bu fonksiyon, istenmeyen sonuçları engellemek için önemli olduğundan değiştirilmedi.
    return (
        "blurry, low quality, noise, artifacts, "
        "perfect skin, flawless, airbrushed, retouched, CGI, 3D, plastic, beauty filter, "
        "smile, grin, smirk, lip curve, happiness, joy, cheerful, open mouth, teeth, "
        "patterned background, cluttered, outdoor, "
        "shiny skin, glossy, oily, "
        "ugly, deformed, disfigured, poor details" # Ekstra negatifler
    )

# ANA GÜNCELLEME: Prompt oluşturma fonksiyonu artık çok daha dinamik
def generate_minimal_prompt(protagonist_info):
    """Çeşitliliği artırılmış, dinamik bir istem metni oluşturur."""
    if not protagonist_info: return None
    age = int(protagonist_info['age'])
    
    # Her seferinde rastgele seçimler yapmak için fonksiyonları çağır
    background_desc = get_optimal_background_for_removal()
    outfit_desc = get_high_contrast_outfit(background_desc)
    hair_desc = get_age_appropriate_hair_style(age)
    expression_desc = get_professional_expression()
    ethnicity_desc = get_random_ethnicity()

    # Yeni, dinamik prompt
    prompt = (
        f"Ultra-sharp professional LinkedIn headshot of {protagonist_info['name']}, a {age} year old {ethnicity_desc}. "
        f"Expression: {expression_desc}. "
        f"Appearance: {hair_desc}, wearing a {outfit_desc}. "
        f"Skin: Realistic, natural skin texture with visible pores and slight imperfections, not airbrushed. "
        f"Lighting and Background: Professional studio lighting, on a {background_desc} for easy background removal. "
        f"Quality: Razor-sharp focus, high definition, photorealistic, no blur."
    )
    return prompt

# --- GÖRSEL ÜRETİM VE İŞLEME FONKSİYONLARI ---
# Bu fonksiyonlar değiştirilmedi, orijinal halleriyle çalışıyorlar.

def generate_image(prompt, max_retries=5):
    """Verilen istem metni ile görsel oluşturur."""
    if not prompt: return None
    
    negative_prompt = get_minimal_negative_prompt()
    # URL'ye uygun hale getirme
    full_prompt_for_url = requests.utils.quote(f"{prompt} | {negative_prompt}")
    url = f"https://image.pollinations.ai/prompt/{full_prompt_for_url}"
    
    for attempt in range(max_retries):
        print(f"🖼️ Görsel oluşturma denemesi {attempt + 1}/{max_retries}...")
        try:
            params = {
                'width': 768, 'height': 1024, 'nologo': 'true', 'model': 'flux',
                'seed': int(time.time()) + attempt * 1000 + random.randint(0, 1000), # Ekstra rastgelelik
                'quality': 'ultra', 'sharpness': 'maximum',
                'smile': 'none', 'mouth': 'closed', 'teeth': 'none',
                'perfection': 'false', 'flawless': 'false', 'imperfections': 'true'
            }
            response = requests.get(url, params=params, timeout=120)
            
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                # Bazen API küçük hata görselleri döndürebiliyor, bunu kontrol edelim
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
    """Görseli belirtilen yola kaydeder ve keskinleştirir."""
    if not image: return None
    try:
        # Hafif bir keskinlik artışı
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.1)
        
        full_path = os.path.join(output_dir, filename)
        image.save(full_path, 'PNG')
        print(f"💾 Fotoğraf başarıyla kaydedildi: {full_path}")
        return full_path
    except Exception as e:
        print(f"❌ Fotoğraf kaydedilirken bir hata oluştu: {e}")
        return None

# --- ANA İŞ AKIŞI FONKSİYONU ---
# Bu fonksiyon değiştirilmedi, tüm süreci yönetmeye devam ediyor.
def run_profile_photo_generation(protagonist_profile, output_dir):
    """
    Bu ana fonksiyon, main.py tarafından çağrılır ve tüm süreci yönetir.
    """
    print("--- Profil Fotoğrafı Üretim Modülü Başlatıldı (v2 - Çeşitlilik Artırıldı) ---")
    
    protagonist_info = extract_protagonist_info(protagonist_profile)
    if not protagonist_info:
        raise Exception("Ana karakter bilgileri (isim, yaş) profilden çıkarılamadı.")

    print(f"👤 Ana karakter bilgileri bulundu: {protagonist_info.get('name')}, Yaş: {protagonist_info.get('age')}")
    
    prompt = generate_minimal_prompt(protagonist_info)
    print(f"\nOluşturulan Dinamik İstem: {prompt}\n")
    
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

# --- Örnek Kullanım ---
if __name__ == '__main__':
    # Bu blok, dosya doğrudan çalıştırıldığında test amacıyla kullanılır.
    # Örnek bir karakter profili
    sample_profile = "Meet Alex, a 42-year-old visionary entrepreneur who is leading a tech startup."
    
    # Çıktıların kaydedileceği bir klasör oluştur
    output_directory = "profile_photos"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        
    try:
        # Ana iş akışını çalıştır
        original_path, thumbnail_path = run_profile_photo_generation(sample_profile, output_directory)
        print("\n--- İŞLEM TAMAMLANDI ---")
        print(f"Orijinal Fotoğraf: {original_path}")
        print(f"Küçük Resim: {thumbnail_path}")
    except Exception as e:
        print(f"\n--- BİR HATA OLUŞTU ---")
        print(e)

