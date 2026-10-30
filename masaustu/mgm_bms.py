# -*- coding: utf-8 -*-
"""
MGM BMS – JK-BMS Android uygulamasının (v6.3.01) PC karşılığı.

Arayüz: HTML/CSS (ui/index.html) – pywebview ile Windows'un Edge WebView2 motorunda açılır.
Arka uç: bleak (BLE) + jk_protocol.

Gereksinim:  pip install -r requirements.txt
Çalıştır:    python mgm_bms.py
(pywebview yoksa klasik tkinter arayüzü – mgm_bms_klasik.py – açılır.)
"""
import csv
import datetime as dt
import functools
import json
import os
import queue
import struct
import sys
import threading
import time

import jk_protocol as jk
from ble_worker import BleWorker, HAVE_BLEAK
from gecmis import History
import lisans

APP_TITLE = "MGM BMS"
APP_VERSION = "3.6"


def resource(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _strip(d):
    """JSON'a gidecek sözlükten ham bayt alanlarını çıkarır."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ============================================================================= demo BMS
class DemoBms:
    """Gerçek BMS gibi davranan sahte cihaz: tüm komutları kabul eder ve uygular."""

    def __init__(self, events):
        self.q = events
        self.t0 = time.time()
        info, sett, _ = jk.make_demo_frames(0)
        self.info = bytearray(info)
        self.sett = bytearray(sett)
        self.running = False
        self.paused = False

    def start(self):
        self.running = True
        self._emit(self.info)
        self._emit(self.sett)
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    @staticmethod
    def _fix(b):
        b[-1] = sum(b[:-1]) & 0xFF

    def _emit(self, fr):
        fr = bytes(fr)
        self.q.put(("raw", "RX", fr))
        t = fr[4]
        if t == 3:
            self.q.put(("info", jk.parse_device_info(fr)))
        elif t == 1:
            self.q.put(("settings", jk.parse_settings(fr)))
        elif t == 6:
            self.q.put(("logframe", fr))
        else:
            self.q.put(("cells", jk.parse_cell_info(fr)))

    def _loop(self):
        while self.running:
            if not self.paused:
                _, _, c = jk.make_demo_frames(time.time() - self.t0)
                c = bytearray(c)
                c[6 + 192] = self.sett[6 + 112]   # MOS durumları anahtarları izlesin
                c[6 + 193] = self.sett[6 + 116]
                self._fix(c)
                self._emit(c)
            time.sleep(1)

    def _put_str(self, buf, off, data):
        n = min(data[5], 13)
        buf[6 + off:6 + off + 16] = bytes(data[6:6 + n]).ljust(16, b"\x00")
        self._fix(buf)

    def _send_log(self):
        self.paused = True
        for fr in jk.make_demo_log_frames(30):
            time.sleep(0.35)
            self._emit(fr)
        time.sleep(0.3)
        self.paused = False

    def write(self, data: bytes):
        self.q.put(("raw", "TX", bytes(data)))
        cmd, ln = data[4], data[5]
        later = lambda fn, d=0.25: threading.Timer(d, fn).start()
        if cmd == jk.CMD_SETTINGS_AND_DATA:
            later(lambda: self._emit(self.sett))
        elif cmd == jk.CMD_DEVICE_INFO:
            later(lambda: self._emit(self.info))
        elif cmd == jk.CMD_LOG:
            threading.Thread(target=self._send_log, daemon=True).start()
        elif cmd == jk.CMD_RENAME:
            self._put_str(self.info, 40, data)
        elif cmd in (0x9C, 0xA0, 0x9F):
            self._put_str(self.info, {0x9C: 56, 0xA0: 112, 0x9F: 96}[cmd], data)
        elif cmd in (0x68, 0x69, 0x6A):                 # kimya ön ayarı
            ovp, uvp = {0x68: (4200, 2800), 0x69: (3650, 2500), 0x6A: (2800, 1800)}[cmd]
            struct.pack_into("<I", self.sett, 6 + 12, ovp)
            struct.pack_into("<I", self.sett, 6 + 4, uvp)
            self._fix(self.sett)
        elif 1 <= cmd <= 0x22 and ln == 4:              # ana parametreler
            off = (cmd - 1) * 4
            self.sett[6 + off:6 + off + 4] = data[6:10]
            self._fix(self.sett)
        else:                                           # gelişmiş parametreler
            for f in jk.ADV_FIELDS:
                if f.get("reg") != cmd or f["kind"] == "ro":
                    continue
                val = int.from_bytes(data[6:6 + max(ln, 1)], "little", signed=False)
                if f["kind"] == "bit":
                    if cmd == 107:
                        self.info[6 + 157] = (self.info[6 + 157] & ~8) | (8 if val else 0)
                        self._fix(self.info)
                    else:
                        i = 6 + 281 + cmd // 8
                        self.sett[i] = (self.sett[i] & ~(1 << cmd % 8)) | ((1 if val else 0) << cmd % 8)
                        self._fix(self.sett)
                else:
                    buf = self.sett if f["src"] == "set" else self.info
                    size = struct.calcsize(jk._FMT[f["typ"]])
                    buf[6 + f["off"]:6 + f["off"] + size] = data[6:6 + size]
                    self._fix(buf)
                break


# ============================================================================= JS köprüsü
class Api:
    """pywebview js_api: 'window.pywebview.api.<metod>()' ile JS'ten çağrılır.
    Alt çizgiyle başlayan her şey JS'e kapalıdır."""

    def __init__(self):
        self._lic = lisans.status()
        self._q = queue.Queue()
        self._window = None
        self._ready = False
        self._buffer = []
        self._worker = BleWorker(self._q) if HAVE_BLEAK else None
        self._demo = None
        self._connected = False
        self._settings = None
        self._info = None
        self._spay = None
        self._ipay = None
        self._adv = {}
        self._pending = {}          # ana parametre ofseti -> (değer, zaman)
        self._apending = {}         # gelişmiş anahtar -> (değer, zaman)
        self._csv_file = None
        self._csv = None
        self._log = None
        self._log_recs = []
        self._import = None
        try:
            self._hist = History()
        except Exception as e:                       # kayıt klasörü yazılamıyorsa program yine çalışsın
            print("24 saat kaydı açılamadı:", e)
            self._hist = None
        threading.Thread(target=self._pump, daemon=True).start()

    # ------------------------------------------------------------------ temel
    def ready(self):
        self._ready = True
        buf, self._buffer = self._buffer, []
        for ev in buf:
            self._emit(ev)
        return True

    # ------------------------------------------------------------------ lisans
    def license_info(self):
        return self._lic

    def activate(self, key):
        try:
            self._lic = lisans.activate(str(key))
        except ValueError as e:
            raise RuntimeError(str(e))
        return self._lic

    def meta(self):
        return {"fields": [list(f) for f in jk.SETTING_FIELDS], "adv": jk.adv_meta(), "have_ble": HAVE_BLEAK,
                "name_max": jk.NAME_MAX_LEN, "version": APP_VERSION,
                "actions": {k: v[1] for k, v in jk.ACTIONS.items()},
                "calibrations": {k: list(v) for k, v in jk.CALIBRATIONS.items()},
                "history": self._hist is not None, "cell_hist": self._hist is not None}

    def scan(self):
        self._need_ble()
        self._worker.submit(self._worker.scan(6.0))
        return True

    def connect(self, address):
        self._need_ble()
        self.demo(False)
        self._worker.submit(self._worker.connect(address))
        return True

    def disconnect(self):
        if self._worker:
            self._worker.submit(self._worker.disconnect())
        return True

    def demo(self, on):
        if on and not self._demo:
            if self._connected:
                raise RuntimeError("Demo için önce bağlantıyı kesin")
            self._reset_state()
            self._demo = DemoBms(self._q)
            self._emit({"type": "demo", "on": True})
            self._demo.start()
        elif not on and self._demo:
            self._demo.stop()
            self._demo = None
            self._reset_state()
            self._emit({"type": "demo", "on": False})
        return bool(self._demo)

    # ------------------------------------------------------------------ yazma
    def write_param(self, off, raw):
        off, raw = int(off), int(raw)
        frame = jk.build_setting_write(off, raw)
        self._pending[off] = (raw, time.time())
        self._emit({"type": "pending", "off": off, "state": "sent"})
        self._write(frame)
        self._later(0.6, lambda: self._write(jk.build_command(jk.CMD_SETTINGS_AND_DATA)))
        self._later(5.0, lambda: self._pending_timeout(off))
        return True

    def write_adv(self, key, raw):
        if self._is_old():
            raise RuntimeError("Eski protokollü (24S) BMS'te gelişmiş ayarlar desteklenmiyor")
        raw = int(raw)
        f = jk.ADV_BY_KEY[key]
        frame = jk.build_adv_write(key, raw)
        self._apending[key] = (raw, time.time())
        self._emit({"type": "apending", "key": key, "state": "sent"})
        self._write(frame)
        refresh = jk.CMD_DEVICE_INFO if (f.get("src") == "info" or f.get("reg") == 107) else jk.CMD_SETTINGS_AND_DATA
        self._later(0.6, lambda: self._write(jk.build_command(refresh)))
        self._later(5.0, lambda: self._apending_timeout(key))
        return True

    def rename(self, name):
        self._write(jk.build_rename(name))
        self._later(1.0, lambda: self._write(jk.build_command(jk.CMD_DEVICE_INFO)))
        return True

    def set_string(self, kind, text, old=""):
        if kind not in jk.STRING_CMDS:
            raise ValueError("Bilinmeyen alan")
        cur = (self._info or {}).get({"device_password": "device_password", "setting_password": "setting_password"}.get(kind, ""), "")
        if kind in ("device_password", "setting_password") and cur and old != cur:
            raise ValueError("Eski şifre yanlış")
        self._write(jk.build_string_cmd(kind, text))
        self._later(1.0, lambda: self._write(jk.build_command(jk.CMD_DEVICE_INFO)))
        return True

    def action(self, name):
        if name not in jk.ACTIONS:
            raise ValueError("Bilinmeyen işlem")
        self._write(jk.build_action(name))
        if name.startswith("preset_"):
            self._later(1.0, lambda: self._write(jk.build_command(jk.CMD_SETTINGS_AND_DATA)))
        return jk.ACTIONS[name][1]

    def calibrate(self, kind, raw):
        self._write(jk.build_calibration(kind, int(raw)))
        return True

    def sync_time(self):
        self._write(jk.build_time_sync())
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def refresh(self):
        self._write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
        self._later(0.5, lambda: self._write(jk.build_command(jk.CMD_DEVICE_INFO)))
        return True

    def send_cmd(self, text):
        h = "".join(ch for ch in str(text) if ch in "0123456789abcdefABCDEF")
        if len(h) == 2:
            frame = jk.build_command(int(h, 16))
        elif len(h) >= 4 and len(h) % 2 == 0:
            frame = bytes.fromhex(h)
        else:
            raise ValueError("Geçersiz hex komut")
        self._write(frame)
        return True

    # ------------------------------------------------------------------ yedek / geri yükleme
    def export_params(self):
        if not self._settings:
            raise RuntimeError("Önce BMS'e bağlanın ve ayarların okunmasını bekleyin")
        info = self._info or {}
        data = {
            "uygulama": "MGM BMS", "surum": APP_VERSION, "tarih": dt.datetime.now().isoformat(timespec="seconds"),
            "model": info.get("model"), "seri": info.get("serial"), "ad": info.get("name"),
            "parametreler": {str(off): self._settings["_raw"][off] for off, *_ in jk.SETTING_FIELDS},
            "gelismis": {k: v for k, v in self._adv.items() if jk.ADV_BY_KEY[k]["kind"] != "ro"},
            "okunabilir": {f[1]: jk.fmt_setting(f[0], self._settings["_raw"][f[0]]) + (" " + f[4] if f[4] else "")
                           for f in jk.SETTING_FIELDS},
        }
        name = f"MGM_BMS_{(info.get('name') or 'yedek').replace(' ', '_')}_{dt.datetime.now():%Y%m%d_%H%M}.json"
        path = self._save_dialog(name, "JSON dosyası (*.json)")
        if not path:
            return None
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        return os.path.basename(path)

    def import_params(self):
        if not self._settings:
            raise RuntimeError("Önce BMS'e bağlanın ve ayarların okunmasını bekleyin")
        import webview
        res = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=("JSON dosyası (*.json)",))
        if not res:
            return None
        path = res if isinstance(res, str) else res[0]
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        if data.get("uygulama") != "MGM BMS":
            raise ValueError("Bu dosya bir MGM BMS yedeği değil")
        changes = []
        for off_s, raw in data.get("parametreler", {}).items():
            off = int(off_s)
            if off in jk.FIELD_BY_OFF and self._settings["_raw"].get(off) != raw:
                f = jk.FIELD_BY_OFF[off]
                changes.append({"id": f"p{off}", "name": f[1], "cur": self._fmt_p(off, self._settings["_raw"].get(off)),
                                "new": self._fmt_p(off, raw), "raw": raw})
        if not self._is_old():
            for key, raw in data.get("gelismis", {}).items():
                f = jk.ADV_BY_KEY.get(key)
                if f and f["kind"] != "ro" and self._adv.get(key) != raw:
                    changes.append({"id": f"a{key}", "name": f["name"], "cur": self._fmt_a(f, self._adv.get(key)),
                                    "new": self._fmt_a(f, raw), "raw": raw})
        self._import = changes
        return {"file": os.path.basename(path), "model": data.get("model"), "date": data.get("tarih"),
                "changes": changes, "same_model": data.get("model") == (self._info or {}).get("model")}

    def apply_import(self):
        changes, self._import = self._import or [], None
        if not changes:
            return 0

        def run():
            for i, c in enumerate(changes):
                try:
                    if c["id"].startswith("p"):
                        self._write(jk.build_setting_write(int(c["id"][1:]), c["raw"]))
                    else:
                        self._write(jk.build_adv_write(c["id"][1:], c["raw"]))
                except Exception as e:
                    self._emit({"type": "toast", "kind": "err", "text": f"{c['name']}: {e}"})
                self._emit({"type": "import", "done": i + 1, "total": len(changes)})
                time.sleep(0.35)
            self._write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
            time.sleep(0.6)
            self._write(jk.build_command(jk.CMD_DEVICE_INFO))
            time.sleep(1.2)
            bad = [c["name"] for c in changes if not self._verify_change(c)]
            self._emit({"type": "import", "finished": True, "total": len(changes), "failed": bad})
        threading.Thread(target=run, daemon=True).start()
        return len(changes)

    def _verify_change(self, c):
        if c["id"].startswith("p"):
            return self._settings and self._settings["_raw"].get(int(c["id"][1:])) == c["raw"]
        return self._adv.get(c["id"][1:]) == c["raw"]

    # ------------------------------------------------------------------ arıza kayıtları
    def download_log(self):
        if self._log and time.time() - self._log["last"] < 8:
            raise RuntimeError("İndirme zaten sürüyor")
        self._log = {"recs": {}, "total": None, "start": time.time(), "last": time.time(), "frames": 0}
        self._write(jk.build_command(jk.CMD_LOG))
        self._later(10.0, self._log_watchdog)
        return True

    def save_log(self):
        if not self._log_recs:
            raise RuntimeError("Önce kayıtları indirin")
        name = f"MGM_BMS_kayitlar_{dt.datetime.now():%Y%m%d_%H%M}.csv"
        path = self._save_dialog(name, "CSV dosyası (*.csv)")
        if not path:
            return None
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp, delimiter=";")
            w.writerow(["Zaman", "Olay", "Kod", "Şarj MOS", "Deşarj MOS", "Dengeleme", "Isıtma", "Maks hücre no",
                        "Min hücre no", "Maks hücre V", "Min hücre V", "Batarya V", "Akım A", "Kalan Ah", "Tam Ah",
                        "Maks sıcaklık", "Min sıcaklık", "MOS sıcaklık", "Isıtma akımı A"])
            for r in self._log_recs:
                w.writerow([r["time"], r["event"], r["code"], *("AÇIK" if r[k] else "KAPALI" for k in ("chg", "dsg", "bal", "heat")),
                            r["max_no"], r["min_no"], f"{r['max_v']:.3f}", f"{r['min_v']:.3f}", f"{r['voltage']:.2f}",
                            f"{r['current']:.1f}", f"{r['remain_ah']:.1f}", f"{r['full_ah']:.1f}",
                            r["t_max"], r["t_min"], r["t_mos"], f"{r['heat_a']:.1f}"])
        return os.path.basename(path)

    def _log_finish(self, ok=True):
        lg, self._log = self._log, None
        if not lg:
            return
        recs = sorted(lg["recs"].values(), key=lambda r: r["ts"], reverse=True)
        self._log_recs = recs
        if not ok and not recs:
            self._emit({"type": "log", "state": "fail", "text": "BMS kayıt göndermedi (bu model desteklemiyor olabilir)"})
        else:
            self._emit({"type": "log", "state": "done", "records": recs, "total": lg["total"]})

    def _log_watchdog(self):
        lg = self._log
        if not lg:
            return
        if time.time() - lg["last"] >= 4.5:
            self._log_finish(ok=bool(lg["recs"]))
        else:
            self._later(1.5, self._log_watchdog)

    # ------------------------------------------------------------------ CSV
    def csv(self, on):
        if on and not self._csv:
            path = self._save_dialog(f"mgmbms_{dt.datetime.now():%Y%m%d_%H%M%S}.csv", "CSV dosyası (*.csv)")
            if not path:
                return False
            self._csv_file = open(path, "w", newline="", encoding="utf-8-sig")
            self._csv = csv.writer(self._csv_file, delimiter=";")
            self._csv.writerow(["zaman", "gerilim_V", "akim_A", "guc_W", "SOC_%", "kalan_Ah", "fark_V",
                                "MOS_C", "T1_C", "T2_C"] + [f"hucre{i}" for i in range(1, 33)])
            self._emit({"type": "toast", "kind": "ok", "text": f"CSV kaydı başladı: {os.path.basename(path)}"})
        elif not on and self._csv:
            self._csv_file.close()
            self._csv_file = self._csv = None
            self._emit({"type": "toast", "kind": "info", "text": "CSV kaydı durduruldu"})
        return bool(self._csv)

    # ------------------------------------------------------------------ 24 saat kaydı
    def _need_hist(self):
        if not self._hist:
            raise RuntimeError("24 saat kaydı kullanılamıyor (kayıt klasörü açılamadı)")
        return self._hist

    def history_rows(self):
        return self._hist.chart_rows() if self._hist else []

    def history_cells(self, seconds=1800):
        return self._hist.cell_rows(float(seconds)) if self._hist else []

    def history_info(self):
        return self._need_hist().info()

    def history_enable(self, on):
        return self._need_hist().set_enabled(on)

    def history_export(self):
        h = self._need_hist()
        if not h.info()["count"]:
            raise RuntimeError("Kayıtta henüz veri yok")
        path = self._save_dialog(f"MGM_BMS_24saat_{dt.datetime.now():%Y%m%d_%H%M}.csv", "CSV dosyası (*.csv)")
        if not path:
            return None
        n = h.export_csv(path)
        return {"file": os.path.basename(path), "count": n}

    def history_clear(self):
        return self._need_hist().clear()

    # ------------------------------------------------------------------ iç işler
    def _need_ble(self):
        if not self._worker:
            raise RuntimeError("Bluetooth için 'pip install bleak' gerekli")

    def _is_old(self):
        return bool(self._info and self._info.get("protocol") == "eski (24S)")

    def _reset_state(self):
        self._pending.clear()
        self._apending.clear()
        self._settings = self._info = self._spay = self._ipay = None
        self._adv = {}
        self._log = None

    @staticmethod
    def _later(sec, fn):
        t = threading.Timer(sec, fn)
        t.daemon = True
        t.start()

    @staticmethod
    def _fmt_p(off, raw):
        if raw is None:
            return "—"
        f = jk.FIELD_BY_OFF[off]
        return (jk.fmt_setting(off, raw) + (" " + f[4] if f[4] else "")).strip()

    @staticmethod
    def _fmt_a(f, raw):
        if raw is None:
            return "—"
        if f["kind"] == "bit":
            return "Açık" if raw else "Kapalı"
        if f["kind"] == "select":
            opts = getattr(jk, f["options"])
            return opts[raw] if 0 <= raw < len(opts) else str(raw)
        v = raw * f["scale"]
        txt = str(raw) if f["scale"] == 1 else f"{v:.{1 if f['scale'] == 0.1 else 3}f}"
        return (txt + " " + f.get("unit", "")).strip()

    def _save_dialog(self, name, ftype):
        import webview
        res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name, file_types=(ftype,))
        if not res:
            return None
        path = res if isinstance(res, str) else res[0]
        ext = "." + ftype.split("*.")[-1].rstrip(")")
        return path if path.lower().endswith(ext) else path + ext

    def _write(self, frame):
        if self._demo:
            self._demo.write(frame)
        elif self._connected and self._worker:
            self._worker.submit(self._worker.write(frame))
        else:
            raise RuntimeError("Önce BMS'e bağlanın")

    def _pending_timeout(self, off):
        p = self._pending.get(off)
        if p and time.time() - p[1] >= 4.9:
            del self._pending[off]
            cur = self._settings["_raw"].get(off) if self._settings else None
            self._emit({"type": "pending", "off": off, "state": "fail",
                        "text": f"{jk.FIELD_BY_OFF[off][1]}: BMS değeri kabul etmedi"
                                + (f" (şu an {jk.fmt_setting(off, cur)})" if cur is not None else "")})

    def _apending_timeout(self, key):
        p = self._apending.get(key)
        if p and time.time() - p[1] >= 4.9:
            del self._apending[key]
            f = jk.ADV_BY_KEY[key]
            self._emit({"type": "apending", "key": key, "state": "fail",
                        "text": f"{f['name']}: BMS değeri kabul etmedi (şu an {self._fmt_a(f, self._adv.get(key))})"})

    def _emit(self, ev):
        if not (self._window and self._ready):
            if len(self._buffer) < 200:
                self._buffer.append(ev)
            return
        code = f"window.MGM && MGM.onEvent({json.dumps(ev, ensure_ascii=False)})"
        try:
            (self._window.run_js if hasattr(self._window, "run_js") else self._window.evaluate_js)(code)
        except Exception:
            pass

    def _pump(self):
        while True:
            ev = self._q.get()
            kind, args = ev[0], ev[1:]
            try:
                getattr(self, "_on_" + kind)(*args)
            except Exception as e:  # arayüzü asla düşürme
                self._emit({"type": "toast", "kind": "err", "text": f"İç hata: {e}"})

    def _recompute_adv(self):
        if self._is_old():
            self._emit({"type": "adv", "raw": {}, "supported": False})
            return
        self._adv = jk.parse_advanced(self._spay, self._ipay)
        for key, (want, _) in list(self._apending.items()):
            if self._adv.get(key) == want:
                del self._apending[key]
                f = jk.ADV_BY_KEY[key]
                self._emit({"type": "apending", "key": key, "state": "ok",
                            "text": f"{f['name']} = {self._fmt_a(f, want)} kaydedildi"})
        self._emit({"type": "adv", "raw": self._adv, "supported": True})

    def _on_status(self, text):
        self._emit({"type": "status", "text": text})

    def _on_error(self, text):
        self._emit({"type": "error", "text": text})

    def _on_scan(self, devs):
        self._emit({"type": "scan", "devices": [{"jk": j, "rssi": r, "name": n, "addr": a} for j, r, n, a in devs]})

    def _on_connected(self, ok):
        self._connected = ok
        self._reset_state()
        self._emit({"type": "connected", "ok": ok})

    def _on_raw(self, direction, data):
        self._emit({"type": "raw", "dir": direction, "hex": data.hex(" ").upper(), "len": len(data)})

    def _on_info(self, info):
        self._ipay = info.get("_payload")
        self._info = info
        self._emit({"type": "info", "info": _strip(info)})
        self._recompute_adv()

    def _on_settings(self, s):
        self._settings = s
        self._spay = s.get("_payload")
        for off, (want, _) in list(self._pending.items()):
            got = s["_raw"].get(off)
            if got == want:
                del self._pending[off]
                self._emit({"type": "pending", "off": off, "state": "ok",
                            "text": f"{jk.FIELD_BY_OFF[off][1]} = {jk.fmt_setting(off, got)} kaydedildi"})
        self._emit({"type": "settings", "raw": {str(k): v for k, v in s["_raw"].items()}})
        self._recompute_adv()

    def _on_logframe(self, frame):
        lg = self._log
        if not lg:
            return
        total, recs = jk.parse_log_frame(frame)
        lg["total"] = total
        lg["frames"] += 1
        lg["last"] = time.time()
        for r in recs:
            lg["recs"][(r["ts"], r["code"], r["voltage"])] = r
        self._emit({"type": "log", "state": "progress", "got": len(lg["recs"]), "total": total})
        if total and len(lg["recs"]) >= total:
            self._log_finish()

    def _on_cells(self, d):
        if self._log and self._log["frames"] > 0:      # uygulama: 0x02 gelince günlük bitmiş sayılır
            self._log_finish()
        self._emit({"type": "cells", "d": d})
        if self._hist and not self._demo:              # demo verisi kalıcı kayda girmez
            try:
                self._hist.add(d)
            except Exception:
                pass
        if self._csv:
            t = d["temps"]
            self._csv.writerow([dt.datetime.now().isoformat(timespec="seconds"), f"{d['voltage']:.3f}",
                                f"{d['current']:.3f}", f"{d['power']:.1f}", d["soc"], f"{d['remain_ah']:.3f}",
                                f"{d['delta_cell']:.3f}", d["mos_temp"], t[0], t[1]] + [f"{c:.3f}" for c in d["cells"]])
            self._csv_file.flush()

    def _on_close(self, *_):
        try:
            if self._demo:
                self._demo.stop()
            if self._worker:
                self._worker.submit(self._worker.disconnect()).result(timeout=3)
        except Exception:
            pass
        if self._csv_file:
            self._csv_file.close()
        if self._hist:
            self._hist.close()


# lisans yoksa JS'ten çağrılabilen her yöntem reddedilir (arayüz atlatılsa bile)
_LIC_FREE = {"ready", "meta", "license_info", "activate"}


def _lic_gate(fn):
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        if not (self._lic and self._lic.get("ok")):
            raise RuntimeError("Lisans gerekli – önce programı etkinleştirin")
        return fn(self, *a, **k)
    return wrapper


for _n, _f in list(vars(Api).items()):
    if callable(_f) and not _n.startswith("_") and _n not in _LIC_FREE:
        setattr(Api, _n, _lic_gate(_f))


def main():
    try:
        import webview
    except ImportError:
        print("pywebview bulunamadı – klasik arayüz açılıyor. (pip install pywebview)")
        if not lisans.tk_gate():
            return
        import mgm_bms_klasik
        mgm_bms_klasik.App().mainloop()
        return
    api = Api()
    win = webview.create_window(APP_TITLE, resource(os.path.join("ui", "index.html")), js_api=api,
                                width=1380, height=880, min_size=(1160, 760), background_color="#06090f")
    api._window = win
    win.events.closing += api._on_close
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
