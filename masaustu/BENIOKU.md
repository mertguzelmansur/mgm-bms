# MGM BMS (Python)

JK-BMS Android uygulamasının (v6.3.01 build 275) PC sürümü. APK decompile edilerek
çıkarılan Bluetooth (BLE) protokolü birebir Python'a aktarıldı.

Arayüz HTML/CSS ile yapıldı ve `pywebview` ile Windows'un Edge WebView2 motorunda masaüstü
penceresi olarak açılır (Windows 10/11'de WebView2 hazır gelir). pywebview kurulamazsa program
otomatik olarak eski tkinter arayüzüne (`mgm_bms_klasik.py`) düşer.

## Kurulum
1. Python 3.10+ (Windows'ta kurulumda "Add to PATH" işaretli olsun)
2. `baslat.bat` çift tıkla  – ya da:  `pip install -r requirements.txt`  →  `python mgm_bms.py`
   (Eski arayüz: `baslat_klasik.bat`)
3. Tek .exe istersen: `exe_olustur.bat` → `dist\MGM_BMS.exe`

Bilgisayarda **Bluetooth 4.0+ (BLE)** olmalı. BMS'e aynı anda telefon bağlıysa PC bağlanamaz;
telefondaki uygulamayı kapat.

## Lisans
Program ilk açılışta **Cihaz Kimliği** gösterir (MGM-XXXX-XXXX-XXXX-XXXX). Bu kimliğe özel lisans anahtarı
(MGM1-…) yapıştırılınca etkinleşir; anahtar başka bilgisayarda çalışmaz. Lisans `%APPDATA%\MGM BMS\lisans.key`
dosyasında saklanır. Anahtarlar ayrı "MGM Lisans Üretici" programıyla üretilir (yalnızca MGM'de).

**Dağıtım:** müşteriye .py dosyalarını değil, derlenmiş **MGM_BMS.exe**'yi ver.
- `exe_olustur.bat` – PyInstaller ile hızlı derleme
- `exe_olustur_nuitka.bat` – Nuitka ile C'ye derleme (kopyalamaya/kurcalamaya karşı daha dayanıklı, önerilen)

## Kullanım
- **Cihaz Bul** → açılan pencerede yeşil çerçeveli olanlar JK BMS → tıkla, bağlanır
- **Demo**: BMS olmadan arayüzü sahte veriyle dener
- **CSV kaydı**: her saniyelik veriyi Excel'de açılabilir CSV'ye yazar (`;` ayraçlı)
- Sol menü: Panel (SOC göstergesi, gerilim/akım/güç/fark + mini grafikler, hücre çubukları,
  kontrol anahtarları, sıcaklıklar, alarmlar), Hücreler (ayrıntılı kartlar, direnç, sapma),
  Grafikler (2 dk / 5 dk / 15 dk / 30 dk / 1 sa / 2 sa / 5 sa / 24 sa; üzerine gelince değer ve saat gösterir),
  Ayarlar, Cihaz, Konsol (hex trafik)
- **Hücreler** sayfasında her hücre kartının altında o hücrenin **son 30 dakikalık gerilim grafiği** vardır (üzerine
  gelince değer ve saat; 30 dk içindeki en düşük/en yüksek değer). "Ortak" ölçek hücreleri birbiriyle karşılaştırır,
  "Hücre başına" ölçek her hücrenin kendi değişimini büyütür. Program açılınca grafikler 24 saat kaydından dolar.
  Kartta ayrıca **akım** ve hücrenin **gücü** (hücre gerilimi × akım) görünür. Seri pakette tüm hücrelerden aynı akım
  geçer, BMS hücre başına ayrı akım ölçmez. Aktif dengeleme sırasında en yüksek hücreden alınan ve en düşük hücreye
  verilen dengeleme akımı ilgili kartlarda ayrıca gösterilir.
- **24 saat kaydı** (Grafikler sayfası): gerçek BMS'e bağlıyken her saniyenin verisi (gerilim, akım, güç, fark,
  SOC, sıcaklıklar, kalan Ah ve tüm hücre gerilimleri) otomatik olarak diske yazılır; 24 saatten eskiler kendiliğinden
  silinir. Program kapatılıp açılınca grafikler bu kayıttan dolar; bağlantı olmayan süreler grafikte boşluk olarak görünür.
  **24 saati kaydet (CSV)** tüm kaydı Excel'de açılabilir dosyaya aktarır, **Kaydı sil** (onay sorar) kaydı tamamen siler,
  **Otomatik kayıt** anahtarı kaydı durdurur/başlatır (tercih hatırlanır). Demo verisi kayda girmez.
  Kayıt dosyası: `%APPDATA%\MGM BMS\gecmis_24s.jsonl` (24 saatte yaklaşık 10–15 MB).
- **Ayarlar** sayfası varsayılan olarak kilitlidir. Sağ üstteki kilidi açınca satırlara tıklayıp
  değeri değiştirebilirsin. Değer uygulamadaki min/maks sınırlarıyla kontrol edilir, eşik sıralaması
  bozulursa (ör. OVP < OVP geri dönüş) uyarı çıkar. Yazdıktan sonra ayarlar BMS'ten geri okunur:
  ✓ kaydedildi ya da "BMS değeri kabul etmedi" bildirimi gelir. BMS'te ayar şifresi varsa kilit açarken sorulur.
  ⚠ Koruma değerlerini hücre üreticisinin veri sayfasına göre gir; yanlış değer bataryaya zarar verebilir.
- **Cihaz** sayfasındaki **Adı değiştir** düğmesi BMS'in Bluetooth adını değiştirir (en fazla 13 karakter;
  harf, rakam, - _ . ve boşluk; Türkçe harf olmaz). Yeni ad, yeniden taramada listede görünür.
- Panel'deki Şarj / Deşarj / Dengeleyici anahtarları BMS'teki ayarı değiştirir (onay sorar).
- **Gelişmiş** (kilit Ayarlar ile ortak): ısıtıcı başlama/durma sıcaklığı ve deşarjda ısıtma, sıcaklık sensörlerini
  devre dışı bırakma, deşarj UTP, OCP2/OCP3, akım sınırlayıcı, ön deşarj süresi, özel şarj cihazı, float modu,
  RCV/RFV süreleri, Re-Bulk SOC, acil durum modu ve süresi, aralıklı alarm, LCD buzzer ve 2 kuru kontak (tetik
  kaynağı + tetik/bırakma değeri), akıllı uyku, LCD sürekli açık, UART1–4 (RS485) ve CAN inverter protokolü
  seçimi, cihaz adresi, veri kayıt periyodu, GPS kilitleri, fabrika anahtarları (KERS, hücre filtresi,
  şarj/deşarj kilidi), akım aralığı ve bayi kimliği (salt okunur). Her yazım BMS'ten geri okunup doğrulanır.
- **Kayıtlar**: BMS'in kendi belleğindeki arıza/olay geçmişini indirir (koruma, alarm, açma/kapama, uyku…;
  her kayıtta gerilim, akım, kalan Ah, maks/min hücre, sıcaklıklar ve MOS durumları) ve CSV'ye kaydeder.
- **Araçlar**: parametre yedeği (JSON dışa/içe aktarma – yalnızca farklı değerler listelenir ve yazılır),
  BMS saatini bilgisayarla eşitleme, kimya ön ayarı (LFP / NCM / LTO), ayar ve cihaz şifresi değiştirme,
  kullanıcı verisi 1/2, kalibrasyon (gerilim, akım, SOC, SOH, döngü kapasitesi), yeniden başlat / kapat /
  fabrika ayarı / tüm verileri sil. Riskli işlemler kutuya "ONAYLA" yazmadan çalışmaz.

## Dosyalar
- `jk_protocol.py` – protokol: komut üretimi, çerçeve birleştirme, çözümleme, eski (24S) → yeni dönüşüm
- `ble_worker.py`  – bleak ile BLE bağlantısı (arka plan thread'i)
- `lisans.py`      – lisans doğrulama (Ed25519 imza, cihaz kimliği)
- `gecmis.py`      – son 24 saatlik ölçüm kaydı (diske yazma, eskiyi atma, CSV dışa aktarma)
- `mgm_bms.py`     – uygulama: pywebview penceresi + Python ↔ arayüz köprüsü + demo BMS
- `ui/index.html`  – arayüz (HTML/CSS/JS, internet gerektirmez)
- `mgm_bms_klasik.py` – eski tkinter arayüzü (yedek)

## Protokol özeti
| | |
|---|---|
| Servis / Karakteristik | `FFE0` / `FFE1` (yazma-yanıtsız + bildirim) |
| Komut (20 B) | `AA 55 90 EB cmd len değer(LE) 00… toplam&FF` |
| Cevap (300 B) | `55 AA EB 90 tip sayaç veri[293] toplam&FF` |
| 0x97 | cihaz bilgisi iste → tip 0x03 |
| 0x96 | ayarlar (0x01) + sürekli anlık veri (0x02) |
| 0x1D / 0x1E / 0x1F | şarj / deşarj / denge anahtarı (4 B değer) |
| 0x01–0x22 | ayar yaz: kayıt = ofset/4+1, `AA 55 90 EB kayıt 04 değer(LE, ×oran) …` |
| 0x9B | cihaz adını değiştir: `AA 55 90 EB 9B uzunluk ad[13] toplam` |
| 0x9C / 0xA0 / 0x9F / 0xA2 | cihaz şifresi / ayar şifresi / kullanıcı verisi 1 / 2 (ad ile aynı biçim) |
| 0x24–0x3F | gelişmiş ayarlar; anahtarlar ayar verisinde bayt 281 + kayıt/8, bit kayıt%8 |
| 0xA5–0xB8 | inverter protokolleri, kuru kontak/buzzer, süreler (cihaz bilgisi çerçevesinde okunur) |
| 0x6B | acil durum · 0x6C saat eşitleme (2020'den beri saniye) |
| 0x64 / 0x67 / 0x6E / 0x6F / 0x70 | kalibrasyon: gerilim / akım / SOC / SOH / döngü kapasitesi |
| 0x65 / 0x66 / 0x9D / 0xA3 | kapat / yeniden başlat / fabrika ayarı-geçmiş / tüm veriler |
| 0x68 / 0x69 / 0x6A | NCM / LFP / LTO varsayılanları |
| 0xA7 | arıza kayıtları → 0x06 paketleri (12 kayıt × 24 bayt) |

Anlık veri (0x02) ofsetleri (veri = çerçeve[6:]): hücreler 0–63 (u16 mV ×32), aktif hücre maskesi 64,
ort 68, fark 70, maks/min indeks 72/73, kablo direnci 74–137, MOS sıcaklık 138 (/10),
gerilim 144 (u32 mV), güç 148 (mW), akım 152 (s32 mA), T1/T2 156/158, sistem alarmı 160,
denge akımı 164, denge durumu 166, SOC 167, kalan 168 (mAh), tam 172, döngü 176, SOH 184,
kullanıcı alarmı 186, çalışma süresi 188, şarj/deşarj MOS 192/193, T3-T5 248-252.

## Bilerek eklenmeyenler
- **Firmware güncelleme (OTA):** dosyalar JK sunucusundan geliyor ve iki farklı çip için ayrı protokol var;
  yarıda kalan bir güncelleme BMS'i kullanılmaz hale getirebilir.
- **Servis (bayi) şifresi üreteci:** program ayar kilidini zaten kendisi yönetiyor, gerek yok.
- Bulut/sunucu hesabı, QR eşleştirme, LED bar ürünü ekranı, uygulama güncelleme ve hata raporlama.
- Bayi kimliğini değiştirme (orijinal uygulamanın o BMS'e bağlanmasını engelleyebilir) – yalnızca gösterilir.
