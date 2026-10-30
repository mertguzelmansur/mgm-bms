# MGM BMS

JK BMS bataryaları için Bluetooth izleme ve ayar programı – resmi JK-BMS Android uygulamasının yerine,
**Windows masaüstü** ve **Android** için. Her iki sürüm aynı arayüzü ve aynı protokol kodunu kullanır.

**Özellikler:** canlı panel (SOC, gerilim, akım, güç, hücre farkı), hücre başına 30 dk gerilim grafiği ve akım/güç,
2 dk – 24 saat grafikler, 24 saat kalıcı kayıt + CSV, tüm koruma ve gelişmiş parametrelerin düzenlenmesi,
BLE ad değiştirme, şifreler, kalibrasyon, kimya ön ayarları, saat eşitleme, parametre yedeği,
BMS arıza kayıtları, yalnızca JK bataryalarını gösteren tarama, demo modu, lisans sistemi.

## Klasörler

| Klasör | İçerik |
|---|---|
| `masaustu/` | Python masaüstü programı (pywebview + bleak). Arayüz: `masaustu/ui/index.html` (Android ile ortak) |
| `android/` | Yerel Java Android uygulaması (WebView + BLE köprüsü, arka plan servisi, 24 saat kaydı). Gradle gerekmez |
| `lisans-uretici/` | Bilgisayarda lisans anahtarı / fabrika kodu üretici (`gizli_anahtar.key` gerekir) |
| `docs/` | iPhone'dan lisans üretme sayfası (GitHub Pages) |
| `araclar/` | `gizli_dosyalari_olustur.py` – depoya girmeyen gizli dosyaları üretir |
| `.github/workflows/derle.yml` | GitHub'da otomatik APK + Windows EXE derleme |

## ⚠ Gizli dosyalar – depoda YOK

`.gitignore` bunları dışarıda tutar, **elle de eklemeyin**:

- `lisans-uretici/gizli_anahtar.key` – lisans imzalayan ana anahtar (USB'de yedekleyin)
- `masaustu/lisans_anahtar.py`, `android/app/java/com/mgm/bms/LicenseKey.java` – kısa anahtar doğrulama anahtarı

Bilgisayarda derlemeden önce bir kez (gizli_anahtar.key `lisans-uretici/` içindeyken):

```
python araclar/gizli_dosyalari_olustur.py
```

Gizli dosyalar eksikse program çalışır ama 8 karakterlik anahtarları kabul etmez – yani depo yanlışlıkla
herkese açık kalsa bile kimse lisans üretemez. Yine de deponun **Private (gizli)** olması önerilir.

## Çalıştırma / derleme

**Masaüstü (Windows):** `masaustu/baslat.bat` (Python 3.10+). Tek dosya exe: `masaustu/exe_olustur.bat`
(PyInstaller) veya `masaustu/exe_olustur_nuitka.bat` (C'ye derler, kurcalamaya daha dayanıklı – müşteriye bunu verin).

**Android:** `sh android/derle.sh` → `android/out/MGM_BMS_v*.apk` (JDK 17, Python 3, curl, unzip, zip;
Windows'ta Git Bash/WSL). Araçlar GitHub'dan indirilip SHA-256 ile doğrulanır.

**GitHub'da otomatik:** Settings → Secrets and variables → Actions → New repository secret
`MGM_DOGRULAMA_ANAHTARI` = `python araclar/gizli_dosyalari_olustur.py --dogrulama-yazdir` çıktısı.
Sonra Actions → **Derle** → *Run workflow* (APK ve EXE "Artifacts" altında) ya da `v3.6` gibi bir
etiket gönderin → otomatik **Release**.

## Lisans sistemi

Program ilk açılışta Cihaz Kimliği gösterir (`MGM-XXXX-XXXX-XXXX-XXXX`). Ona özel 8 karakterlik anahtar
(`XXXX-XXXX`) ya da her cihazda çalışan **fabrika kodu** ile açılır. Üretim: `lisans-uretici/uretici_baslat.bat`
ya da iPhone'dan `docs/` sayfası.

**iPhone sayfası (GitHub Pages):** Settings → Pages → Branch `main` / **`/docs`** → Save.
Ücretsiz GitHub hesabında Pages yalnızca **herkese açık** depolarda çalışır; depo gizliyse `docs/` klasörünü
ayrı, herkese açık bir depoya yükleyin (içinde gizli bilgi yoktur).

---
© MGM – Mert Güzelmansur. Tüm hakları saklıdır.
