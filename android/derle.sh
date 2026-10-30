#!/bin/sh
# MGM BMS APK – Gradle'sız derleme (Linux / macOS / Windows'ta Git Bash ya da WSL):
#   aapt2 + javac + dx + uber-apk-signer.  Gereken: JDK 17+, Python 3, curl, unzip, zip
# Önce bir kez:  python ../araclar/gizli_dosyalari_olustur.py
set -e
cd "$(dirname "$0")"
SURUM_KODU=${SURUM_KODU:-9}; SURUM=${SURUM:-4.5}
[ -f app/java/com/mgm/bms/LicenseKey.java ] || { echo "HATA: LicenseKey.java yok → önce: python ../araclar/gizli_dosyalari_olustur.py"; exit 1; }
sh araclar/indir.sh
T=araclar/indir; export JAVA_TOOL_OPTIONS=
rm -rf build out && mkdir -p build/classes out
python3 web_hazirla.py 2>/dev/null || python web_hazirla.py
$T/aapt2 compile --dir app/res -o build/res.zip
$T/aapt2 link -I $T/android.jar --manifest app/AndroidManifest.xml -A build/assets -o build/unsigned.apk \
  --java build/gen --min-sdk-version 24 --target-sdk-version 34 --version-code $SURUM_KODU --version-name $SURUM build/res.zip --auto-add-overlay
javac -source 8 -target 8 -nowarn -encoding UTF-8 -bootclasspath $T/android.jar -d build/classes app/java/com/mgm/bms/*.java build/gen/com/mgm/bms/R.java 2>&1 | grep -v "^warning\|^Note\|^[0-9]* warning" || true
[ -f build/classes/com/mgm/bms/MainActivity.class ] || { echo "HATA: Java derlenemedi"; exit 1; }
java -cp $T/dx.jar com.android.dx.command.Main --dex --min-sdk-version=24 --output=build/classes.dex build/classes
(cd build && zip -q -j unsigned.apk classes.dex)
java -jar $T/uber-apk-signer.jar -a build/unsigned.apk -o build/imzali >/dev/null
cp build/imzali/*.apk out/MGM_BMS_v$SURUM.apk
echo "TAMAM: android/out/MGM_BMS_v$SURUM.apk"
