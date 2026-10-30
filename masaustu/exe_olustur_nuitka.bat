@echo off
REM MGM_BMS.exe'yi Nuitka ile C koduna derleyerek olusturur (lisans kontrolunu sokmek PyInstaller'a gore cok daha zor).
REM Ilk calistirmada Nuitka C derleyicisini (MinGW) kendisi indirir; 5-15 dakika surebilir.
cd /d "%~dp0"
if not exist lisans_anahtar.py (
  echo HATA: lisans_anahtar.py yok. Once: python ..\araclar\gizli_dosyalari_olustur.py
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt nuitka ordered-set zstandard
python -m nuitka --onefile --assume-yes-for-downloads --windows-console-mode=disable ^
  --include-data-dir=ui=ui --include-module=lisans_anahtar --include-package=bleak --include-package=webview --include-package-data=webview ^
  --output-filename=MGM_BMS.exe --output-dir=dist_nuitka mgm_bms.py
echo.
echo Hazir: dist_nuitka\MGM_BMS.exe
pause
