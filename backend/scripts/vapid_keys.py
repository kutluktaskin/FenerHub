"""Web Push için VAPID anahtar çifti üretir (bir kez çalıştırılır).

Çıktıdaki iki değeri Render > Environment'a ekle: VAPID_PUBLIC_KEY ve VAPID_PRIVATE_KEY.
Özel anahtarı git'e, koda ya da frontend'e yazma. Anahtar değişirse eski abonelikler geçersiz olur.
Kullanım: python scripts/vapid_keys.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(f"VAPID_PUBLIC_KEY={b64(public)}")
print(f"VAPID_PRIVATE_KEY={b64(private)}")
