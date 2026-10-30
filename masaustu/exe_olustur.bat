@echo off
REM Tek dosyalik MGM_BMS.exe olusturur (dist klasorune)
cd /d "%~dp0"
if not exist lisans_anahtar.py (
  echo HATA: lisans_anahtar.py yok. Once: python ..\araclar\gizli_dosyalari_olustur.py
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name MGM_BMS ^
  --add-data "ui;ui" --hidden-import lisans_anahtar --collect-submodules bleak --collect-data webview mgm_bms.py
echo.
echo Hazir: dist\MGM_BMS.exe
pause
