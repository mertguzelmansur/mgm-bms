#!/bin/sh
# Derleme araçlarını indirir (Gradle / Android Studio gerekmez). Hepsi GitHub'dan, SHA-256 doğrulamalı.
set -e
D="$(cd "$(dirname "$0")" && pwd)/indir"; mkdir -p "$D"; cd "$D"
get() { # url dosya sha256
  if [ -f "$2" ] && echo "$3  $2" | sha256sum -c - >/dev/null 2>&1; then return; fi
  echo "indiriliyor: $2"; curl -sSfL -o "$2" "$1"
  echo "$3  $2" | sha256sum -c - >/dev/null || { echo "HATA: $2 sağlama toplamı tutmadı"; rm -f "$2"; exit 1; }
}
get https://github.com/iBotPeaches/Apktool/releases/download/v2.10.0/apktool_2.10.0.jar apktool.jar c0350abbab5314248dfe2ee0c907def4edd14f6faef1f5d372d3d4abd28f0431
get https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar uber-apk-signer.jar e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835
get https://github.com/pxb1988/dex2jar/releases/download/v2.4/dex-tools-v2.4.zip dex-tools.zip ee7c45eb3c1d2474a6145d8d447e651a736a22d9664b6d3d3be5a5a817dda23a
get https://raw.githubusercontent.com/Sable/android-platforms/master/android-34/android.jar android.jar 6cea1df3efb77103ac3e2beb9bf4718964b0e0869ab16d39d29d5cbae1c147ad
[ -f aapt2 ] || { unzip -o -q -j apktool.jar prebuilt/linux/aapt2_64 -d . && mv aapt2_64 aapt2 && chmod +x aapt2; }
[ -f dx.jar ] || { unzip -o -q -j dex-tools.zip '*/lib/dx-*.jar' -d . && mv dx-*.jar dx.jar; }
echo "Araçlar hazır: $D"
