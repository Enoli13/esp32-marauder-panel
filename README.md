# ESP32 Marauder — CachyOS/Linux Araç Takımı

Bare **ESP32-WROOM** (ekransız NodeMCU/DevKit) üzerinde [ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) firmware'ini **terminalden flashlamak** ve **grafik bir panelden kullanmak** için hazırlanmış küçük bir araç takımı. Linux (CachyOS/Arch) için yazıldı.

> Ekransız WROOM'da Marauder, cihaz üstü menü yerine **seri port (CLI)** üzerinden çalışır. Bu repo, o CLI'yi hem kolay yakma scripti hem de düğmeli bir Python GUI ile sarmalar.

## İçerik

| Dosya | İşi |
|---|---|
| `flash-marauder.sh` | En güncel Marauder sürümünü GitHub'dan çekip `esptool` ile WROOM'a yakar (v1.20+ installer-zip yapısına uyumlu). |
| `src/marauder_panel.py` | **Tam kontrol paneli** — tüm Marauder komutları sekmeli düğmelerle, canlı AP tablosu, ham konsol, elle komut. |
| `src/marauder_scanner.py` | **Sade tarayıcı** — sadece WiFi ağlarını canlı tabloda gösterir (otomatik kanal gezme). |

## Gereksinimler

- Linux (CachyOS/Arch komutlarıyla; diğer dağıtımlarda paket adlarını uyarlayın)
- Bir ESP32-WROOM kart ve USB kablo
- `esptool`, `curl`, `jq`, `unzip` (flash scripti için)
- `python-pyserial`, `tk` (GUI için)

Arch/CachyOS'ta:
```bash
sudo pacman -S --needed esptool curl jq unzip python-pyserial tk
```

## 1) Firmware'i yakma

```bash
chmod +x flash-marauder.sh
./flash-marauder.sh            # portu otomatik bulur
# veya portu elle ver:
./flash-marauder.sh /dev/ttyUSB0
```

Script şunları yapar: araçları kurar → kullanıcıyı `uucp` grubuna ekler (seri port izni) → portu bulur → son sürümün `esp32_lddb` dosyalarını indirir → doğru adreslere yazar (`0x1000` bootloader, `0x8000` partition, `0xe000` ota-data, `0x10000` app).

> İlk çalıştırmada port izni için **oturumu kapatıp açman** ya da `newgrp uucp` gerekebilir.
> "Failed to connect" derse: kartın **BOOT** düğmesini basılı tutarak tak, scripti tekrar çalıştır.

## 2) Grafik panel

```bash
python src/marauder_panel.py
```

1. Port'u seç → **Bağlan**.
2. **Ağ Tara** ile çevredeki ağları canlı tabloya doldur (otomatik kanal gezer).
3. Diğer sekmelerden komutları çalıştır; altta ham seri çıktı ve elle komut kutusu var.

Sadece tarayıcı isteyen için: `python src/marauder_scanner.py`.

### Panel sekmeleri
- **Tarama / Sniff** — beacon/probe/deauth/PMKID/raw/SAE sniff, station & AP+STA tarama, paket sayımı. (pasif dinleme)
- **Listeler / Hedef** — AP/STA/SSID listeleri, hedef seçme, kaydet/yükle.
- **Ağ Keşfi** — ağa katılma, recon, ping/ARP/port scan, MAC track.
- **GPS / Wardrive** — konum verisi, wardriving, POI/tracker.
- **Bluetooth** — BLE tarama, BLE spam, Remote ID.
- **Saldırı** — beacon/probe/deauth/evilportal/karma vb. (aktif gönderim)
- **Sistem** — kanal, LED, parlaklık, info, MAC rastgele/klon, reboot.

## ⚠ Yasal ve etik uyarı

Bu araçların **pasif** olanları (sniff/scan/list) yalnızca havayı dinler ve genelde yasaldır. **Aktif** olanları (`attack`, `blespam`, `evilportal`, `karma`, `spoofat`) ortama paket gönderir ve **başkasının ağına/cihazına karşı kullanılması çoğu ülkede suçtur**. Bu işlevleri yalnızca:

- kendine ait ağ ve cihazlarda, veya
- test etmek için **açık, yazılı izin aldığın** sistemlerde

kullan. Sorumluluk tamamen kullanıcıya aittir. Not: bare ESP32'de deauth paketi gönderimi (TX) firmware tarafından zaten kapalıdır.

## Teşekkür

- Firmware: [justcallmekoko/ESP32Marauder](https://github.com/justcallmekoko/ESP32Marauder)
- Bu repo yalnızca Linux tarafı için yakma scripti ve GUI sarmalayıcısıdır; firmware'in yazarı değildir.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
