# videoyapar.py

import os
import re
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    ImageClip, TextClip, ColorClip, concatenate_audioclips
)
from moviepy.audio.AudioClip import AudioArrayClip

# --- AYARLAR (Orijinal boyutlar korundu) ---
TEST_MODU = False
PROFIL_FOTO_KONUM_X = 0.5
PROFIL_FOTO_KONUM_Y = 0.12
PROFIL_FOTO_BOYUT = 350
ALTYAZI_KONUM_Y = 0.75
ALTYAZI_FONT_SIZE = 36
ALTYAZI_MAX_GENISLIK_ORANI = 0.9
ISIM_FONT_SIZE = 40
ALTYAZI_ASAGI_KAYDIR = -1.6

# --- YARDIMCI FONKSİYONLAR (Sizin orijinal kodunuzdan, buluta uyarlandı) ---

def kahraman_adini_al(protagonist_profile_text):
    """Verilen profil metninden kahramanın ilk adını okur."""
    try:
        for satir in protagonist_profile_text.splitlines():
            if satir.strip().lower().startswith("protagonist:"):
                icerik = satir.split(":", 1)[1].strip()
                # Örnek: "David Sterling, 32" -> "David"
                isim = icerik.split(",")[0].strip().split(" ")[0]
                print(f"✅ Kahraman adı profilden okundu: {isim}")
                return isim.upper()
        
        # İsim bulunamazsa hata fırlat
        raise Exception("❌ HATA: Profil metninde 'Protagonist:' satırı bulunamadı. Video oluşturulamaz.")
        
    except Exception as e:
        if "Protagonist:" in str(e):
            # Protagonist bulunamadı hatası - direkt fırlat
            raise e
        else:
            # Diğer hatalar için yeni hata mesajı
            raise Exception(f"❌ HATA: Kahraman adı okunurken bir hata oluştu: {e}. Video oluşturulamaz.")

def altyazi_parse(altyazi_dosyasi):
    """SRT dosyasını parse eder ve altyazı listesi döndürür."""
    try:
        with open(altyazi_dosyasi, 'r', encoding='utf-8') as f:
            icerik = f.read().strip()
        bloklar = re.split(r'\n\s*\n', icerik)
        altyazilar = []
        def zaman_to_saniye(zaman_str):
            saat, dakika, saniye_ms = zaman_str.split(':')
            saniye, ms = saniye_ms.split(',')
            return int(saat) * 3600 + int(dakika) * 60 + int(saniye) + int(ms) / 1000
        for blok in bloklar:
            if not blok.strip(): continue
            satirlar = blok.strip().split('\n')
            if len(satirlar) < 2: continue
            
            zaman_satiri_index = next((i for i, s in enumerate(satirlar) if '-->' in s), -1)
            if zaman_satiri_index == -1: continue

            zaman_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', satirlar[zaman_satiri_index])
            if not zaman_match: continue
            
            baslangic = zaman_to_saniye(zaman_match.group(1))
            bitis = zaman_to_saniye(zaman_match.group(2))
            metin = '\n'.join(satirlar[zaman_satiri_index+1:]).strip()
            altyazilar.append({'numara': len(altyazilar) + 1, 'baslangic': baslangic, 'bitis': bitis, 'metin': metin, 'sure': bitis - baslangic})
        
        print(f"📝 {len(altyazilar)} altyazı başarıyla parse edildi")
        return altyazilar
    except Exception as e:
        print(f"❌ Altyazı parse hatası: {e}")
        return []

def altyazi_stili(txt, video_genisligi):
    txt = txt.upper()
    altyazi_max_genislik = int(video_genisligi * ALTYAZI_MAX_GENISLIK_ORANI)
    # Dockerfile'da kurduğumuz fontu kullanıyoruz
    return TextClip(
        txt, fontsize=ALTYAZI_FONT_SIZE, color='white', font='Liberation-Sans-Bold',
        method='caption', align='center', size=(altyazi_max_genislik, None)
    )

def altyazi_clipleri_olustur(altyazilar, video_genisligi, altyazi_y_konum, video_suresi):
    """Her altyazı için ayrı TextClip oluşturur."""
    altyazi_clips = []
    for altyazi in altyazilar:
        if altyazi['baslangic'] >= video_suresi: continue
        try:
            clip = altyazi_stili(altyazi['metin'], video_genisligi)
            sure = min(altyazi['sure'], video_suresi - altyazi['baslangic'])
            clip = clip.set_start(altyazi['baslangic']).set_duration(sure)
            clip = clip.set_position(('center', altyazi_y_konum), relative=True)
            altyazi_clips.append(clip)
        except Exception as e:
            print(f"⚠️  Altyazı #{altyazi.get('numara', '?')} oluşturulamadı: {e}")
            continue
    print(f"📝 Toplam {len(altyazi_clips)} altyazı clip'i oluşturuldu")
    return altyazi_clips

def gradyan_arka_plan_olustur(genislik, yukseklik, ses_suresi):
    gradyan = np.zeros((int(yukseklik), int(genislik), 3), dtype=np.uint8)
    for x in range(int(genislik)):
        ratio = x / genislik
        b = int(10 + ratio * 245)
        gradyan[:, x] = [0, 0, b]
    return ImageClip(gradyan, duration=ses_suresi)

# --- ANA VİDEO OLUŞTURMA FONKSİYONU ---
def run_video_creation(bg_video_path, audio_path, srt_path, profile_photo_path, protagonist_profile, output_dir):
    print("--- Video Birleştirme Modülü Başlatıldı (720p) ---")
    
    # İsim alınırken hata olursa burada durur
    kahraman_adi = kahraman_adini_al(protagonist_profile)
    altyazilar = altyazi_parse(srt_path)
    if not altyazilar: raise Exception("Altyazı dosyası okunamadı veya boş.")

    ses_clip = None
    arkaplan_video = None
    final_clip = None
    
    try:
        ses_clip = AudioFileClip(audio_path)
        altyazi_suresi = altyazilar[-1]['bitis'] if altyazilar else 0
        video_suresi = max(ses_clip.duration, altyazi_suresi)
        
        if TEST_MODU:
            video_suresi = min(10, video_suresi)
            ses_clip = ses_clip.subclip(0, video_suresi)

        print(f"🎬 Final video süresi: {video_suresi:.2f} saniye")

        arkaplan_video = VideoFileClip(bg_video_path)
        if video_suresi > arkaplan_video.duration:
            arkaplan = arkaplan_video.loop(duration=video_suresi)
        else:
            arkaplan = arkaplan_video.set_duration(video_suresi)

        # 720p'ye yeniden boyutlandır
        arkaplan = arkaplan.resize(height=720)

        if ses_clip.duration < video_suresi:
            print(f"🔇 Ses süresi {video_suresi - ses_clip.duration:.2f} saniye uzatılıyor")
            sessizlik = AudioArrayClip(np.zeros((int((video_suresi - ses_clip.duration) * ses_clip.fps), ses_clip.nchannels)), fps=ses_clip.fps)
            ses_clip = concatenate_audioclips([ses_clip, sessizlik])

        arkaplan = arkaplan.set_audio(ses_clip)
        
        video_genislik, video_yukseklik = arkaplan.size
        print(f"📐 Video boyutları: {video_genislik}x{video_yukseklik}")

        altyazi_arka_plan_yukseklik = int(video_yukseklik * 0.3)
        altyazi_arka_plan_y = video_yukseklik - altyazi_arka_plan_yukseklik - 50
        altyazi_arka_plan = ColorClip(
            size=(video_genislik, altyazi_arka_plan_yukseklik),
            color=(0, 0, 0), duration=video_suresi
        ).set_opacity(0.7).set_position(('center', altyazi_arka_plan_y))

        profil_clip = ImageClip(profile_photo_path, duration=video_suresi, ismask=False).resize(height=PROFIL_FOTO_BOYUT)
        profil_genislik = profil_clip.w
        profil_clip = profil_clip.set_position((PROFIL_FOTO_KONUM_X - profil_genislik / (2 * video_genislik), PROFIL_FOTO_KONUM_Y), relative=True)
        
        isim_etiket_yukseklik = 60
        isim_text = TextClip(kahraman_adi, fontsize=ISIM_FONT_SIZE, color='white', font='Liberation-Sans-Bold').set_duration(video_suresi)
        isim_gradyan = gradyan_arka_plan_olustur(profil_genislik, isim_etiket_yukseklik, video_suresi)
        isim_etiket = CompositeVideoClip([isim_gradyan, isim_text.set_position('center')])
        
        isim_y_relatif = (altyazi_arka_plan_y - isim_etiket_yukseklik) / video_yukseklik
        isim_etiket = isim_etiket.set_position((PROFIL_FOTO_KONUM_X - isim_etiket.w / (2 * video_genislik), isim_y_relatif), relative=True)

        altyazi_asagi_kaydir_piksel = altyazi_arka_plan_yukseklik * ALTYAZI_ASAGI_KAYDIR / 10
        altyazi_y_konum = ALTYAZI_KONUM_Y + (altyazi_asagi_kaydir_piksel / video_yukseklik)
        
        altyazi_clips = altyazi_clipleri_olustur(altyazilar, video_genisligi, altyazi_y_konum, video_suresi)

        final_clip = CompositeVideoClip([
            arkaplan,
            altyazi_arka_plan,
            profil_clip,
            isim_etiket,
            *altyazi_clips
        ])
        
        output_video_path = os.path.join(output_dir, "final_video.mp4")
        
        # --- DOSYA BOYUTUNU OPTİMİZE ETMEK İÇİN GÜNCELLENMİŞ KOD ---
        available_threads = os.cpu_count() or 4
        print(f"⚙️ Video render işlemi için {available_threads} CPU çekirdeği kullanılacak.")
        
        final_clip.write_videofile(
            output_video_path,
            codec="libx264",
            audio_codec="aac",
            bitrate="4000k",  # 720p video için kaliteyi koruyan makul bir bitrate
            fps=24,
            threads=available_threads,
            preset="slow", # Daha yavaş ama daha verimli sıkıştırma
            logger='bar'
        )
        # --- GÜNCELLEME SONU ---
        
        print(f"✅ Video başarıyla oluşturuldu (720p): {output_video_path}")
        return output_video_path

    except Exception as e:
        print(f"❌ Video oluşturulurken kritik bir hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        raise Exception("Video oluşturulamadı.")
    finally:
        # Kaynakları temizle
        if ses_clip: ses_clip.close()
        if arkaplan_video: arkaplan_video.close()
        if final_clip: final_clip.close()
        print("🧹 Video kaynakları temizlendi.")
