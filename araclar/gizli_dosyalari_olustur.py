# -*- coding: utf-8 -*-
"""Depoya GİRMEYEN gizli dosyaları üretir (her derlemeden önce bir kez):

  masaustu/lisans_anahtar.py                         – kısa anahtar doğrulama anahtarı (masaüstü)
  android/app/java/com/mgm/bms/LicenseKey.java       – aynısı (Android)

Kaynak (biri yeterli):
  python araclar/gizli_dosyalari_olustur.py                          → lisans-uretici/gizli_anahtar.key okunur
  python araclar/gizli_dosyalari_olustur.py --dogrulama <64 hex>     → yalnızca doğrulama anahtarı (GitHub Actions için)
  ortam değişkeni MGM_DOGRULAMA_ANAHTARI=<64 hex>

Doğrulama anahtarı ile lisans ÜRETİLEBİLİR (kısa anahtarlar HMAC'tir); bu yüzden bu dosyalar asla depoya girmez.
Ed25519 gizli anahtarı (gizli_anahtar.key) ise yalnızca --dogrulama-yazdir ile doğrulama anahtarını türetmek için okunur.
"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
      try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    hk = None
    if "--dogrulama" in a:
        hk = bytes.fromhex(a[a.index("--dogrulama") + 1].strip())
    elif os.environ.get("MGM_DOGRULAMA_ANAHTARI"):
        hk = bytes.fromhex(os.environ["MGM_DOGRULAMA_ANAHTARI"].strip())
    else:
        p = os.path.join(ROOT, "lisans-uretici", "gizli_anahtar.key")
        if not os.path.exists(p):
            sys.exit("HATA: lisans-uretici/gizli_anahtar.key yok (ya da --dogrulama <hex> verin)")
        seed = bytes.fromhex(open(p).read().strip())
        hk = hashlib.sha256(b"MGMBMS-SHORT-KEY|" + seed).digest()
        if "--dogrulama-yazdir" in a:      # GitHub Secret'a girilecek değer
            print(hk.hex())
            return
    if len(hk) != 32:
        sys.exit("HATA: doğrulama anahtarı 32 bayt (64 hex karakter) olmalı")
    mask = os.urandom(32)
    A, B = bytes(x ^ y for x, y in zip(hk, mask)).hex(), mask.hex()
    with open(os.path.join(ROOT, "masaustu", "lisans_anahtar.py"), "w", encoding="utf-8") as f:
        f.write(f'# OTOMATİK ÜRETİLDİ – DEPOYA EKLEMEYİN\nSK_A = bytes.fromhex("{A}")\nSK_B = bytes.fromhex("{B}")\n')
    with open(os.path.join(ROOT, "android", "app", "java", "com", "mgm", "bms", "LicenseKey.java"), "w", encoding="utf-8") as f:
        f.write(f'package com.mgm.bms;\n\n// OTOMATİK ÜRETİLDİ – DEPOYA EKLEMEYİN\nfinal class LicenseKey {{\n    static final String A = "{A}";\n    static final String B = "{B}";\n}}\n')
    print("Gizli dosyalar oluşturuldu: masaustu/lisans_anahtar.py, android/.../LicenseKey.java")


if __name__ == "__main__":
    main()
