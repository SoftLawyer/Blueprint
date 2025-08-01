import os
import io
import tempfile
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

app = Flask(__name__)

class VideoFabrikasi:
    def __init__(self):
        # 720p çözünürlük
        self.width = 1280
        self.height = 720
        self.fps = 30
        
        # Tek font yükle
        self.fonts = self._load_fonts()
    
    def _load_fonts(self):
        """Liberation Sans font yükle - cache yok"""
        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        
        try:
            if os.path.exists(font_path):
                return {
                    "bold": ImageFont.truetype(font_path, 28),      # 720p için
                    "regular": ImageFont.truetype(font_path, 20),   # 720p için
                    "small": ImageFont.truetype(font_path, 16)
                }
        except Exception as e:
            print(f"Font yükleme hatası: {e}")
        
        # Fallback - default font
        return {
            "bold": ImageFont.load_default(),
            "regular": ImageFont.load_default(), 
            "small": ImageFont.load_default()
        }
    
    def _wrap_text(self, text, font, max_width):
        """Metni satırlara böl - 720p için optimize"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def create_video_frame(self, text, frame_number, total_frames):
        """720p video frame oluştur"""
        # 720p canvas
        frame = Image.new('RGB', (self.width, self.height), color='#1a1a1a')
        draw = ImageDraw.Draw(frame)
        
        # 720p için pozisyonlar
        margin_x = 80
        margin_y = 60
        content_width = self.width - (2 * margin_x)
        
        # Text wrapping
        lines = self._wrap_text(text, self.fonts["regular"], content_width)
        
        # Başlangıç Y pozisyonu
        start_y = margin_y + 50
        line_height = 35  # 720p için
        
        # Her satırı çiz
        for i, line in enumerate(lines):
            y_pos = start_y + (i * line_height)
            
            # Ekran sınırları içinde mi kontrol et
            if y_pos < self.height - margin_y:
                draw.text((margin_x, y_pos), line, 
                         font=self.fonts["regular"], 
                         fill='white')
        
        # PIL Image'ı OpenCV formatına çevir
        frame_cv = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
        return frame_cv
    
    def create_video(self, text, duration=10):
        """720p video oluştur"""
        total_frames = duration * self.fps
        
        # Geçici video dosyası
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Video writer - 720p
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_path, fourcc, self.fps, (self.width, self.height))
        
        try:
            # Frame'leri oluştur
            for frame_num in range(total_frames):
                frame = self.create_video_frame(text, frame_num, total_frames)
                out.write(frame)
            
            out.release()
            return temp_path
            
        except Exception as e:
            out.release()
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

# Global instance
video_fabrikasi = VideoFabrikasi()

@app.route('/', methods=['POST'])
def create_video():
    try:
        data = request.get_json() or {}
        text = data.get('text', 'Merhaba Dünya! Bu bir test videosudur.')
        duration = min(int(data.get('duration', 10)), 30)  # Max 30 saniye
        
        # Video oluştur
        video_path = video_fabrikasi.create_video(text, duration)
        
        # Video dosyasını gönder
        def remove_file(response):
            try:
                os.unlink(video_path)
            except:
                pass
            return response
        
        return send_file(
            video_path,
            as_attachment=True,
            download_name=f'video_{duration}s.mp4',
            mimetype='video/mp4'
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'resolution': '720p'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
