"""Arka plan animasyonu için videolardan kare çıkarır (geliştirme aracı, sitede kullanılmaz).

frontend/ klasöründeki boga.mp4, stadyum.mp4 ve taraftar.mp4'ten frontend/frames/ altına
sıralı JPG kareler yazar (background.js bunları oynatır). Videolar repoda değildir.
DİKKAT: frontend/frames/ klasörünü önce siler.

  pip install opencv-python
  python tools/extract.py
"""
import os
import shutil
from pathlib import Path

import cv2

# Yollar frontend klasörüne göre (script nereden çalıştırılırsa çalıştırılsın)
os.chdir(Path(__file__).resolve().parents[1] / "frontend")

# İşlenecek videoların sırası (Bu sıra web sitesindeki akış sırasıdır)
video_dosyalari = ["boga.mp4", "stadyum.mp4", "taraftar.mp4"]
hedef_klasor = "frames"

# Eski frames klasörünü temizle (Eski resimlerin araya karışmasını önler)
if os.path.exists(hedef_klasor):
    shutil.rmtree(hedef_klasor)
os.makedirs(hedef_klasor)

global_kare_sayaci = 1

print("Kare çıkarma işlemi başlıyor...\n")

for video_adi in video_dosyalari:
    if not os.path.exists(video_adi):
        print(f"HATA: {video_adi} dosyası bulunamadı! Lütfen dosya adının tam olarak böyle olduğundan emin olun.")
        continue
        
    print(f"{video_adi} işleniyor...")
    cap = cv2.VideoCapture(video_adi)
    
    toplam_kare = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  - Bulunan kare: {toplam_kare}")

    kare_sayaci = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break  # Video bittiğinde döngüden çık

        # Çıktı dosya adı: frame_0001.jpg, frame_0002.jpg şeklinde devam eder
        dosya_adi = os.path.join(hedef_klasor, f"frame_{global_kare_sayaci:04d}.jpg")
        
        # %100 Yüksek (HD) kalitede kaydet
        cv2.imwrite(dosya_adi, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        
        global_kare_sayaci += 1
        kare_sayaci += 1

    cap.release()
    print(f"  - {video_adi} tamamlandı. ({kare_sayaci} kare çıkarıldı)\n")

toplam_cikarilan = global_kare_sayaci - 1
print(f"TÜM İŞLEM TAMAMLANDI! Toplam {toplam_cikarilan} adet yüksek çözünürlüklü görsel 'frames' klasörüne kaydedildi.")