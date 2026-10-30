# -*- coding: utf-8 -*-
"""Depoya GIRMEYEN gizli dosyalari uretir (her derlemeden once bir kez)."""
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
        if "--dogrulama-yazdir" in a:
            print(hk.hex())
            return
    if len(hk) != 32:
        sys.exit("HATA: dogrulama anahtari 64 hex karakter olmali")
    mask = os.urandom(32)
    A, B = bytes(x ^ y for x, y in zip(hk, mask)).hex(), mask.hex()
    with open(os.path.join(ROOT, "masaustu", "lisans_anahtar.py"), "w", encoding="utf-8") as f:
        f.write(f'# OTOMATIK URETILDI - DEPOYA EKLEMEYIN\nSK_A = bytes.fromhex("{A}")\nSK_B = bytes.fromhex("{B}")\n')
    with open(os.path.join(ROOT, "android", "app", "java", "com", "mgm", "bms", "LicenseKey.java"), "w", encoding="utf-8") as f:
        f.write(f'package com.mgm.bms;\n\n// OTOMATIK URETILDI - DEPOYA EKLEMEYIN\nfinal class LicenseKey {{\n    static final String A = "{A}";\n    static final String B = "{B}";\n}}\n')
    print("Gizli dosyalar olusturuldu")


if __name__ == "__main__":
    main()
