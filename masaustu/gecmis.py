# -*- coding: utf-8 -*-
"""MGM BMS – son 24 saatlik ölçüm kaydı.

Gerçek BMS'ten gelen her hücre verisi (en fazla saniyede bir) diske eklenir ve 24 saatten eski
kayıtlar düzenli olarak atılır. Program kapatılıp açıldığında grafikler bu kayıttan dolar.

Dosya: Windows'ta %APPDATA%\\MGM BMS\\gecmis_24s.jsonl, diğerlerinde ~/.mgm_bms/gecmis_24s.jsonl
Her satır: [zaman_ms, V, A, W, fark_mV, SOC, MOS, T1, T2, kalan_Ah, [hücre_mV...]]
"""
import csv
import datetime as dt
import json
import os
import threading
import time

KEEP_S = 24 * 3600          # saklama süresi
MIN_STEP_S = 1.0            # iki örnek arası en az süre
COMPACT_EVERY_S = 1800      # bu sıklıkta dosya yeniden yazılıp eski satırlar atılır
FULL_RES_S = 2 * 3600       # arayüze: son 2 saat tam çözünürlük, öncesi seyreltilmiş
OLD_STEP_S = 5.0


def data_dir():
    base = os.environ.get("APPDATA")
    d = os.path.join(base, "MGM BMS") if base else os.path.join(os.path.expanduser("~"), ".mgm_bms")
    os.makedirs(d, exist_ok=True)
    return d


class History:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "gecmis_24s.jsonl")
        self.cfg_path = os.path.join(os.path.dirname(self.path), "ayarlar.json")
        self.rows = []
        self.lock = threading.Lock()
        self.enabled = True
        self._last_t = 0
        self._last_compact = time.time()
        self._fh = None
        self._load_cfg()
        self._load()

    # ------------------------------------------------------------ ayar
    def _load_cfg(self):
        try:
            with open(self.cfg_path, encoding="utf-8") as f:
                self.enabled = bool(json.load(f).get("kayit_24s", True))
        except Exception:
            self.enabled = True

    def set_enabled(self, on):
        self.enabled = bool(on)
        try:
            cfg = {}
            if os.path.exists(self.cfg_path):
                with open(self.cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["kayit_24s"] = self.enabled
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
        except Exception:
            pass
        return self.enabled

    # ------------------------------------------------------------ dosya
    def _load(self):
        cut = (time.time() - KEEP_S) * 1000
        rows = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        if isinstance(r, list) and len(r) >= 9 and r[0] >= cut:
                            rows.append(r)
                    except Exception:
                        continue          # yarım kalmış satır (ani kapanma) – atla
        rows.sort(key=lambda r: r[0])
        self.rows = rows
        if rows:
            self._last_t = rows[-1][0] / 1000
        self._rewrite()

    def _rewrite(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in self.rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        if self._fh:
            self._fh.close()
            self._fh = None
        os.replace(tmp, self.path)
        self._last_compact = time.time()

    def close(self):
        with self.lock:
            if self._fh:
                self._fh.close()
                self._fh = None

    # ------------------------------------------------------------ kayıt
    def add(self, d):
        """parse_cell_info sözlüğünü kaydeder; kaydedilen satırı (ya da None) döndürür."""
        if not self.enabled:
            return None
        now = time.time()
        if now - self._last_t < MIN_STEP_S:
            return None
        t = d.get("temps") or [None, None]
        r = [int(now * 1000), round(d["voltage"], 3), round(d["current"], 3), round(d["power"], 1),
             round(d["delta_cell"] * 1000), d["soc"], d["mos_temp"], t[0] if len(t) > 0 else None,
             t[1] if len(t) > 1 else None, round(d.get("remain_ah", 0), 3),
             [int(round(c * 1000)) for c in d.get("cells", [])]]
        with self.lock:
            self._last_t = now
            self.rows.append(r)
            try:
                if not self._fh:
                    self._fh = open(self.path, "a", encoding="utf-8")
                self._fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                self._fh.flush()
            except Exception:
                pass
            if now - self._last_compact > COMPACT_EVERY_S:
                self._prune(now)
                self._rewrite()
        return r

    def _prune(self, now=None):
        cut = ((now or time.time()) - KEEP_S) * 1000
        i = 0
        while i < len(self.rows) and self.rows[i][0] < cut:
            i += 1
        if i:
            del self.rows[:i]

    def clear(self):
        with self.lock:
            self.rows = []
            self._last_t = 0
            self._rewrite()
        return True

    # ------------------------------------------------------------ arayüze
    def info(self):
        with self.lock:
            self._prune()
            n = len(self.rows)
            first = self.rows[0][0] if n else None
            last = self.rows[-1][0] if n else None
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        return {"count": n, "first": first, "last": last, "bytes": size, "enabled": self.enabled, "path": self.path}

    def chart_rows(self):
        """Grafik için hafif satırlar: [t, V, A, W, fark, SOC, MOS, T1, T2]; 2 saatten eskiler 5 sn'de bir."""
        with self.lock:
            self._prune()
            rows = list(self.rows)
        out, edge, last = [], (time.time() - FULL_RES_S) * 1000, -1e18
        for r in rows:
            if r[0] < edge and r[0] - last < OLD_STEP_S * 1000:
                continue
            last = r[0]
            out.append(r[:9])
        return out

    def cell_rows(self, seconds=1800):
        """Son 'seconds' saniyenin hücre gerilimleri: [[t, [mV, ...]], ...]"""
        cut = (time.time() - seconds) * 1000
        with self.lock:
            return [[r[0], r[10]] for r in self.rows if r[0] >= cut and len(r) > 10]

    def export_csv(self, path):
        with self.lock:
            self._prune()
            rows = list(self.rows)
        ncell = max((len(r[10]) for r in rows if len(r) > 10), default=0)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["zaman", "gerilim_V", "akim_A", "guc_W", "fark_mV", "SOC_%", "MOS_C", "T1_C", "T2_C", "kalan_Ah"]
                       + [f"hucre{i}_V" for i in range(1, ncell + 1)])
            for r in rows:
                cells = r[10] if len(r) > 10 else []
                w.writerow([dt.datetime.fromtimestamp(r[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")]
                           + ["" if v is None else v for v in r[1:10]]
                           + [f"{c / 1000:.3f}" for c in cells])
        return len(rows)
