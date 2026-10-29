# ESP32 Marauder — ARCH/Linux Araç Takımı

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

Tarama / Sniff (çoğu pasif — dinleme)
Ağ Tara — sniffbeacon + otomatik kanal gezme; çevredeki tüm AP’leri tabloya döker. (pasif)
Beacon Sniff — AP’lerin sürekli yayınladığı “ben buradayım” (beacon) çerçevelerini dinler; ağ adı/MAC/kanal/sinyal verir. (pasif)
Probe Sniff — cihazların “X ağı burada mı?” diye sorduğu probe isteklerini yakalar. Eğitim açısından çarpıcı: telefonlar daha önce bağlandığı ağların adlarını havaya sorar, bu da cihaz takibine kapı aralar. (pasif)
Deauth Sniff — ortamda birinin deauth saldırısı yapıp yapmadığını tespit eder. (pasif/savunma)
PMKID Sniff — WPA2 el sıkışmasının PMKID parçasını yakalar; teoride sonradan şifre kırma denemesinde kullanılır. (pasif yakalama)
PWN/EAPOL Sniff — WPA 4'lü el sıkışmasını (handshake) yakalar — Pwnagotchi mantığı. (pasif)
Raw Sniff — tüm ham 802.11 paketlerini gösterir, trafik monitörü. (pasif)
SAE Sniff — WPA3'ün SAE el sıkışmalarını dinler. (pasif)
Station Tara (scansta) — AP’lere bağlı istemci cihazları listeler. (pasif)
AP+STA Tara (scanall) — hem ağları hem istemcileri. (pasif)
Paket Say — saniyedeki paket sayısını gösterir (ortam ne kadar yoğun). (pasif)
Listeler / Hedef (sadece yönetim, gönderim yok)
list -a / -c / -s — yakalanan AP’ler / istemciler / kayıtlı SSID’ler.
AP seç / STA seç / Filtreyle seç — sonraki işlemler için hedef işaretler (örn. select -a 0,2).
Temizle / Kaydet / Yükle — listeleri sıfırla ya da SD karta yaz/oku.
Ağ Keşfi (önce o ağın şifresini bilip katılman gerekir)
Ağa katıl (join) — seçili AP’ye normal istemci gibi bağlanır.
Recon WiFi/BLE — çevre/ağ keşfi.
Ping Scan — ağdaki canlı IP’leri bulur. (aktif ama kendi ağında normal)
ARP Scan — ağdaki cihazları MAC/IP ile haritalar.
Port Scan — bir cihazın açık portlarını tarar.
MAC Track — belirli bir MAC’i sinyal gücüyle takip eder (yaklaşıyor mu uzaklaşıyor mu).
GPS / Wardrive
GPS Data/Fix/NMEA — GPS modülü taktıysan konum verisi.
Wardrive — gezerken bulunan ağları konumla kaydeder (haritalama; WiGLE’a yüklenebilir).
POI / Tracker — ilgi noktası işaretleme / iz kaydı.
Bluetooth
BT Tara (sniffbt) — çevredeki BLE cihazlarını listeler. (pasif)
AirTag / iBeacon / Flipper — belirli BLE türlerini süzer. (pasif)
BLE Spam — çevredeki telefonlara sahte eşleşme bildirimleri gönderir (iOS/Android/Windows’ta açılır pencere yağmuru). Aktif, rahatsız edici — sadece kendi cihazında dene.
Remote ID — drone’ların yaydığı kimlik sinyallerini dinler. (pasif)
Saldırı (neredeyse hepsi aktif gönderim — sadece kendi ağında/izinle)
beacon — sahte ağ adlarıyla bir sürü AP yayınlar (listede yüzlerce ağ belirir).
probe — sahte probe isteği seli.
rickroll — SSID’ler olarak şarkı sözleri yayınlar (şaka amaçlı).
deauth — hedef ağdan istemcileri koparmaya çalışır. Bare ESP32'de TX kapalı olduğu için çalışmaz (donanım kısıtı).
badmsg — bozuk yönetim çerçeveleriyle bazı cihazları takılmaya zorlar.
csa — “kanal değiştir” anonsuyla istemcileri başka kanala iter.
sae — WPA3 el sıkışma seli.
Evil Portal — sahte bir giriş sayfası (captive portal) açar; bağlanıp bilgi girenlerin yazdıklarını yakalar. Bu kimlik avı tekniği — kesinlikle sadece kendi test kurulumunda.
Karma — cihazların aradığı ağlara “evet o ağ benim” diyerek bağlanmaya kandırır.
Spoof AP — belirli bir AP’yi taklit eder.
Sistem
Kanal ayarla — radyoyu tek kanala sabitler.
LED / Parlaklık — ışık rengi / ekran parlaklığı.
Bilgi / Ayarlar — cihaz ve ayar bilgisi.
Rastgele AP/STA MAC — kendi MAC’ini rastgeleleştirir (anonimlik).
Reboot / ls / SPIFFS yedekle — yeniden başlat / dosya listele / yedek al.

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
