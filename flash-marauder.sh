#!/usr/bin/env bash
# ESP32 Marauder flasher for a bare ESP32-WROOM (NodeMCU / DevKit) on CachyOS/Arch.
# v1.20.0+ uyumlu: firmware artık kart başına 4 parça halinde installer zip içinde geliyor.
set -euo pipefail

REPO="justcallmekoko/ESP32Marauder"
TARGET="esp32_lddb"          # bare ESP32-WROOM hedefi
WORKDIR="$(mktemp -d)/marauder"
mkdir -p "$WORKDIR"; cd "$WORKDIR"
echo ">> Çalışma klasörü: $WORKDIR"

# --- 1) Araçlar -------------------------------------------------------------
need() { command -v "$1" >/dev/null 2>&1; }
if ! need esptool.py && ! need esptool; then
  echo ">> esptool kuruluyor..."
  sudo pacman -S --needed --noconfirm esptool || {
    sudo pacman -S --needed --noconfirm python-pipx
    pipx install esptool; export PATH="$HOME/.local/bin:$PATH"
  }
fi
ESPTOOL="$(command -v esptool.py || command -v esptool)"
for t in curl jq unzip; do need "$t" || sudo pacman -S --needed --noconfirm "$t"; done

# --- 2) Seri port izni (uucp) -----------------------------------------------
if ! id -nG "$USER" | grep -qw uucp; then
  echo ">> $USER 'uucp' grubuna ekleniyor."
  sudo usermod -aG uucp "$USER"
  echo "!! Grup için oturumu kapat/aç ya da 'newgrp uucp' çalıştır, sonra scripti tekrar dene."
fi

# --- 3) Port ----------------------------------------------------------------
PORT="${1:-}"
[[ -z "$PORT" ]] && PORT="$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n1 || true)"
if [[ -z "$PORT" ]]; then
  echo "!! ESP32 portu yok. Kartı tak, 'sudo dmesg | tail' ile kontrol et."; exit 1
fi
echo ">> Port: $PORT"

# --- 4) Son sürümü bul, installer zip'ini indir -----------------------------
echo ">> GitHub son sürüm bilgisi alınıyor..."
API="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")"
TAG="$(echo "$API" | jq -r '.tag_name')"
echo ">> Sürüm: $TAG"

ZIP_URL="$(echo "$API" | jq -r '.assets[] | select(.name|endswith("installer-assets.zip")) | .browser_download_url' | head -n1)"
if [[ -z "$ZIP_URL" || "$ZIP_URL" == "null" ]]; then
  echo "!! installer-assets.zip bulunamadı. Varlıkları kontrol et."; exit 1
fi
echo ">> İndiriliyor: $(basename "$ZIP_URL")"
curl -fL --progress-bar -o assets.zip "$ZIP_URL"

# Sadece bu hedefe ait 4 dosyayı çıkar
unzip -o -j assets.zip "*_${TARGET}.bin" "*_${TARGET}.bootloader.bin" \
  "*_${TARGET}.partition-table.bin" "*_${TARGET}.ota-data.bin" -d parts >/dev/null

pick() { ls parts/*"$1" 2>/dev/null | head -n1; }
APP="$(ls parts/*_${TARGET}.bin 2>/dev/null | grep -vE '\.(bootloader|partition-table|ota-data)\.bin$' | head -n1)"
BL="$(pick ".bootloader.bin")"
PT="$(pick ".partition-table.bin")"
OTA="$(pick ".ota-data.bin")"

echo ">> Dosyalar:"; ls -lh parts/
for f in "$APP" "$BL" "$PT" "$OTA"; do
  [[ -f "$f" ]] || { echo "!! Eksik dosya, zip içeriğini kontrol et."; exit 1; }
done

# --- 5) Flashla -------------------------------------------------------------
echo ">> Flashlanıyor... (bağlanamazsa karttaki BOOT düğmesini basılı tutarak tekrar dene)"
"$ESPTOOL" --chip esp32 --port "$PORT" --baud 921600 \
  --before default_reset --after hard_reset \
  write_flash -z --flash_mode keep --flash_freq keep --flash_size detect \
  0x1000  "$BL" \
  0x8000  "$PT" \
  0xe000  "$OTA" \
  0x10000 "$APP"

echo ""
echo ">> BİTTİ. Karttaki RESET düğmesine bas."
echo ">> Bağlanmak için:  screen $PORT 115200   (çıkış: Ctrl-A sonra K, y)"
echo "   screen yoksa:  sudo pacman -S screen"
echo "   Terminal açılınca 'help' yaz; 'scanap', 'sniffbeacon', 'list -a' gibi komutlar WROOM'da çalışır."
