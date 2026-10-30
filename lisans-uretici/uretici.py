# -*- coding: utf-8 -*-
"""MGM BMS – Lisans Anahtarı Üretici (YALNIZCA MGM'DE KALIR, MÜŞTERİYE VERİLMEZ).

Müşterinin programında gördüğü Cihaz Kimliğini ve adını gir → o cihaza özel lisans anahtarı üretilir.
Aynı anahtar masaüstü programında da Android uygulamasında da çalışır (cihaz kimliğine göre).
Verilen her lisans 'verilen_lisanslar.csv' dosyasına yazılır.

Komut satırı:  python uretici.py MGM-XXXX-XXXX-XXXX-XXXX "Müşteri Adı" [bitiş: GG.AA.YYYY]
               python uretici.py FABRIKA "Firma Adı" [bitiş]      → her cihazda çalışan fabrika kodu
Arayüz:        python uretici.py
"""
import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "masaustu"))     # depo içinde: ortak lisans.py
import lisans as L  # noqa: E402

KEY_FILE = os.path.join(HERE, "gizli_anahtar.key")
LOG_FILE = os.path.join(HERE, "verilen_lisanslar.csv")


def load_secret():
    sk = bytes.fromhex(open(KEY_FILE).read().strip())
    if L.public_from_secret(sk).hex() != L.PUBLIC_KEY_HEX:
        raise RuntimeError("gizli_anahtar.key bu programın açık anahtarıyla eşleşmiyor!")
    return sk


def make_key(device_text, name, expires=None):
    """device_text 'FABRIKA' ise her cihazda çalışan fabrika kodu üretir."""
    factory = device_text.strip().upper() in ("FABRIKA", "FABRİKA", "FACTORY")
    dev = None if factory else L.parse_device(device_text)
    if not name.strip():
        raise ValueError("Müşteri / firma adı boş olamaz")
    key = L.make_key8(load_secret(), dev, expires)
    L.check_any(key, dev=dev or L.parse_device("MGM-AAAA-AAAA-AAAA-AAAA"))   # üretileni hemen doğrula
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new:
            w.writerow(["tarih", "musteri", "cihaz_kimligi", "bitis", "anahtar"])
        w.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M"), name.strip(), "FABRİKA KODU" if factory else L.format_device(dev),
                    L._month_end(L._month_index(expires)).strftime("%d.%m.%Y") if expires else "süresiz", key])
    return key


def parse_date(s):
    s = (s or "").strip()
    return dt.datetime.strptime(s, "%d.%m.%Y").date() if s else None


def gui():
    import tkinter as tk
    bg, card, fg, mu, acc = "#0b1119", "#141c27", "#e8eef6", "#8b97a8", "#2ee6b5"
    w = tk.Tk()
    w.title("MGM BMS – Lisans Üretici")
    w.configure(bg=bg)
    w.resizable(False, False)

    def lbl(t, **k):
        tk.Label(w, text=t, bg=bg, fg=mu, font=("Segoe UI", 10)).pack(padx=22, anchor="w", **k)

    tk.Label(w, text="Lisans Anahtarı Üret", bg=bg, fg=fg, font=("Segoe UI", 15, "bold")).pack(padx=22, pady=(18, 10), anchor="w")
    fab = tk.BooleanVar(value=False)
    lbl("Müşterinin Cihaz Kimliği (MGM-XXXX-XXXX-XXXX-XXXX)")
    e_dev = tk.Entry(w, font=("Consolas", 13), relief="flat", bg=card, fg=acc, insertbackground=fg, width=40)
    e_dev.pack(padx=22, pady=(2, 4), fill="x", ipady=6)

    def tog():
        e_dev.configure(state="disabled" if fab.get() else "normal")
    tk.Checkbutton(w, text="Fabrika kodu (her cihazda, sınırsız kurulum)", variable=fab, command=tog, bg=bg, fg=fg,
                   selectcolor=card, activebackground=bg, activeforeground=fg, font=("Segoe UI", 10)).pack(padx=18, pady=(0, 8), anchor="w")
    lbl("Müşteri / firma adı (kayıt için)")
    e_name = tk.Entry(w, font=("Segoe UI", 12), relief="flat", bg=card, fg=fg, insertbackground=fg)
    e_name.pack(padx=22, pady=(2, 10), fill="x", ipady=5)
    lbl("Bitiş tarihi (GG.AA.YYYY – boş bırakılırsa süresiz)")
    e_exp = tk.Entry(w, font=("Segoe UI", 12), relief="flat", bg=card, fg=fg, insertbackground=fg)
    e_exp.pack(padx=22, pady=(2, 10), fill="x", ipady=5)
    out = tk.Text(w, height=1, font=("Consolas", 22, "bold"), relief="flat", bg=card, fg=acc, wrap="none", width=12)
    msg = tk.Label(w, text="", bg=bg, fg="#fb7185", font=("Segoe UI", 10))

    def go():
        try:
            key = make_key("FABRIKA" if fab.get() else e_dev.get(), e_name.get(), parse_date(e_exp.get()))
            out.delete("1.0", "end")
            out.insert("1.0", key)
            w.clipboard_clear()
            w.clipboard_append(key)
            msg.configure(text="Anahtar üretildi ve panoya kopyalandı ✓ (verilen_lisanslar.csv'ye yazıldı)", fg=acc)
        except Exception as e:
            msg.configure(text=f"Hata: {e}", fg="#fb7185")

    tk.Button(w, text="Anahtar üret", command=go, relief="flat", bg=acc, fg="#03231c",
              font=("Segoe UI", 11, "bold"), padx=16, pady=5).pack(padx=22, pady=(0, 10), anchor="e")
    out.pack(padx=22, fill="x")
    msg.pack(padx=22, pady=(6, 18), anchor="w")
    try:
        load_secret()
    except Exception as e:
        msg.configure(text=f"Gizli anahtar okunamadı: {e}")
    w.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        print(make_key(sys.argv[1], sys.argv[2], parse_date(sys.argv[3]) if len(sys.argv) > 3 else None))
    else:
        gui()
