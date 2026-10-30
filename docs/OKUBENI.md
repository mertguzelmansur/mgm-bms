# MGM Lisans

MGM BMS için lisans anahtarı ve fabrika kodu üreten, iPhone'dan kullanılan web uygulaması.
**Bu depoda hiçbir gizli bilgi yoktur.** Gizli anahtar yalnızca kullanıcının telefonunda, kendi parolasıyla
şifrelenmiş olarak durur.

## GitHub Pages'te yayınlama

1. github.com → **New repository** → ad: `mgm-lisans` → **Create repository**
2. **uploading an existing file** → bu klasördeki **tüm dosyaları** sürükle-bırak → **Commit changes**
   (`.nojekyll` gizli dosyadır; görünmüyorsa sorun değil, sayfa onsuz da çalışır)
3. **Settings → Pages** → *Source*: **Deploy from a branch** → Branch: `main` / `/ (root)` → **Save**
4. 1–2 dakika sonra: `https://KULLANICI_ADI.github.io/mgm-lisans/`

Komut satırıyla:

```bash
git init -b main && git add . && git commit -m "MGM Lisans"
git remote add origin https://github.com/KULLANICI_ADI/mgm-lisans.git
git push -u origin main
```

## iPhone'da kurulum (bir kez)

1. Adresi **Safari**'de aç → Paylaş → **Ana Ekrana Ekle**
2. Ana ekrandaki **MGM Lisans** simgesinden aç
3. Bilgisayardaki `MGM_Lisans_Uretici/gizli_anahtar.key` içindeki 64 karakteri yapıştır, en az 10 karakterlik parola belirle

## Kullanım

- **Cihaz lisansı:** müşterinin WhatsApp mesajını yapıştır (Cihaz Kimliği otomatik bulunur) → ad, süre → **Üret** → **WhatsApp**
- **Fabrika kodu:** her cihazda, sınırsız kurulumda çalışan kod
- Anahtarlar 8 karakterdir: `XXXX-XXXX`. Süreli anahtarlar seçilen ayın son gününe kadar geçerlidir.

## Güvenlik

- Parola: PBKDF2-SHA256 (600.000 tur) + AES-256-GCM. Sayfa 10 dk arka planda kalınca kilitlenir.
- `robots.txt` arama motorlarını engeller. Depo herkese açık olabilir; dosyalarda gizli bilgi yoktur.
- **MGM BMS programının kaynak kodunu (lisans.py vb.) bu depoya veya herhangi bir açık depoya YÜKLEME** –
  kısa anahtar doğrulama anahtarı onun içindedir.
