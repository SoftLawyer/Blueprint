# profilfotonunarkasinisiler.py

import os
from rembg import remove, new_session
from PIL import Image
import numpy as np
import cv2 # OpenCV kütüphanesi
import io

# --- SİZİN ORİJİNAL YARDIMCI FONKSİYONLARINIZ ---
# Bu fonksiyonlar, sizin yazdığınız gibi yüz, ten ve saç algılama işlemlerini yapar.
# Bu fonksiyonlara HİÇ dokunulmamıştır.

def detect_skin_color(image_array):
    """Ten rengini algıla - çok hassas"""
    try:
        r, g, b = image_array[:, :, 0], image_array[:, :, 1], image_array[:, :, 2]
        skin_masks = [
            (r > 180) & (g > 140) & (b > 120) & (r > g) & (g > b),
            (r > 120) & (g > 80) & (b > 60) & (r > g) & (g >= b) & (r < 220),
            (r > 80) & (g > 60) & (b > 40) & (r > g) & (g >= b) & (r < 160),
            (r > 160) & (g > 120) & (b > 100) & (r > g) & (r > b) & (g > b),
            (r > 140) & (g > 120) & (b > 80) & (r > g) & (g > b) & (r < 200),
        ]
        skin_mask = np.zeros(image_array.shape[:2], dtype=bool)
        for mask in skin_masks:
            skin_mask |= mask
        return skin_mask
    except Exception as e:
        print(f"❌ Ten rengi algılama hatası: {e}")
        return np.zeros(image_array.shape[:2], dtype=bool)

def detect_face_region_advanced(image_array):
    """Gelişmiş yüz bölgesi algılama"""
    try:
        height, width = image_array.shape[:2]
        skin_mask = detect_skin_color(image_array)
        center_x, center_y = width // 2, height // 2
        y_indices, x_indices = np.ogrid[:height, :width]
        face_ellipse = ((x_indices - center_x) ** 2 / (width * 0.3) ** 2 + (y_indices - center_y * 0.8) ** 2 / (height * 0.35) ** 2) <= 1
        neck_ellipse = ((x_indices - center_x) ** 2 / (width * 0.2) ** 2 + (y_indices - center_y * 1.3) ** 2 / (height * 0.2) ** 2) <= 1
        face_region = (face_ellipse | neck_ellipse) & skin_mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        face_region = cv2.morphologyEx(face_region.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        face_region = cv2.dilate(face_region, kernel, iterations=1)
        return face_region.astype(bool)
    except Exception as e:
        print(f"❌ Gelişmiş yüz algılama hatası: {e}")
        return np.zeros(image_array.shape[:2], dtype=bool)

def detect_hair_regions_safe(image_array, face_region):
    """Yüz bölgesini koruyarak saç algılama"""
    try:
        r, g, b = image_array[:, :, 0], image_array[:, :, 1], image_array[:, :, 2]
        hair_masks = [
            (r < 80) & (g < 80) & (b < 80),
            ((r > 60) & (r < 120) & (g > 40) & (g < 100) & (b > 20) & (b < 80) & (r > g) & (g >= b)),
            ((r > 120) & (g > 100) & (b < 100) & (r > g) & (g > b)),
            ((r > 80) & (r < 150) & (abs(r.astype(int) - g.astype(int)) < 20) & (abs(g.astype(int) - b.astype(int)) < 20)),
        ]
        hair_mask = np.zeros(image_array.shape[:2], dtype=bool)
        for mask in hair_masks:
            hair_mask |= mask
        hair_mask = hair_mask & ~face_region
        height = image_array.shape[0]
        upper_region = np.zeros_like(hair_mask)
        upper_region[:int(height * 0.7), :] = True
        hair_mask = hair_mask & upper_region
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        hair_mask = cv2.morphologyEx(hair_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        return hair_mask.astype(bool)
    except Exception as e:
        print(f"❌ Güvenli saç algılama hatası: {e}")
        return np.zeros(image_array.shape[:2], dtype=bool)

def smart_face_preserving_cleanup(input_path, output_path):
    """Yüzü koruyarak akıllı temizlik"""
    try:
        print(f"🔄 Yüz koruyucu temizlik başlıyor: {input_path}")
        with open(input_path, 'rb') as input_file:
            input_data = input_file.read()
        
        session = new_session('u2net_human_seg')
        output_data = remove(input_data, session=session)
        
        image = Image.open(io.BytesIO(output_data)).convert("RGBA")
        img_array = np.array(image)
        
        face_region = detect_face_region_advanced(img_array)
        hair_regions = detect_hair_regions_safe(img_array, face_region)
        skin_regions = detect_skin_color(img_array)
        
        r, g, b, a = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2], img_array[:, :, 3]
        
        hair_light_mask = hair_regions & (r > 160) & (g > 160) & (b > 160)
        hair_light_mask = hair_light_mask & ~face_region & ~skin_regions
        
        img_array[hair_light_mask, 3] = 0
        print(f"🧹 Saç bölgelerinde {np.sum(hair_light_mask)} piksel temizlendi")
        
        alpha = img_array[:, :, 3]
        hair_edges = hair_regions & (alpha > 0) & (alpha < 255) & ~face_region
        
        if np.any(hair_edges):
            alpha_smooth = cv2.GaussianBlur(alpha, (3, 3), 0)
            alpha[hair_edges] = alpha_smooth[hair_edges]
        
        img_array[:, :, 3] = alpha
        
        result_image = Image.fromarray(img_array)
        result_image.save(output_path)
        
        print(f"✅ Yüz koruyucu temizlik tamamlandı: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Yüz koruyucu temizlik hatası: {e}")
        return False

def ultra_safe_cleanup(input_path, output_path):
    """Ultra güvenli temizlik - yüz hiç dokunulmaz"""
    temp_path = None
    try:
        print(f"🔄 Ultra güvenli temizlik başlıyor: {input_path}")
        
        # ✅ DEĞİŞİKLİK: Cloud Run için /tmp klasörü kullan
        temp_path = os.path.join("/tmp", f"temp_safe_{os.getpid()}_{int(time.time())}.png")
        
        if not smart_face_preserving_cleanup(input_path, temp_path):
            return False
        
        image = Image.open(temp_path).convert("RGBA")
        img_array = np.array(image)
        
        face_region = detect_face_region_advanced(img_array)
        skin_regions = detect_skin_color(img_array)
        
        safety_mask = face_region | skin_regions
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
        safety_mask = cv2.dilate(safety_mask.astype(np.uint8), kernel, iterations=2)
        safety_mask = safety_mask.astype(bool)
        
        r, g, b, a = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2], img_array[:, :, 3]
        
        very_light = (r > 200) & (g > 200) & (b > 200)
        cleanup_mask = very_light & ~safety_mask & (a > 0)
        
        img_array[cleanup_mask, 3] = 0
        print(f"🛡️ Güvenlik maskesi dışında {np.sum(cleanup_mask)} piksel temizlendi")
        
        result_image = Image.fromarray(img_array)
        result_image.save(output_path)
        
        print(f"✅ Ultra güvenli temizlik tamamlandı: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Ultra güvenli temizlik hatası: {e}")
        return False
    finally:
        # ✅ DEĞİŞİKLİK: Finally bloğunda geçici dosyayı temizle
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"🗑️ Geçici dosya temizlendi: {temp_path}")
            except Exception as cleanup_error:
                print(f"⚠️ Geçici dosya temizlenirken hata: {cleanup_error}")

# --- ANA İŞ AKIŞI FONKSİYONU ---
def run_background_removal(input_path, output_dir):
    """
    Bu ana fonksiyon, main.py tarafından çağrılır ve tüm süreci yönetir.
    Sizin orijinal "ultra_safe_cleanup" ve yedekleme mantığınızı korur.
    """
    print("--- Fotoğraf Arka Plan Temizleme Modülü Başlatıldı ---")
    
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Girdi dosyası bulunamadı: {input_path}")
        
    output_path_file = os.path.join(output_dir, "profilfoto.png")
    
    print(f"🎯 İşlenecek dosya: {input_path}")
    print(f"🔄 Profil fotoğrafı oluşturuluyor...")
    
    # Sizin orijinal kodunuzdaki gibi, en iyi sonucu veren ultra güvenli temizliği önce dene
    if ultra_safe_cleanup(input_path, output_path_file):
        print(f"✅ Profil fotoğrafı başarıyla oluşturuldu: {output_path_file}")
        return output_path_file
    else:
        print(f"❌ Ultra güvenli temizlik başarısız oldu!")
        # Alternatif olarak yüz koruyucu temizliği dene
        print(f"🔄 Alternatif yöntem (smart cleanup) deneniyor...")
        if smart_face_preserving_cleanup(input_path, output_path_file):
            print(f"✅ Profil fotoğrafı alternatif yöntemle oluşturuldu: {output_path_file}")
            return output_path_file
        else:
            print(f"❌ Profil fotoğrafı hiçbir yöntemle oluşturulamadı!")
            raise Exception("Arka plan temizlenemedi.")
