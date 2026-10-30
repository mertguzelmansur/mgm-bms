# MGM BMS – Lisans Üretici (GİZLİ – kimseyle paylaşma)

Bu klasör **yalnızca sende** kalır. `gizli_anahtar.key` dosyası lisans anahtarlarını imzalayan gizli anahtardır.
Bu dosya ele geçirilirse herkes lisans üretebilir; kaybolursa yeni lisans üretemezsin (programı yeni anahtarla
yeniden derlemek gerekir). **Bir USB belleğe ve güvenli bir yere yedekle.**

## Kullanım
1. Müşteri programı ilk açtığında "Lisans etkinleştirme" ekranında **Cihaz Kimliği** görür
   (ör. `MGM-7KQ2-ABCD-EFGH-JK45`) ve sana gönderir (WhatsApp, e-posta…).
2. `uretici_baslat.bat` → Cihaz Kimliğini ve müşteri adını yaz → **Anahtar üret**.
   İstersen bitiş tarihi gir (boş = süresiz).
3. Anahtar panoya kopyalanır (`MGM1-…`). Müşteriye gönder, o da programa yapıştırıp **Etkinleştir**'e basar.

Komut satırından: `python uretici.py MGM-XXXX-XXXX-XXXX-XXXX "Müşteri Adı" 31.12.2027`

Verilen tüm lisanslar `verilen_lisanslar.csv` dosyasına yazılır (Excel'de açılır).

## Nasıl korur
- Anahtar, Cihaz Kimliğine özeldir: başka bilgisayara/telefona kopyalanınca çalışmaz.
- Anahtarlar Ed25519 dijital imzasıyla imzalanır; programda yalnızca **doğrulama** (açık) anahtarı vardır,
  bu yüzden programı inceleyen biri yeni anahtar üretemez.
- Masaüstünde Cihaz Kimliği Windows'un MachineGuid değerinden, Android'de telefonun Android kimliğinden türetilir.
  Windows yeniden kurulursa / telefon fabrika ayarına dönerse kimlik değişir → müşteriye yeni anahtar üretirsin.
