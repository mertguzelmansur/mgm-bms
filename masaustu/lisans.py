# -*- coding: utf-8 -*-
"""MGM BMS – lisans doğrulama.

Her kurulum bir Cihaz Kimliği gösterir (Windows'ta MachineGuid'den türetilir). Lisans anahtarı bu kimliğe
özeldir ve MGM'nin gizli anahtarıyla Ed25519 dijital imzasıyla imzalanmıştır. Program yalnızca açık anahtarı
içerir: anahtarı doğrulayabilir ama yenisini üretemez.

Anahtar biçimi:  MGM1-<base32( yük || imza )>
  yük = sürüm(1) | cihaz(10) | verilme_günü(2) | bitiş_günü(2, 0=süresiz) | ad_uzunluğu(1) | ad(utf-8, ≤40)
  imza = Ed25519( "MGMBMS-LIC" || yük )  (64 bayt)
Günler 2024-01-01'den itibaren sayılır.
"""
import base64
import datetime as dt
import hashlib
import os
import struct
import sys

# --------------------------------------------------------------------------- açık anahtar (gizli anahtar programda YOK)
PUBLIC_KEY_HEX = "1fc74cf8d65e33d596138f11eed649d83f36350ccde6746b9e2926c8382bbca4"

DOMAIN = b"MGMBMS-LIC"
# kısa anahtar / fabrika kodu doğrulama anahtarı (HMAC): depoda YOK, lisans_anahtar.py dosyasındadır
# (araclar/gizli_dosyalari_olustur.py üretir, .gitignore ile depo dışında tutulur)
try:
    from lisans_anahtar import SK_A as _SK_A, SK_B as _SK_B
except ImportError:
    _SK_A = _SK_B = None
SHORT_DOMAIN = b"MGMBMS-SHORT"
EPOCH = dt.date(2024, 1, 1)

# --------------------------------------------------------------------------- Ed25519 (RFC 8032, saf Python)
_p = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _inv(x):
    return pow(x, _p - 2, _p)


def _add(P, Q):
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q
    A = (Y1 - X1) * (Y2 - X2) % _p
    B = (Y1 + X1) * (Y2 + X2) % _p
    C = T1 * 2 * _d * T2 % _p
    D = Z1 * 2 * Z2 % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _recover_x(y, sign):
    if y >= _p:
        return None
    x2 = (y * y - 1) * _inv(_d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _I % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * _inv(5) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _compress(P):
    zi = _inv(P[2])
    x, y = P[0] * zi % _p, P[1] * zi % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_from_secret(secret: bytes) -> bytes:
    a, _ = _secret_expand(secret)
    return _compress(_mul(a, _G))


def sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _secret_expand(secret)
    A = _compress(_mul(a, _G))
    r = _h(prefix + msg) % _L
    R = _compress(_mul(r, _G))
    k = _h(R + A + msg) % _L
    return R + int.to_bytes((r + k * a) % _L, 32, "little")


def verify(public: bytes, msg: bytes, sig: bytes) -> bool:
    if len(public) != 32 or len(sig) != 64:
        return False
    A = _decompress(public)
    R = _decompress(sig[:32])
    if not A or not R:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = _h(sig[:32] + public + msg) % _L
    return _eq(_mul(s, _G), _add(R, _mul(k, A)))


# --------------------------------------------------------------------------- cihaz kimliği
def _b32(b):
    return base64.b32encode(b).decode().rstrip("=")


def _unb32(s):
    s = s.upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def _raw_machine_id():
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                               winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0))
            v, _ = winreg.QueryValueEx(k, "MachineGuid")
            return "win:" + str(v).strip().lower()
        except Exception:
            pass
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = open(p).read().strip()
            if v:
                return "linux:" + v
        except Exception:
            pass
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return "mac:" + line.split('"')[-2]
        except Exception:
            pass
    import uuid
    return "node:%012x" % uuid.getnode()


def device_bytes(raw=None, platform="pc"):
    raw = raw if raw is not None else _raw_machine_id()
    return hashlib.sha256(f"MGM-BMS|{platform}|{raw}".encode()).digest()[:10]


def format_device(b: bytes) -> str:
    s = _b32(b)          # 10 bayt → 16 karakter
    return "MGM-" + "-".join(s[i:i + 4] for i in range(0, 16, 4))


def parse_device(text: str) -> bytes:
    s = "".join(ch for ch in text.upper() if ch.isalnum())
    if s.startswith("MGM"):
        s = s[3:]
    if len(s) != 16:
        raise ValueError("Cihaz Kimliği 16 karakter olmalı (MGM-XXXX-XXXX-XXXX-XXXX)")
    return _unb32(s)


def device_id():
    return format_device(device_bytes())


# --------------------------------------------------------------------------- anahtar
def _days(d):
    return (d - EPOCH).days


def make_payload(dev: bytes, name: str, issued: dt.date, expires: dt.date = None) -> bytes:
    nb = name.strip().encode("utf-8")[:40]
    return struct.pack("<B10sHHB", 1, dev, _days(issued), _days(expires) if expires else 0, len(nb)) + nb


def encode_key(payload: bytes, sig: bytes) -> str:
    s = _b32(payload + sig)
    return "MGM1-" + "-".join(s[i:i + 8] for i in range(0, len(s), 8))


def decode_key(text: str):
    s = "".join(ch for ch in text.upper() if ch.isalnum())
    if not s.startswith("MGM1"):
        raise ValueError("Anahtar tanınmadı – XXXX-XXXX biçiminde olmalı")
    raw = _unb32(s[4:])
    if len(raw) < 16 + 64:
        raise ValueError("Anahtar eksik ya da hatalı kopyalanmış")
    payload, sig = raw[:-64], raw[-64:]
    ver, dev, iss, exp, n = struct.unpack("<B10sHHB", payload[:16])
    if ver != 1 or len(payload) != 16 + n:
        raise ValueError("Anahtar biçimi tanınmadı")
    return {"payload": payload, "sig": sig, "device": dev, "issued": EPOCH + dt.timedelta(days=iss),
            "expires": EPOCH + dt.timedelta(days=exp) if exp else None, "name": payload[16:].decode("utf-8", "replace")}


def check_key(text: str, dev: bytes = None, public_hex: str = None, today: dt.date = None):
    """Anahtarı doğrular. Geçerliyse bilgi sözlüğü döndürür, değilse ValueError fırlatır."""
    k = decode_key(text)
    pub = bytes.fromhex(public_hex or PUBLIC_KEY_HEX)
    if not verify(pub, DOMAIN + k["payload"], k["sig"]):
        raise ValueError("Geçersiz lisans anahtarı")
    if k["device"] != (dev if dev is not None else device_bytes()):
        raise ValueError("Bu anahtar başka bir cihaz için üretilmiş")
    if k["expires"] and (today or dt.date.today()) > k["expires"]:
        raise ValueError(f"Lisans süresi {k['expires']:%d.%m.%Y} tarihinde doldu")
    return {"name": k["name"], "issued": k["issued"].isoformat(),
            "expires": k["expires"].isoformat() if k["expires"] else None}


# --------------------------------------------------------------------------- saklama
# --------------------------------------------------------------------------- kısa anahtar / fabrika kodu
# 12 bayt → 20 karakter "XXXXX-XXXXX-XXXXX-XXXXX"
#   MAC(9) | başlık(3) XOR SHA256(MAC)[:3]     başlık = tür(1: 1=cihaz, 2=fabrika) | bitiş_günü(2, 0=süresiz)
#   MAC = HMAC-SHA256(...)[:9]
#   HMAC girdisi: "MGMBMS-SHORT" | tür | bitiş | (cihaz 10 bayt – yalnızca tür 1)
SHORT_DEVICE, SHORT_FACTORY = 1, 2


def short_hmac_key_from_secret(secret: bytes) -> bytes:
    import hashlib as _h
    return _h.sha256(b"MGMBMS-SHORT-KEY|" + secret).digest()


def _short_key():
    if not _SK_A:
        raise ValueError("Bu kopya kısa anahtar doğrulaması olmadan derlenmiş (lisans_anahtar.py eksik)")
    return bytes(a ^ b for a, b in zip(_SK_A, _SK_B))


def _short_mac(hk, kind, exp_day, dev):
    import hmac as _hm
    msg = SHORT_DOMAIN + bytes([kind]) + struct.pack("<H", exp_day) + (dev if kind == SHORT_DEVICE else b"")
    return _hm.new(hk, msg, "sha256").digest()[:9]


def make_short(secret: bytes, dev: bytes = None, expires: dt.date = None) -> str:
    kind = SHORT_DEVICE if dev else SHORT_FACTORY
    e = _days(expires) if expires else 0
    mac = _short_mac(short_hmac_key_from_secret(secret), kind, e, dev)
    raw = mac + _xor3(bytes([kind]) + struct.pack("<H", e), mac)
    s = _b32(raw)                                   # 20 karakter
    return "-".join(s[i:i + 5] for i in range(0, 20, 5))


def _xor3(head, mac):
    import hashlib as _h
    w = _h.sha256(mac).digest()[:3]
    return bytes(a ^ b for a, b in zip(head, w))


def _clean_short(text):
    s = "".join(ch for ch in text.upper() if ch.isalnum())
    return s.translate(str.maketrans("0189", "OIBG"))   # karıştırılan karakterler


def is_short(text):
    s = _clean_short(text)
    return len(s) == 20 and not s.startswith("MGM1")


def check_short(text: str, dev: bytes = None, today: dt.date = None):
    import hmac as _hm
    s = _clean_short(text)
    if len(s) != 20:
        raise ValueError("Anahtar 8 karakter olmalı (XXXX-XXXX)")
    try:
        raw = _unb32(s)[:12]
    except Exception:
        raise ValueError("Anahtarda geçersiz karakter var")
    if _b32(raw) != s:
        raise ValueError("Geçersiz lisans anahtarı")
    mac, head = raw[:9], _xor3(raw[9:12], raw[:9])
    kind, e = head[0], struct.unpack("<H", head[1:3])[0]
    dev = dev if dev is not None else device_bytes()
    if kind not in (SHORT_DEVICE, SHORT_FACTORY) or not _hm.compare_digest(mac, _short_mac(_short_key(), kind, e, dev)):
        raise ValueError("Geçersiz lisans anahtarı" if kind != SHORT_DEVICE else
                         "Geçersiz anahtar ya da başka bir cihaz için üretilmiş")
    exp = EPOCH + dt.timedelta(days=e) if e else None
    if exp and (today or dt.date.today()) > exp:
        raise ValueError(f"Lisans süresi {exp:%d.%m.%Y} tarihinde doldu")
    return {"name": "Fabrika lisansı" if kind == SHORT_FACTORY else "Cihaz lisansı", "issued": None,
            "expires": exp.isoformat() if exp else None, "factory": kind == SHORT_FACTORY}


# --------------------------------------------------------------------------- 8 karakterlik anahtar "XXXX-XXXX"
# 5 bayt: MAC(4) | ay XOR SHA256(MAC)[0]
#   ay = 0 süresiz, aksi halde bitiş ayı (1 = Ocak 2024 … 255 = Mart 2045); o ayın son gününe kadar geçerli
#   MAC = HMAC-SHA256(k, "MGMBMS-K8" | tür | ay | cihaz(yalnızca tür 1))[:4]   tür: 1 cihaz, 2 fabrika
def _month_index(d: dt.date) -> int:
    return (d.year - 2024) * 12 + d.month


def _month_end(m: int) -> dt.date:
    y, mo = 2024 + (m - 1) // 12, (m - 1) % 12 + 1
    nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def _mac8(hk, kind, month, dev):
    import hmac as _hm
    msg = b"MGMBMS-K8" + bytes([kind, month]) + (dev if kind == SHORT_DEVICE else b"")
    return _hm.new(hk, msg, "sha256").digest()[:4]


def make_key8(secret: bytes, dev: bytes = None, expires: dt.date = None) -> str:
    import hashlib as _h
    kind = SHORT_DEVICE if dev else SHORT_FACTORY
    m = _month_index(expires) if expires else 0
    if not 0 <= m <= 255:
        raise ValueError("Bitiş tarihi 2024–2045 arasında olmalı")
    mac = _mac8(short_hmac_key_from_secret(secret), kind, m, dev)
    s = _b32(mac + bytes([m ^ _h.sha256(mac).digest()[0]]))
    return s[:4] + "-" + s[4:]


def check_key8(s: str, dev: bytes = None, today: dt.date = None):
    import hashlib as _h, hmac as _hm
    try:
        raw = _unb32(s)
    except Exception:
        raise ValueError("Anahtarda geçersiz karakter var")
    mac, m = raw[:4], raw[4] ^ _h.sha256(raw[:4]).digest()[0]
    dev = dev if dev is not None else device_bytes()
    hk = _short_key()
    kind = next((k for k in (SHORT_DEVICE, SHORT_FACTORY) if _hm.compare_digest(mac, _mac8(hk, k, m, dev))), None)
    if kind is None:
        raise ValueError("Geçersiz anahtar ya da başka bir cihaz için üretilmiş")
    exp = _month_end(m) if m else None
    if exp and (today or dt.date.today()) > exp:
        raise ValueError(f"Lisans süresi {exp:%d.%m.%Y} tarihinde doldu")
    return {"name": "Fabrika lisansı" if kind == SHORT_FACTORY else "Cihaz lisansı", "issued": None,
            "expires": exp.isoformat() if exp else None, "factory": kind == SHORT_FACTORY}


def check_any(text: str, dev: bytes = None, today: dt.date = None):
    """8 karakterlik anahtar, 20 karakterlik anahtar, fabrika kodu ya da uzun MGM1 anahtarı."""
    s8 = _clean_short(text)
    if len(s8) == 8:
        return check_key8(s8, dev, today)
    return check_short(text, dev, today) if is_short(text) else check_key(text, dev, today=today)


def _lic_path():
    base = os.environ.get("APPDATA")
    d = os.path.join(base, "MGM BMS") if base else os.path.join(os.path.expanduser("~"), ".mgm_bms")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "lisans.key")


def status():
    """{'ok': bool, 'device_id': str, 'name'?, 'expires'?, 'error'?}"""
    st = {"ok": False, "device_id": device_id()}
    try:
        with open(_lic_path(), encoding="utf-8") as f:
            key = f.read().strip()
    except FileNotFoundError:
        return st
    except Exception as e:
        st["error"] = str(e)
        return st
    try:
        st.update(check_any(key))
        st["ok"] = True
    except Exception as e:
        st["error"] = str(e)
    return st


def activate(key: str):
    info = check_any(key)                     # hatalıysa ValueError
    with open(_lic_path(), "w", encoding="utf-8") as f:
        f.write(key.strip())
    return dict(info, ok=True, device_id=device_id())


# --------------------------------------------------------------------------- klasik (tkinter) arayüz için etkinleştirme penceresi
def tk_gate():
    """Lisans yoksa tkinter etkinleştirme penceresi açar. Lisanslıysa True döner, kullanıcı kapatırsa False."""
    if status()["ok"]:
        return True
    import tkinter as tk
    ok = {"v": False}
    w = tk.Tk()
    w.title("MGM BMS – Lisans")
    w.configure(bg="#0b1119")
    w.resizable(False, False)
    fg, mu = "#e8eef6", "#8b97a8"
    tk.Label(w, text="MGM BMS lisans etkinleştirme", bg="#0b1119", fg=fg, font=("Segoe UI", 14, "bold")).pack(padx=24, pady=(20, 4), anchor="w")
    tk.Label(w, text="Aşağıdaki Cihaz Kimliğini satıcınıza gönderin, size özel lisans anahtarını yapıştırın.",
             bg="#0b1119", fg=mu, font=("Segoe UI", 10)).pack(padx=24, anchor="w")
    did = tk.Entry(w, font=("Consolas", 13, "bold"), justify="center", relief="flat", bg="#141c27", fg="#2ee6b5",
                   readonlybackground="#141c27")
    did.insert(0, device_id())
    did.configure(state="readonly")
    did.pack(padx=24, pady=12, fill="x", ipady=8)

    def copy():
        w.clipboard_clear()
        w.clipboard_append(device_id())
        msg.configure(text="Cihaz Kimliği kopyalandı", fg="#2ee6b5")
    tk.Button(w, text="Kimliği kopyala", command=copy, relief="flat", bg="#1b2533", fg=fg).pack(padx=24, anchor="e")
    tk.Label(w, text="Lisans anahtarı", bg="#0b1119", fg=mu, font=("Segoe UI", 10)).pack(padx=24, pady=(14, 2), anchor="w")
    txt = tk.Text(w, height=4, width=64, font=("Consolas", 10), relief="flat", bg="#141c27", fg=fg, insertbackground=fg)
    txt.pack(padx=24, fill="x")
    msg = tk.Label(w, text="", bg="#0b1119", fg="#fb7185", font=("Segoe UI", 10))
    msg.pack(padx=24, pady=6, anchor="w")

    def go():
        try:
            activate(txt.get("1.0", "end"))
            ok["v"] = True
            w.destroy()
        except Exception as e:
            msg.configure(text=str(e), fg="#fb7185")
    tk.Button(w, text="Etkinleştir", command=go, relief="flat", bg="#2ee6b5", fg="#03231c",
              font=("Segoe UI", 11, "bold"), padx=18, pady=6).pack(padx=24, pady=(0, 20), anchor="e")
    w.mainloop()
    return ok["v"]
