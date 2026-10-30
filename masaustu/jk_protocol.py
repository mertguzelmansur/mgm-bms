# -*- coding: utf-8 -*-
"""
JK BMS BLE protokolü (JK-BMS Android 6.3.01 uygulamasından çıkarıldı).

BLE:   Servis 0000ffe0-...,  Karakteristik 0000ffe1-... (yazma + bildirim)
Komut: AA 55 90 EB <cmd> <len> <değer LE ...> <dolgu> <toplam&0xFF>   (20 bayt)
Cevap: 55 AA EB 90 <tip> <sayaç> <293 bayt veri> <toplam&0xFF>       (300 bayt)
        tip 0x01 = ayarlar, 0x02 = anlık hücre/batarya verisi, 0x03 = cihaz bilgisi
"""
import struct
import time

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

FRAME_HEADER = b"\x55\xAA\xEB\x90"
FRAME_LEN = 300

CMD_SETTINGS_AND_DATA = 0x96   # ayarları gönder + sürekli 0x02 akışını başlat
CMD_DEVICE_INFO = 0x97
REG_CHARGE_SWITCH = 0x1D       # uygulamada "Charge"   (29, 4 bayt)
REG_DISCHARGE_SWITCH = 0x1E    # uygulamada "Discharge" (30, 4 bayt)
REG_BALANCE_SWITCH = 0x1F
CMD_RENAME = 0x9B              # BtNameDialogFragment / HexProtocolGenerator
NAME_MAX_LEN = 13
NAME_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_. ")

# Sistem alarm bitleri (LogInfo.sysAlarms) – veri ofseti 160, 32 bit LE
SYS_ALARMS = [
    "Denge kablosu direnci anormal", "MOS aşırı sıcaklık (OTP)", "Hücre sayısı anormal",
    "Akım sensörü anormal", "Hücre aşırı gerilim (OVP)", "Batarya aşırı gerilim (OVP)",
    "Şarj aşırı akım (OCP)", "Şarj kısa devre (SCP)", "Şarj aşırı sıcaklık (OTP)",
    "Şarj düşük sıcaklık (UTP)", "Dahili haberleşme hatası", "Hücre düşük gerilim (UVP)",
    "Batarya düşük gerilim (UVP)", "Deşarj aşırı akım (OCP)", "Deşarj kısa devre (SCP)",
    "Deşarj aşırı sıcaklık (OTP)", "Şarj MOS anormal", "Deşarj MOS anormal",
    "GPS bağlantısı yok", "Şifreyi hemen değiştirin", "Deşarj açılamadı",
    "Batarya aşırı sıcaklık", "Sıcaklık sensörü anormal", "Paralel limitör anormal",
    "SCP geri alma başarısız", "Deşarj OCP2", "Deşarj OCP3", "Deşarj düşük sıcaklık (UTP)",
    "Batarya GPS ile kilitli",
]
# Kullanıcı alarm bitleri (LogInfo.userAlarms) – veri ofseti 186, 16 bit LE
USER_ALARMS = [
    "UA2 Batarya aşırı sıcaklık", "UA2 Batarya düşük sıcaklık", "UA2 Büyük sıcaklık farkı",
    "UA2 Hücre aşırı gerilim uyarısı", "UA2 Hücre düşük gerilim uyarısı",
    "UA2 Deşarj aşırı akım uyarısı", "UA2 Şarj aşırı akım uyarısı",
    "UA2 Sıcaklık sensörü anormal", "UA2 Şarj cihazı haberleşmesi koptu",
    "UA2 BMS CAN haberleşmesi koptu", "UA2 Isıtıcı rölesi anormal",
    "UA2 Şarj cihazı anormal", "UA2 Isıtma anormal", "UA2 Isıtıcı anormal",
]

# Eski protokol (24S, "JK-B..." modelleri) – LogInfo.deviceOld
OLD_MODELS = {
    "JK-B1A20S15P", "JK-B1A24S15P", "JK-BD4A17S4P", "JK-B1A24S-15P", "JK-B5A16S-60P",
    "SQ-BD6A20S6P", "SQ-BD6A20S10P", "SQ-BD6A24S10P", "JK-B1A24S-P", "JK-B1A8S20P",
    "JK-B2A20S20P", "JK-B2A24S15P", "JK-B2A24S20P", "JK-B2A24S25P", "JK-B2A24S60P",
    "JK-BD6A20S-10P", "JK-BD6A17S6P", "JK-BD6A17S8P", "JK-BD6A20S3P", "JK-BD6A20S6P",
    "JK-BD6A20S8P", "JK-BD6A24S6P", "JK-BD6A24S8P", "JK-B2A8S20P", "JK-B5A16S60P",
    "JK-B5A24S60P", "JK-B2A24S-15P", "JK-B2A24S-20P", "JK-BD6A17S10P", "JK-BD6A20S10P",
    "JK-BD6A20S15P", "JK-BD6A22S15P", "JK-BD6A24S10P", "SQ-B1A20S15P", "SQ-B1A24S15P",
}


# --------------------------------------------------------------------------- komutlar
def build_command(cmd: int, value: int = 0, length: int = 0) -> bytes:
    """Utils.generate20ByteHex karşılığı (dolgu rastgele yerine 0)."""
    frame = bytearray(b"\xAA\x55\x90\xEB")
    frame += bytes([cmd & 0xFF, length & 0xFF])
    if length:
        frame += (value & ((1 << (8 * length)) - 1)).to_bytes(length, "little")
    frame += bytes(19 - len(frame))
    frame.append(sum(frame) & 0xFF)
    return bytes(frame)


def build_rename(name: str) -> bytes:
    """Cihaz (Bluetooth) adını değiştirme komutu – uygulamadaki ile birebir:
    AA 55 90 EB 9B <uzunluk> <ad: 13 bayt ASCII, 0 dolgulu> <toplam&FF>"""
    name = name.strip()
    if not name:
        raise ValueError("Ad boş olamaz")
    if len(name) > NAME_MAX_LEN:
        raise ValueError(f"Ad en fazla {NAME_MAX_LEN} karakter olabilir")
    bad = sorted(set(name) - NAME_ALLOWED)
    if bad:
        raise ValueError("Geçersiz karakter: " + " ".join(bad) + "  (Türkçe harf kullanılamaz)")
    raw = name.encode("ascii")
    frame = bytearray(b"\xAA\x55\x90\xEB") + bytes([CMD_RENAME, len(raw)])
    frame += raw.ljust(NAME_MAX_LEN, b"\x00")
    frame.append(sum(frame) & 0xFF)
    return bytes(frame)


def checksum_ok(frame: bytes) -> bool:
    return len(frame) >= FRAME_LEN and (sum(frame[:FRAME_LEN - 1]) & 0xFF) == frame[FRAME_LEN - 1]


class FrameAssembler:
    """BLE bildirim parçalarını 300 baytlık çerçevelere birleştirir."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        out = []
        if data[:4] == FRAME_HEADER:
            self.buf = bytearray()
        self.buf += data
        while True:
            i = self.buf.find(FRAME_HEADER)
            if i < 0:
                self.buf = self.buf[-3:]
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < FRAME_LEN:
                break
            frame = bytes(self.buf[:FRAME_LEN])
            if checksum_ok(frame) or frame[4] == 0x06:
                out.append(frame)
                del self.buf[:FRAME_LEN]
            else:
                del self.buf[:4]
        return out


# --------------------------------------------------------------------------- yardımcılar
def u8(p, o): return p[o]
def s8(p, o): return struct.unpack_from("<b", p, o)[0]
def u16(p, o): return struct.unpack_from("<H", p, o)[0]
def s16(p, o): return struct.unpack_from("<h", p, o)[0]
def u32(p, o): return struct.unpack_from("<I", p, o)[0]
def s32(p, o): return struct.unpack_from("<i", p, o)[0]


def ascii_field(p, o, n):
    return bytes(p[o:o + n]).split(b"\x00")[0].decode("ascii", "replace").strip()


def secs_to_text(s):
    d, s = divmod(int(s), 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{d}g {h:02d}:{m:02d}:{s:02d}"


def payload_of(frame: bytes) -> bytes:
    return frame[6:FRAME_LEN - 1]


def _finish(out: bytearray) -> bytes:
    out = bytearray(out[:FRAME_LEN - 1]) + bytes(max(0, FRAME_LEN - 1 - len(out)))
    out.append(sum(out) & 0xFF)
    return bytes(out)


# --------------------------------------------------------------------------- eski → yeni
def old_to_new(frame: bytes) -> bytes:
    """oldToNewAgreement.kt birebir: 24S çerçeveyi 32S düzenine çevirir."""
    p = payload_of(frame)
    t = frame[4]
    if t == 0x01:
        o = bytearray(bytes.fromhex("55AAEB90010000000000"))
        for a, b in [(4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]:
            o += p[a:b]
        o += bytes(16)
        for a in range(40, 136, 4):
            o += p[a:a + 4]
        o += p[136:232]
        o += bytes.fromhex("00" * 49 + "7CF8FFFF0F0000000000000000")
        return _finish(o)
    if t == 0x02:
        o = bytearray(bytes.fromhex("55AAEB900200"))
        o += p[0:48] + bytes(16)
        o += p[48:52] + p[52:54] + p[54:56] + p[56:57] + p[57:58]
        o += p[58:106] + bytes(16)
        o += p[128:130]
        o += p[108:112] + p[112:116] + p[116:120] + p[120:124] + p[124:126] + p[126:128]
        o += p[130:132] + bytes(2) + p[132:134] + p[134:135] + p[135:136]
        o += p[136:140] + p[140:144] + p[144:148] + p[148:152] + bytes(4)
        o += p[156:160] + p[160:161] + p[161:162] + bytes(2)
        for a in range(164, 176, 2):
            o += p[a:a + 2]
        o += p[176:177]
        o += bytes.fromhex("00" * 51 + "33" * 21 + "FEFF7FDC" + "00" * 9)
        return _finish(o)
    if t == 0x03:
        o = bytearray(bytes.fromhex("55AAEB900300"))
        for a, b in [(0, 16), (16, 24), (24, 32), (32, 36), (36, 40), (40, 56), (56, 72),
                     (72, 80), (80, 96), (96, 112), (112, 128)]:
            o += p[a:b]
        o += bytes(16) + bytes.fromhex("7EF8FFFF0F000000000000008008000000000098030100")
        return _finish(o)
    return frame


# --------------------------------------------------------------------------- çözümleyiciler
def parse_device_info(frame: bytes) -> dict:
    p = payload_of(frame)
    return {
        "model": ascii_field(p, 0, 16),
        "hw": ascii_field(p, 16, 8),
        "sw": ascii_field(p, 24, 8),
        "uptime_s": u32(p, 32),
        "power_on_count": u32(p, 36),
        "name": ascii_field(p, 40, 16),
        "mfg_date": ascii_field(p, 72, 8),
        "serial": ascii_field(p, 80, 16),
        "protocol": p[292] if len(p) > 292 else 0,
        # uygulama: veri[144:176] içindeki 19. bayt, 3. bit → ad değiştirme destekli
        "can_rename": bool(p[163] & 0x08) if len(p) > 163 else True,
        # ThreeFragmentViewModel.setRefreshData: ayar şifresi = veri[112:128] (sb3.substring(224,256))
        "setting_password": ascii_field(p, 112, 16),
        # DeviceActivityViewModel "更改设备密码": cihaz (eşleştirme) şifresi = veri[56:72]
        "device_password": ascii_field(p, 56, 16),
        "user_data": ascii_field(p, 96, 16),
        "password_protected": bool(p[163] & 0x10) if len(p) > 163 else False,
        "distributor_id": u16(p, 176) if len(p) > 178 else 0,
        "_payload": bytes(p),
    }


def is_old_protocol(info: dict) -> bool:
    return info.get("protocol", 0) == 0 and info.get("model", "") in OLD_MODELS


# Yazılabilir parametreler – ThreeFragmentViewModel'deki TwoTypeTwoBean tablosundan.
# Kayıt numarası = ofset/4 + 1 ; ham değer = değer × oran ; min/maks ham birimde.
# (ofset, ad, tip, ölçek, birim, min_ham, maks_ham)
SETTING_FIELDS = [
    (0, "Akıllı uyku gerilimi", "u32", 0.001, "V", 1200, 4400),
    (4, "Hücre düşük gerilim koruma (UVP)", "u32", 0.001, "V", 1200, 4400),
    (8, "Hücre UVP geri dönüş", "u32", 0.001, "V", 1200, 4400),
    (12, "Hücre aşırı gerilim koruma (OVP)", "u32", 0.001, "V", 1200, 4400),
    (16, "Hücre OVP geri dönüş", "u32", 0.001, "V", 1200, 4400),
    (20, "Denge tetikleme farkı", "u32", 0.001, "V", 3, 1000),
    (24, "SOC %100 gerilimi", "u32", 0.001, "V", 1200, 4400),
    (28, "SOC %0 gerilimi", "u32", 0.001, "V", 1200, 4400),
    (32, "Önerilen şarj gerilimi (RCV)", "u32", 0.001, "V", 1200, 4400),
    (36, "Tam şarj gerilimi (RFV)", "u32", 0.001, "V", 1200, 4400),
    (40, "Kapanma gerilimi", "u32", 0.001, "V", 1200, 4400),
    (44, "Maks. şarj akımı", "u32", 0.001, "A", 1000, 600000),
    (48, "Şarj OCP gecikmesi", "u32", 1, "s", 2, 600),
    (52, "Şarj OCP geri dönüş süresi", "u32", 1, "s", 2, 600),
    (56, "Maks. deşarj akımı", "u32", 0.001, "A", 1000, 2000000),
    (60, "Deşarj OCP gecikmesi", "u32", 1, "s", 2, 600),
    (64, "Deşarj OCP geri dönüş süresi", "u32", 1, "s", 2, 600),
    (68, "SCP geri dönüş süresi", "u32", 1, "s", 2, 600),
    (72, "Maks. denge akımı", "u32", 0.001, "A", 300, 15000),
    (76, "Şarj aşırı sıcaklık (OTP)", "s32", 0.1, "°C", 300, 800),
    (80, "Şarj OTP geri dönüş", "s32", 0.1, "°C", 300, 800),
    (84, "Deşarj aşırı sıcaklık (OTP)", "s32", 0.1, "°C", 300, 800),
    (88, "Deşarj OTP geri dönüş", "s32", 0.1, "°C", 300, 800),
    (92, "Şarj düşük sıcaklık (UTP)", "s32", 0.1, "°C", -450, 200),
    (96, "Şarj UTP geri dönüş", "s32", 0.1, "°C", -450, 200),
    (100, "MOS aşırı sıcaklık", "s32", 0.1, "°C", 300, 1100),
    (104, "MOS OTP geri dönüş", "s32", 0.1, "°C", 300, 1100),
    (108, "Hücre sayısı", "u32", 1, "", 2, 32),
    (112, "Şarj anahtarı", "bool", 1, "", 0, 1),
    (116, "Deşarj anahtarı", "bool", 1, "", 0, 1),
    (120, "Dengeleyici anahtarı", "bool", 1, "", 0, 1),
    (124, "Nominal kapasite", "u32", 0.001, "Ah", 2000, 2000000),
    (128, "Kısa devre gecikmesi", "u32", 1, "µs", 0, 1000000),
    (132, "Dengeleme başlangıç gerilimi", "u32", 0.001, "V", 1200, 4400),
]
FIELD_BY_OFF = {f[0]: f for f in SETTING_FIELDS}
FIELD_BY_NAME = {f[1]: f for f in SETTING_FIELDS}


def setting_register(off: int) -> int:
    return off // 4 + 1


def fmt_setting(off: int, raw: int) -> str:
    _, _, typ, scale, unit, _, _ = FIELD_BY_OFF[off]
    if typ == "bool":
        return "Açık" if raw else "Kapalı"
    if scale == 1:
        return str(raw)
    dec = {"V": 3, "A": 2, "Ah": 1}.get(unit, 1) if scale == 0.001 else 1
    return f"{raw * scale:.{dec}f}"


def build_setting_write(off: int, raw: int) -> bytes:
    """Bir ayar parametresini yazar (uygulamadaki generate20ByteHex(code, 4, değer))."""
    _, name, _, _, _, lo, hi = FIELD_BY_OFF[off]
    if not lo <= raw <= hi:
        raise ValueError(f"{name}: {raw} izin verilen aralığın dışında ({lo}..{hi})")
    return build_command(setting_register(off), raw, 4)


def parse_settings(frame: bytes) -> dict:
    p = payload_of(frame)
    out = {}
    raw = {}
    for off, name, typ, scale, unit, _, _ in SETTING_FIELDS:
        if typ == "bool":
            raw[off] = 1 if p[off] else 0
        else:
            raw[off] = u32(p, off) if typ == "u32" else s32(p, off)
        out[name] = (fmt_setting(off, raw[off]), unit)
    out["_raw"] = raw
    out["_cell_count"] = u32(p, 108)
    out["_capacity_ah"] = u32(p, 124) / 1000.0
    out["_charge_on"] = bool(p[112])
    out["_discharge_on"] = bool(p[116])
    out["_balance_on"] = bool(p[120])
    out["_payload"] = bytes(p)
    return out


def settings_sanity(raw: dict) -> list:
    """Eşik sıralamasında mantıksız durumlar için uyarı listesi."""
    w = []
    def chk(a, b, msg):
        if a in raw and b in raw and not raw[a] < raw[b]:
            w.append(msg)
    chk(4, 8, "UVP, UVP geri dönüşten küçük olmalı")
    chk(8, 16, "UVP geri dönüş, OVP geri dönüşten küçük olmalı")
    chk(16, 12, "OVP geri dönüş, OVP'den küçük olmalı")
    chk(40, 4, "Kapanma gerilimi UVP'den küçük olmalı")
    if 24 in raw and 12 in raw and raw[24] > raw[12]:
        w.append("SOC %100 gerilimi OVP'den büyük olmamalı")
    chk(28, 24, "SOC %0 gerilimi SOC %100'den küçük olmalı")
    chk(80, 76, "Şarj OTP geri dönüş, Şarj OTP'den küçük olmalı")
    chk(88, 84, "Deşarj OTP geri dönüş, Deşarj OTP'den küçük olmalı")
    chk(92, 96, "Şarj UTP, UTP geri dönüşten küçük olmalı")
    chk(104, 100, "MOS OTP geri dönüş, MOS OTP'den küçük olmalı")
    if 32 in raw and 12 in raw and raw[32] > raw[12]:
        w.append("Önerilen şarj gerilimi (RCV) OVP'den büyük olmamalı")
    return w


def _bits(v, n):
    return [i for i in range(n) if (v >> i) & 1]


def parse_cell_info(frame: bytes, cell_count_hint: int = 0) -> dict:
    """OneFragmentViewModel.setUI / TwoFragmentViewModel ile aynı ofsetler."""
    p = payload_of(frame)
    mask = u32(p, 64)
    enabled = _bits(mask, 32)
    if not enabled:
        n = cell_count_hint or sum(1 for i in range(32) if u16(p, i * 2))
        enabled = list(range(n))
    cells = [u16(p, i * 2) / 1000.0 for i in range(32)]
    res = [u16(p, 74 + i * 2) / 1000.0 for i in range(32)]
    res_alarm = set(_bits(u32(p, 140), 32))

    def temp(off):
        v = s16(p, off)
        return None if v <= -2000 or v >= 2000 else v / 10.0

    sys_alarm_bits = u32(p, 160)
    user_alarm_bits = u16(p, 186)
    alarms = [SYS_ALARMS[i] if i < len(SYS_ALARMS) else f"Sistem alarmı bit {i}"
              for i in _bits(sys_alarm_bits, 32)]
    user_alarms = [USER_ALARMS[i] if i < len(USER_ALARMS) else f"Kullanıcı alarmı bit {i}"
                   for i in _bits(user_alarm_bits, 16)]

    ts = u32(p, 256)
    return {
        "cells": [cells[i] for i in enabled],
        "cell_index": [i + 1 for i in enabled],
        "resistances": [res[i] for i in enabled],
        "res_alarm": [i in res_alarm for i in enabled],
        "avg_cell": u16(p, 68) / 1000.0,
        "delta_cell": u16(p, 70) / 1000.0,
        "max_idx": s8(p, 72),
        "min_idx": s8(p, 73),
        "mos_temp": temp(138),
        "voltage": u32(p, 144) / 1000.0,
        "power": u32(p, 148) / 1000.0,
        "current": s32(p, 152) / 1000.0,
        "temps": [temp(156), temp(158), temp(248), temp(250), temp(252)],
        "balance_current": s16(p, 164) / 1000.0,
        "balance_action": p[166],          # 0 yok, 1 şarj, 2 deşarj
        "soc": p[167],
        "remain_ah": u32(p, 168) / 1000.0,
        "full_ah": u32(p, 172) / 1000.0,
        "cycles": u32(p, 176),
        "cycle_ah": u32(p, 180) / 1000.0,
        "soh": p[184],
        "precharge": p[185],
        "runtime_s": u32(p, 188),
        "charge_mos": bool(p[192]),
        "discharge_mos": bool(p[193]),
        "alarms": alarms,
        "user_alarms": user_alarms,
        "bms_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts + 1577808000)) if ts else "",
    }


# --------------------------------------------------------------------------- demo verisi
def make_demo_frames(t: float):
    """Gerçek BMS olmadan arayüzü denemek için sahte çerçeveler üretir."""
    import math
    import random
    n = 16
    # 0x03 cihaz bilgisi
    d = bytearray(b"\x55\xAA\xEB\x90\x03\x01") + bytes(293)
    def put(o, s): d[6 + o:6 + o + len(s)] = s.encode()
    put(0, "JK_PB2A16S20P"); put(16, "15A"); put(24, "15.36"); put(40, "JK-DEMO")
    put(72, "240501"); put(80, "DEMO12345")
    struct.pack_into("<II", d, 6 + 32, int(t) + 86400 * 12, 7)
    d[6 + 292] = 1
    d[6 + 163] = 0x18
    put(56, "1234"); put(96, "Garaj akusu")
    d[6 + 178] = 1; d[6 + 179] = 4; d[6 + 212] = 0; d[6 + 264] = 0; d[6 + 273] = 0   # UART1 / CAN / UART2-4
    d[6 + 228] = 1; d[6 + 229] = 5; d[6 + 230] = 0                                   # LCD / DRY1 / DRY2 tetik
    struct.pack_into("<iiiiii", d, 6 + 232, 20, 25, 2800, 2900, 0, 0)
    struct.pack_into("<I", d, 6 + 256, 3600)                                         # veri kayıt periyodu
    d[6 + 260] = 20; d[6 + 261] = 10; d[6 + 263] = 10; d[6 + 272] = 5               # RCV/RFV süresi, acil süre, re-bulk
    struct.pack_into("<H", d, 6 + 176, 0)
    info = _finish(d)

    # 0x01 ayarlar
    s = bytearray(b"\x55\xAA\xEB\x90\x01\x01") + bytes(293)
    vals = {0: 3300, 4: 2800, 8: 3000, 12: 3650, 16: 3550, 20: 10, 24: 3450, 28: 3000, 32: 3550,
            36: 3450, 40: 2600, 44: 100000, 48: 30, 52: 60, 56: 150000, 60: 300, 64: 60, 68: 5,
            72: 2000, 76: 700, 80: 600, 84: 700, 88: 600, 92: 0, 96: 50, 100: 1000, 104: 800,
            108: n, 112: 1, 116: 1, 120: 1, 124: 280000, 128: 1500, 132: 3400}
    for o, v in vals.items():
        struct.pack_into("<i", s, 6 + o, v)
    struct.pack_into("<IIi", s, 6 + 264, 1, 5, 200000)        # cihaz adresi, ön deşarj süresi, akım aralığı
    s[6 + 278] = 5; s[6 + 279] = 10; s[6 + 280] = 24            # ısıtıcı başla/dur, akıllı uyku süresi
    s[6 + 290] = (-20) & 0xFF; s[6 + 291] = (-10) & 0xFF       # deşarj UTP / UTPR
    for code in (29, 30, 31, 43, 45, 50, 51):                    # açık anahtarlar
        s[6 + 281 + code // 8] |= 1 << (code % 8)
    settings = _finish(s)

    # 0x02 hücre bilgisi
    c = bytearray(b"\x55\xAA\xEB\x90\x02\x05") + bytes(293)
    P = 6
    base = 3300 + 40 * math.sin(t / 30)
    cells = [int(base + random.randint(-8, 8) + (15 if i == 5 else 0)) for i in range(n)]
    for i, v in enumerate(cells):
        struct.pack_into("<H", c, P + i * 2, v)
        struct.pack_into("<H", c, P + 74 + i * 2, 60 + random.randint(0, 20))
    struct.pack_into("<I", c, P + 64, (1 << n) - 1)
    struct.pack_into("<HH", c, P + 68, sum(cells) // n, max(cells) - min(cells))
    c[P + 72] = cells.index(max(cells)); c[P + 73] = cells.index(min(cells))
    struct.pack_into("<h", c, P + 138, 312 + random.randint(-3, 3))
    volt = sum(cells)
    cur = int(12000 * math.sin(t / 20))
    struct.pack_into("<IIi", c, P + 144, volt, abs(volt * cur // 1000), cur)
    struct.pack_into("<hh", c, P + 156, 254, 261)
    struct.pack_into("<I", c, P + 160, 0)
    struct.pack_into("<h", c, P + 164, 120 if (max(cells) - min(cells)) > 10 else 0)
    c[P + 166] = 2 if (max(cells) - min(cells)) > 10 else 0
    soc = int(50 + 30 * math.sin(t / 60))
    c[P + 167] = soc
    struct.pack_into("<IIII", c, P + 168, 280000 * soc // 100, 280000, 42, 11760000)
    c[P + 184] = 100
    struct.pack_into("<I", c, P + 188, int(t) + 3600 * 50)
    c[P + 192] = 1; c[P + 193] = 1
    struct.pack_into("<hhh", c, P + 248, -2000, -2000, -2000)
    struct.pack_into("<I", c, P + 256, int(time.time()) - 1577808000)
    cellf = _finish(c)
    return info, settings, cellf


# =============================================================================
# GELİŞMİŞ ÖZELLİKLER (ThreeFragmentViewModel.setRefreshData / ThreeBean / TwoTypeTwoBean)
# =============================================================================
# Ayar çerçevesi (0x01) ve cihaz çerçevesi (0x03) içindeki ek alanlar.
# src: "set" = ayar verisi, "info" = cihaz verisi ; ln = komuttaki değer uzunluğu
RS485_PROTOCOLS = [
    "000 - 4G-GPS uzak modül V4.2", "001 - JK BMS RS485 Modbus V1.0", "002 - NIU U serisi",
    "003 - China Tower paylaşımlı kabin V1.1", "004 - PACE RS485 Modbus V1.3", "005 - PYLON düşük gerilim RS485 V3.5",
    "006 - Growatt BMS RS485 1xSxxP ESS Rev2.01", "007 - Voltronic inverter-BMS 485 (2020)",
    "008 - China Tower paylaşımlı kabin V2.0", "009 - WOW RS485 Modbus V1.3", "010 - JK BMS LCD protokolü V2.0",
    "011 - UART1 kullanıcı tanımlı", "012 - UART2 kullanıcı tanımlı", "013 - (9600) JK BMS RS485 Modbus V1.0",
    "014 - (9600) PYLON düşük gerilim RS485 V3.5", "015 - JK BMS PBxx LCD protokolü V1.0", "016 - JK BMS LIN BUS V1.0",
    "017 - JK aktif dengeleyici LCD V1.0", "018 - RS485 protokol 18", "019 - RS485 protokol 19", "020 - RS485 protokol 20",
]
CAN_PROTOCOLS = [
    "000 - JK BMS CAN (250K) V2.0", "001 - Deye düşük gerilim hibrit inverter CAN V1.0", "002 - PYLON düşük gerilim V1.2",
    "003 - Growatt BMS CAN düşük gerilim Rev1.04", "004 - Victron CANbus BMS (2017)", "005 - MEGAREVO hibrit BMS CAN",
    "006 - JK BMS CAN (500K) V2.0", "007 - INVT BMS CAN V1.02", "008 - GoodWe LV BMS (EX/EM/S-BP/BP)",
    "009 - FSS ConnectingBat V1.0", "010 - MUST PV1800F CAN", "011 - LuxpowerTek batarya CAN V01",
    "012 - CAN kullanıcı tanımlı", "013 - CAN kullanıcı tanımlı 2", "014 - JINLONG düşük gerilim inverter CAN V1.0",
    "015 - NMEA 2000 V1.300", "016 - CAN protokol 016", "017 - CAN protokol 017", "018 - CAN protokol 018",
    "019 - CAN protokol 019", "020 - CAN protokol 020",
]
TRIGGER_SOURCES = [
    "00 - Kapalı", "01 - Düşük SOC", "02 - Batarya aşırı gerilim", "03 - Batarya düşük gerilim",
    "04 - Hücre aşırı gerilim", "05 - Hücre düşük gerilim", "06 - Şarj aşırı akım", "07 - Deşarj aşırı akım",
    "08 - Batarya aşırı sıcaklık", "09 - MOSFET aşırı sıcaklık", "10 - Sistem alarmı", "11 - Batarya düşük sıcaklık",
    "12 - GPS uzaktan kontrol", "13 - SOC üstünde", "14 - MOSFET anormal",
]

# kind: num | select | bit | ro      group: arayüzdeki grup başlığı
ADV_FIELDS = [
    # --- Isıtma
    dict(key="b39", name="Deşarjda ısıtma", group="Isıtma", kind="bit", reg=39),
    dict(key="s278", name="Isıtıcı başlama sıcaklığı", group="Isıtma", kind="num", src="set", off=278, typ="s8", scale=1, unit="°C", reg=55, ln=1, lo=-40, hi=100),
    dict(key="s279", name="Isıtıcı durma sıcaklığı", group="Isıtma", kind="num", src="set", off=279, typ="s8", scale=1, unit="°C", reg=56, ln=1, lo=-40, hi=100),
    # --- Sıcaklık
    dict(key="s290", name="Deşarj düşük sıcaklık (UTP)", group="Sıcaklık sensörleri", kind="num", src="set", off=290, typ="s8", scale=1, unit="°C", reg=58, ln=1, lo=-40, hi=100),
    dict(key="s291", name="Deşarj UTP geri dönüş", group="Sıcaklık sensörleri", kind="num", src="set", off=291, typ="s8", scale=1, unit="°C", reg=59, ln=1, lo=-40, hi=100),
    dict(key="b40", name="Batarya sıcaklık sensörünü devre dışı bırak", group="Sıcaklık sensörleri", kind="bit", reg=40),
    dict(key="b63", name="MOS sıcaklık sensörünü devre dışı bırak", group="Sıcaklık sensörleri", kind="bit", reg=63),
    # --- Ek korumalar
    dict(key="b51", name="Deşarj aşırı akım 2 (OCP2)", group="Ek korumalar", kind="bit", reg=51),
    dict(key="b52", name="Deşarj aşırı akım 3 (OCP3)", group="Ek korumalar", kind="bit", reg=52),
    dict(key="b46", name="Deşarj akım sınırlayıcı", group="Ek korumalar", kind="bit", reg=46),
    dict(key="s268", name="Ön deşarj süresi", group="Ek korumalar", kind="num", src="set", off=268, typ="u32", scale=1, unit="s", reg=37, ln=4, lo=0, hi=300),
    # --- Şarj kontrolü
    dict(key="b44", name="Özel şarj cihazı", group="Şarj kontrolü", kind="bit", reg=44),
    dict(key="b48", name="Şarj float modu", group="Şarj kontrolü", kind="bit", reg=48),
    dict(key="i260", name="RCV süresi", group="Şarj kontrolü", kind="num", src="info", off=260, typ="u8", scale=0.1, unit="sa", reg=179, ln=1, lo=0, hi=250),
    dict(key="i261", name="RFV süresi", group="Şarj kontrolü", kind="num", src="info", off=261, typ="u8", scale=0.1, unit="sa", reg=180, ln=1, lo=0, hi=250),
    dict(key="i272", name="Yeniden yükleme SOC (Re-Bulk)", group="Şarj kontrolü", kind="num", src="info", off=272, typ="u8", scale=1, unit="%", reg=183, ln=1, lo=0, hi=50),
    # --- Alarm, acil durum, kuru kontak
    dict(key="e107", name="Acil durum modu", group="Alarm ve acil durum", kind="bit", reg=107),
    dict(key="i263", name="Acil durum süresi", group="Alarm ve acil durum", kind="num", src="info", off=263, typ="u8", scale=1, unit="dk", reg=181, ln=1, lo=1, hi=30),
    dict(key="b49", name="Düğme ile acil durum", group="Alarm ve acil durum", kind="bit", reg=49),
    dict(key="b50", name="Aralıklı alarm", group="Alarm ve acil durum", kind="bit", reg=50),
    dict(key="i228", name="LCD buzzer tetik kaynağı", group="Alarm ve acil durum", kind="select", src="info", off=228, typ="u8", reg=169, ln=1, options="TRIGGER_SOURCES"),
    dict(key="i232", name="LCD buzzer tetik değeri", group="Alarm ve acil durum", kind="num", src="info", off=232, typ="s32", scale=1, unit="", reg=172, ln=4, lo=-1410065407, hi=1410065407),
    dict(key="i236", name="LCD buzzer bırakma değeri", group="Alarm ve acil durum", kind="num", src="info", off=236, typ="s32", scale=1, unit="", reg=173, ln=4, lo=-1410065407, hi=1410065407),
    dict(key="i229", name="Kuru kontak 1 tetik kaynağı", group="Kuru kontaklar", kind="select", src="info", off=229, typ="u8", reg=170, ln=1, options="TRIGGER_SOURCES"),
    dict(key="i240", name="Kuru kontak 1 tetik değeri", group="Kuru kontaklar", kind="num", src="info", off=240, typ="s32", scale=1, unit="", reg=174, ln=4, lo=-1410065407, hi=1410065407),
    dict(key="i244", name="Kuru kontak 1 bırakma değeri", group="Kuru kontaklar", kind="num", src="info", off=244, typ="s32", scale=1, unit="", reg=175, ln=4, lo=-1410065407, hi=1410065407),
    dict(key="i230", name="Kuru kontak 2 tetik kaynağı", group="Kuru kontaklar", kind="select", src="info", off=230, typ="u8", reg=171, ln=1, options="TRIGGER_SOURCES"),
    dict(key="i248", name="Kuru kontak 2 tetik değeri", group="Kuru kontaklar", kind="num", src="info", off=248, typ="s32", scale=1, unit="", reg=176, ln=4, lo=-1410065407, hi=1410065407),
    dict(key="i252", name="Kuru kontak 2 bırakma değeri", group="Kuru kontaklar", kind="num", src="info", off=252, typ="s32", scale=1, unit="", reg=177, ln=4, lo=-1410065407, hi=1410065407),
    # --- Uyku / ekran
    dict(key="b45", name="Akıllı uyku", group="Uyku ve ekran", kind="bit", reg=45),
    dict(key="s280", name="Akıllı uyku süresi", group="Uyku ve ekran", kind="num", src="set", off=280, typ="u8", scale=1, unit="sa", reg=57, ln=1, lo=1, hi=100),
    dict(key="b43", name="LCD sürekli açık", group="Uyku ve ekran", kind="bit", reg=43),
    # --- Haberleşme
    dict(key="i178", name="UART1 (RS485) protokolü", group="Haberleşme (inverter)", kind="select", src="info", off=178, typ="u8", reg=165, ln=1, options="RS485_PROTOCOLS"),
    dict(key="i212", name="UART2 protokolü", group="Haberleşme (inverter)", kind="select", src="info", off=212, typ="u8", reg=168, ln=1, options="RS485_PROTOCOLS"),
    dict(key="i264", name="UART3 protokolü", group="Haberleşme (inverter)", kind="select", src="info", off=264, typ="u8", reg=182, ln=1, options="RS485_PROTOCOLS"),
    dict(key="i273", name="UART4 protokolü", group="Haberleşme (inverter)", kind="select", src="info", off=273, typ="u8", reg=184, ln=1, options="RS485_PROTOCOLS"),
    dict(key="i179", name="CAN protokolü", group="Haberleşme (inverter)", kind="select", src="info", off=179, typ="u8", reg=166, ln=1, options="CAN_PROTOCOLS"),
    dict(key="s264", name="Cihaz adresi", group="Haberleşme (inverter)", kind="num", src="set", off=264, typ="u32", scale=1, unit="", reg=36, ln=4, lo=0, hi=999999999),
    dict(key="b47", name="Zamanlı veri kaydı", group="Haberleşme (inverter)", kind="bit", reg=47),
    dict(key="i256", name="Veri kayıt periyodu", group="Haberleşme (inverter)", kind="num", src="info", off=256, typ="u32", scale=1, unit="s", reg=178, ln=4, lo=5, hi=864000),
    # --- GPS
    dict(key="b41", name="GPS kalp atışı", group="GPS", kind="bit", reg=41),
    dict(key="b53", name="GPS ile şarjı kilitle", group="GPS", kind="bit", reg=53),
    dict(key="b54", name="GPS ile deşarjı kilitle", group="GPS", kind="bit", reg=54),
    # --- Fabrika
    dict(key="b60", name="KERS (rejeneratif frenleme)", group="Fabrika ayarları", kind="bit", reg=60, factory=True),
    dict(key="b61", name="Hücre gerilimi filtresi", group="Fabrika ayarları", kind="bit", reg=61, factory=True),
    dict(key="b62", name="Şarj/deşarj karşılıklı kilidi", group="Fabrika ayarları", kind="bit", reg=62, factory=True),
    dict(key="s272", name="Akım ölçüm aralığı", group="Fabrika ayarları", kind="ro", src="set", off=272, typ="u32", scale=0.001, unit="A"),
    dict(key="i176", name="Bayi (distribütör) kimliği", group="Fabrika ayarları", kind="ro", src="info", off=176, typ="u16", scale=1, unit=""),
]
ADV_BY_KEY = {f["key"]: f for f in ADV_FIELDS}

_FMT = {"u8": "<B", "s8": "<b", "u16": "<H", "s16": "<h", "u32": "<I", "s32": "<i"}


def parse_advanced(settings_payload, info_payload) -> dict:
    """Ham değerler: {key: int}. Bit anahtarları: ayar[281 + kod//8] bit kod%8 (kod 29..63),
    acil durum: cihaz[157] bit 3 (uygulamada byteHex10[3])."""
    out = {}
    sp, ip = settings_payload, info_payload
    for f in ADV_FIELDS:
        k = f["kind"]
        try:
            if k == "bit":
                if f["reg"] == 107:
                    if ip is None:
                        continue
                    out[f["key"]] = (ip[157] >> 3) & 1
                else:
                    if sp is None:
                        continue
                    c = f["reg"]
                    out[f["key"]] = (sp[281 + c // 8] >> (c % 8)) & 1
            else:
                src = sp if f["src"] == "set" else ip
                if src is None:
                    continue
                out[f["key"]] = struct.unpack_from(_FMT[f["typ"]], src, f["off"])[0]
        except (IndexError, struct.error):
            pass
    return out


def build_adv_write(key: str, raw: int) -> bytes:
    f = ADV_BY_KEY[key]
    if f["kind"] == "ro":
        raise ValueError(f"{f['name']} salt okunur")
    if f["kind"] == "bit":
        if raw not in (0, 1):
            raise ValueError("Anahtar değeri 0 ya da 1 olmalı")
        return build_command(f["reg"], raw, 4)
    if f["kind"] == "select":
        n = len(globals()[f["options"]])
        if not 0 <= raw < n:
            raise ValueError(f"{f['name']}: seçim 0..{n - 1} arası olmalı")
        return build_command(f["reg"], raw, 1)
    if not f["lo"] <= raw <= f["hi"]:
        raise ValueError(f"{f['name']}: {raw} izin verilen aralığın dışında ({f['lo']}..{f['hi']})")
    return build_command(f["reg"], raw, f["ln"])


def adv_meta():
    """Arayüze gönderilecek tanımlar (seçenek listeleri açılmış hâlde)."""
    out = []
    for f in ADV_FIELDS:
        g = dict(f)
        if "options" in g:
            g["options"] = globals()[g["options"]]
        out.append(g)
    return out


# --------------------------------------------------------------------------- eylemler (değersiz komutlar)
ACTIONS = {
    "restart": (0x66, "BMS'i yeniden başlat"),
    "shutdown": (0x65, "BMS'i kapat"),
    "factory_reset": (0x9D, "Fabrika ayarı / geçmişi sil"),     # uygulama ikisi için de 157 gönderiyor
    "erase_all": (0xA3, "Tüm verileri sil"),
    "preset_ncm": (0x68, "NCM/NCA varsayılan parametrelerini yükle"),
    "preset_lfp": (0x69, "LFP varsayılan parametrelerini yükle"),
    "preset_lto": (0x6A, "LTO varsayılan parametrelerini yükle"),
}
CMD_LOG = 0xA7
REG_TIME_SYNC = 0x6C        # ItemThreeDuiShi: generate20ByteHex(108, 4, epoch - 1577808000)
EPOCH_2020 = 1577808000

# metin yazan komutlar (HexProtocolGenerator: önek + uzunluk + 13 bayt ASCII)
STRING_CMDS = {"device_password": 0x9C, "setting_password": 0xA0, "user_data_1": 0x9F, "user_data_2": 0xA2}

# kalibrasyon (yalnızca yazma) – (kayıt, uzunluk, ölçek, birim, min, maks)
CALIBRATIONS = {
    "volt": (100, 4, 0.001, "V", 1000, 200000, "Toplam gerilim kalibrasyonu"),
    "curr": (103, 4, 0.001, "A", 0, 2000000, "Akım kalibrasyonu"),
    "soc": (110, 1, 1, "%", 1, 99, "SOC kalibrasyonu"),
    "soh": (111, 1, 1, "%", 50, 100, "SOH kalibrasyonu"),
    "cycle": (112, 4, 0.001, "Ah", 1, 20000000, "Döngü kapasitesi düzeltmesi"),
}


def build_action(name: str) -> bytes:
    return build_command(ACTIONS[name][0])


def build_time_sync(ts: float = None) -> bytes:
    ts = int(time.time() if ts is None else ts)
    return build_command(REG_TIME_SYNC, ts - EPOCH_2020, 4)


def build_string_cmd(kind: str, text: str) -> bytes:
    text = text.strip()
    if not text:
        raise ValueError("Boş olamaz")
    if len(text) > NAME_MAX_LEN:
        raise ValueError(f"En fazla {NAME_MAX_LEN} karakter")
    bad = sorted(set(text) - NAME_ALLOWED)
    if bad:
        raise ValueError("Geçersiz karakter: " + " ".join(bad) + "  (Türkçe harf kullanılamaz)")
    raw = text.encode("ascii")
    frame = bytearray(b"\xAA\x55\x90\xEB") + bytes([STRING_CMDS[kind], len(raw)]) + raw.ljust(NAME_MAX_LEN, b"\x00")
    frame.append(sum(frame) & 0xFF)
    return bytes(frame)


def build_calibration(kind: str, raw: int) -> bytes:
    reg, ln, _, _, lo, hi, name = CALIBRATIONS[kind]
    if not lo <= raw <= hi:
        raise ValueError(f"{name}: değer aralık dışında")
    return build_command(reg, raw, ln)


# --------------------------------------------------------------------------- arıza kayıtları (0x06)
LOG_EVENTS = {
    1: "Açılış", 3: "Uygulama şarjı kapattı", 4: "Uygulama şarjı açtı", 5: "Uygulama deşarjı kapattı",
    6: "Uygulama deşarjı açtı", 7: "Uzaktan şarj kapatıldı", 8: "Uzaktan şarj açıldı", 9: "Uzaktan deşarj kapatıldı",
    10: "Uzaktan deşarj açıldı", 11: "MOS aşırı sıcaklık", 12: "MOS aşırı sıcaklık bitti", 13: "Akım sensörü anormal",
    14: "Akım sensörü normale döndü", 15: "Dahili haberleşme hatası", 16: "Dahili haberleşme düzeldi",
    17: "Hücre aşırı gerilim", 18: "Hücre aşırı gerilim bitti", 19: "Batarya aşırı gerilim", 20: "Batarya aşırı gerilim bitti",
    21: "Şarj aşırı akım", 22: "Şarj aşırı akım bitti", 23: "Şarj kısa devre", 24: "Şarj kısa devre bitti",
    25: "Şarj aşırı sıcaklık", 26: "Şarj aşırı sıcaklık bitti", 27: "Şarj düşük sıcaklık", 28: "Şarj düşük sıcaklık bitti",
    29: "Hücre düşük gerilim", 30: "Hücre düşük gerilim bitti", 31: "Batarya düşük gerilim", 32: "Batarya düşük gerilim bitti",
    33: "Deşarj aşırı akım", 34: "Deşarj aşırı akım bitti", 35: "Deşarj kısa devre", 36: "Deşarj kısa devre bitti",
    37: "Deşarj aşırı sıcaklık", 38: "Deşarj aşırı sıcaklık bitti", 39: "Watchdog sistemi yeniden başlattı",
    40: "Deşarj kısa devre 2", 41: "Elle acil durum açıldı", 43: "Acil durum otomatik kapandı",
    44: "Uygulama BMS'i kapattı", 45: "Düğme ile BMS kapatıldı", 46: "Deşarj açılamadı", 47: "RS485 ile BMS kapatıldı",
    48: "CAN ile şarj kapatıldı", 49: "CAN ile şarj açıldı", 50: "CAN ile deşarj kapatıldı", 51: "CAN ile deşarj açıldı",
    52: "RS485 ile şarj kapatıldı", 53: "RS485 ile şarj açıldı", 54: "RS485 ile deşarj kapatıldı", 55: "RS485 ile deşarj açıldı",
    56: "Uyku moduna girdi", 57: "Şarj MOS anormal", 58: "Deşarj MOS anormal", 59: "Saat ayarlandı",
    60: "Hücre sayısı anormal", 61: "Düğme acil durum açık", 62: "Düğme acil durum kapalı", 63: "Düğme ile zorla ısıtma",
    64: "Deşarj aşırı akım 2", 65: "Deşarj aşırı akım 3", 66: "Kısa devre bırakma başarısız",
    67: "Fabrika ayarı NCM/NCA", 68: "Fabrika ayarı LFP", 69: "Fabrika ayarı LTO",
    70: "Uzaktan acil durum açık", 71: "Uzaktan acil durum kapalı", 72: "Deşarj düşük sıcaklık", 73: "Deşarj düşük sıcaklık bitti",
}


def parse_log_frame(frame: bytes):
    """SystemLogFragmentViewModel '故障记录': veri[0:2]=toplam kayıt, veri[2]=bu paketteki kayıt,
    kayıtlar veri[3]'ten itibaren 24'er bayt."""
    p = payload_of(frame)
    total = u16(p, 0)
    n = min(p[2], 12)
    recs = []
    for k in range(n):
        b = 3 + 24 * k
        ts = u32(p, b) + EPOCH_2020
        code = p[b + 4]
        bits = p[b + 5]
        t = lambda o: None if s8(p, o) == -1 else s8(p, o)
        recs.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)), "ts": ts,
            "code": code, "event": LOG_EVENTS.get(code, f"Olay #{code}"),
            "chg": bool(bits & 1), "dsg": bool(bits & 2), "bal": bool(bits & 4), "heat": bool(bits & 8),
            "max_no": p[b + 6], "min_no": p[b + 7],
            "max_v": u16(p, b + 8) / 1000, "min_v": u16(p, b + 10) / 1000,
            "voltage": u16(p, b + 12) / 100, "current": s16(p, b + 14) / 10,
            "remain_ah": u16(p, b + 16) / 10, "full_ah": u16(p, b + 18) / 10,
            "t_max": t(b + 20), "t_min": t(b + 21), "t_mos": t(b + 22), "heat_a": s8(p, b + 23) / 10,
        })
    return total, recs


def make_demo_log_frames(count=30):
    import random
    frames = []
    now = int(time.time())
    codes = [1, 56, 21, 22, 29, 30, 4, 6, 59, 17, 18, 11, 12, 33, 34, 45, 1, 25, 26]
    recs = []
    for i in range(count):
        ts = now - (count - i) * 3600 * 7 - random.randint(0, 3000)
        code = codes[i % len(codes)]
        v = 52.4 + random.random()
        recs.append((ts, code, 0b0111 if i % 4 else 0b0011, random.randint(1, 16), random.randint(1, 16),
                     int((3.30 + random.random() * .05) * 1000), int((3.27 + random.random() * .02) * 1000),
                     int(v * 100), int(random.uniform(-80, 60) * 10), int(random.uniform(40, 270) * 10), 2800,
                     random.randint(22, 34), random.randint(18, 22), random.randint(25, 40), 0))
    for start in range(0, count, 12):
        chunk = recs[start:start + 12]
        f = bytearray(b"\x55\xAA\xEB\x90\x06\x00") + bytes(293)
        struct.pack_into("<HB", f, 6, count, len(chunk))
        for k, r in enumerate(chunk):
            struct.pack_into("<IBBBBHHHhHHbbbb", f, 6 + 3 + 24 * k, r[0] - EPOCH_2020, *r[1:])
        frames.append(_finish(f))
    return frames
