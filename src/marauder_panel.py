#!/usr/bin/env python3
"""
Marauder Control Panel — ESP32 Marauder için tam grafik kontrol paneli.
Tüm CLI komutlarını sekmeli düğmelerle sunar + canlı AP tablosu + elle komut.

Kurulum (CachyOS/Arch):
    sudo pacman -S --needed python-pyserial tk
Çalıştırma:
    python marauder_panel.py
ÖNEMLİ: Porta bağlı başka program (tio/screen/başka GUI) varsa önce kapat.

ETİK/UYARI: 'Saldırı' ve 'Bluetooth spam' işlevlerini yalnızca kendi
ağlarında/cihazlarında veya açık izin aldığın sistemlerde kullan.
Bare ESP32'de deauth paketi gönderimi (TX) firmware tarafından kapalıdır.
"""
import csv
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:
    raise SystemExit("pyserial yok. Kur:  sudo pacman -S --needed python-pyserial tk")

BAUD = 115200
HOP_CHANNELS = [1, 6, 11, 2, 3, 4, 5, 7, 8, 9, 10, 12, 13]
HOP_INTERVAL = 1.5
BEACON_RE = re.compile(
    r'(-?\d+)\s+Ch:\s*(\d+)\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+ESSID:\s?(.*)'
)


class Panel:
    def __init__(self, root):
        self.root = root
        self.ser = None
        self.running = False
        self.scanning = False
        self.q = queue.Queue()
        self.aps = {}
        self.lock = threading.Lock()

        root.title("Marauder Kontrol Paneli")
        root.geometry("1040x760")

        self._build_topbar()
        self._build_tabs()
        self._build_table()
        self._build_console()

        self.root.after(80, self.drain)
        self.root.after(1000, self.refresh_table)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ================= ÜST BAR =================
    def _build_topbar(self):
        top = ttk.Frame(self.root, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=self.guess_port())
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=20, values=self.ports())
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(top, text="Yenile", command=lambda: self.port_cb.config(values=self.ports())).pack(side="left")
        self.conn_btn = ttk.Button(top, text="Bağlan", command=self.toggle_conn)
        self.conn_btn.pack(side="left", padx=8)
        ttk.Button(top, text="■ DURDUR (stopscan)", command=lambda: self.write("stopscan")).pack(side="left", padx=4)
        self.status = ttk.Label(top, text="● Bağlı değil", foreground="#b00")
        self.status.pack(side="left", padx=8)

    # ================= SEKMELER =================
    def _build_tabs(self):
        nb = ttk.Notebook(self.root); nb.pack(fill="x", padx=8, pady=4)

        # --- Tarama / Sniff ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Tarama / Sniff")
        self._btn_row(t, [
            ("▶ Ağ Tara (canlı tablo)", self.toggle_scan, "scan"),
            ("Beacon Sniff", lambda: self.write("sniffbeacon")),
            ("Probe Sniff", lambda: self.write("sniffprobe")),
            ("Deauth Sniff", lambda: self.write("sniffdeauth")),
            ("PMKID Sniff", lambda: self.write("sniffpmkid")),
        ])
        self._btn_row(t, [
            ("PWN/EAPOL Sniff", lambda: self.write("sniffpwn")),
            ("Raw Sniff", lambda: self.write("sniffraw")),
            ("SAE Sniff", lambda: self.write("sniffsae")),
            ("Station Tara", lambda: self.write("scansta")),
            ("AP+STA Tara", lambda: self.write("scanall")),
        ])
        row = ttk.Frame(t); row.pack(fill="x", pady=2)
        ttk.Checkbutton(row, text="Ağ Tara'da kanal gez", variable=tk.BooleanVar(value=True)).pack(side="left")
        self.hop_var = tk.BooleanVar(value=True)
        ttk.Button(row, text="Paket Say", command=lambda: self.write("packetcount")).pack(side="left", padx=4)
        ttk.Button(row, text="Tabloyu Temizle", command=self.clear_table).pack(side="left", padx=4)
        ttk.Button(row, text="CSV Kaydet", command=self.save_csv).pack(side="left", padx=4)

        # --- Listeler / Hedef ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Listeler / Hedef")
        self._btn_row(t, [
            ("AP Listele (list -a)", lambda: self.write("list -a")),
            ("STA Listele (list -c)", lambda: self.write("list -c")),
            ("SSID Listele (list -s)", lambda: self.write("list -s")),
            ("Seçili (list -t)", lambda: self.write("list -t")),
        ])
        self._param_row(t, "AP seç (index):", "select -a {}", "örn: 0,2,5")
        self._param_row(t, "STA seç (index):", "select -c {}", "örn: 1")
        self._param_row(t, "Filtreyle seç:", 'select -a -f "contains {}"', "örn: Fiber")
        self._btn_row(t, [
            ("AP listesini temizle", lambda: self.write("clearlist -a")),
            ("STA temizle", lambda: self.write("clearlist -c")),
            ("Seçimi temizle", lambda: self.write("clearlist -s")),
        ])
        self._btn_row(t, [
            ("AP'leri kaydet (save -a)", lambda: self.write("save -a")),
            ("AP yükle (load -a)", lambda: self.write("load -a")),
            ("SSID kaydet (save -s)", lambda: self.write("save -s")),
            ("SSID yükle (load -s)", lambda: self.write("load -s")),
        ])

        # --- Ağ Keşfi ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Ağ Keşfi")
        ttk.Label(t, text="Bir ağa katıl, sonra tara (recon/scan ağ içi çalışır):",
                  foreground="#567").pack(anchor="w")
        self._param_row(t, "Ağa katıl (AP index):", "join -a {}", "önce AP seç/ara")
        self._param_row(t, "Katıl + şifre (idx pass):", "join -a {}", "idx'i yaz, şifreyi manuel ekle")
        self._btn_row(t, [
            ("Recon WiFi", lambda: self.write("recon wifi")),
            ("Recon BLE", lambda: self.write("recon ble")),
            ("Recon durum", lambda: self.write("recon status")),
            ("Recon durdur", lambda: self.write("recon stop")),
        ])
        self._btn_row(t, [
            ("Ping Scan", lambda: self.write("pingscan")),
            ("ARP Scan", lambda: self.write("arpscan")),
            ("ARP Scan (-f)", lambda: self.write("arpscan -f")),
            ("MAC Track", lambda: self.write("mactrack")),
        ])
        self._param_row(t, "Port Scan (ip index):", "portscan -a -t {}", "ARP'tan gelen index")

        # --- GPS ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="GPS / Wardrive")
        self._btn_row(t, [
            ("GPS Data", lambda: self.write("gpsdata")),
            ("GPS Fix", lambda: self.write("gps -t fix")),
            ("NMEA", lambda: self.write("nmea")),
            ("Wardrive", lambda: self.write("wardrive")),
        ])
        self._btn_row(t, [
            ("GPS POI başlat", lambda: self.write("gpspoi -s")),
            ("GPS POI bitir", lambda: self.write("gpspoi -e")),
            ("Tracker başlat", lambda: self.write("gpstracker -c start")),
            ("Tracker durdur", lambda: self.write("gpstracker -c stop")),
        ])

        # --- Bluetooth ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Bluetooth")
        self._btn_row(t, [
            ("BT Tara (sniffbt)", lambda: self.write("sniffbt")),
            ("AirTag", lambda: self.write("sniffbt -t airtag")),
            ("iBeacon", lambda: self.write("sniffbt -t ibeacon")),
            ("Flipper", lambda: self.write("sniffbt -t flipper")),
        ])
        self._dropdown_row(t, "BLE Spam türü:",
                           ["sourapple", "applejuice", "google", "samsung", "windows", "flipper", "all"],
                           "blespam -t {}")
        self._btn_row(t, [
            ("Remote ID tara", lambda: self.write("remoteid scan")),
            ("Remote ID listele", lambda: self.write("remoteid list")),
        ])

        # --- Saldırı ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Saldırı")
        ttk.Label(t, text="⚠ Yalnızca kendi ağ/cihazlarında kullan. Bare ESP32'de deauth TX kapalıdır.",
                  foreground="#b00").pack(anchor="w", pady=(0, 4))
        ttk.Label(t, text="Önce 'Listeler / Hedef' sekmesinden hedef seç.", foreground="#567").pack(anchor="w")
        self._dropdown_row(t, "Saldırı türü:",
                           ["beacon", "probe", "rickroll", "deauth", "badmsg", "csa", "sae", "quiet", "sleep"],
                           "attack -t {}")
        self._btn_row(t, [
            ("Evil Portal başlat", lambda: self.write("evilportal -c start")),
            ("Evil Portal durdur", lambda: self.write("stopscan")),
            ("Karma", lambda: self.write("karma -p 0")),
        ])
        self._param_row(t, "Spoof AP (index):", "spoofat -t {}", "seçili AP index")

        # --- Sistem ---
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Sistem")
        self._param_row(t, "Kanal ayarla:", "channel -s {}", "1-13")
        self._param_row(t, "LED rengi (hex):", "led -s {}", "örn: FF0000")
        self._param_row(t, "Parlaklık (0-9):", "brightness -s {}", "0-9")
        self._btn_row(t, [
            ("Bilgi (info)", lambda: self.write("info")),
            ("Ayarlar (settings)", lambda: self.write("settings")),
            ("LED rainbow", lambda: self.write("led -p rainbow")),
            ("SD'ye SPIFFS yedekle", lambda: self.write("backupspiffs")),
        ])
        self._btn_row(t, [
            ("Rastgele AP MAC", lambda: self.write("randapmac")),
            ("Rastgele STA MAC", lambda: self.write("randstamac")),
            ("ls /", lambda: self.write("ls /")),
            ("Yeniden başlat", lambda: self.write("reboot")),
        ])

    # ================= CANLI TABLO =================
    def _build_table(self):
        ttk.Label(self.root, text="Canlı AP tablosu (Ağ Tara ile dolar):", padding=(10, 2)).pack(anchor="w")
        cols = ("ssid", "bssid", "ch", "rssi", "count")
        titles = ("Ağ Adı", "MAC", "Kanal", "Sinyal", "Görülme")
        widths = (330, 170, 70, 80, 90)
        frame = ttk.Frame(self.root, padding=(8, 0)); frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        for c, tt, w in zip(cols, titles, widths):
            self.tree.heading(c, text=tt)
            self.tree.column(c, width=w, anchor="w" if c == "ssid" else "center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        bar = ttk.Frame(self.root, padding=(8, 2)); bar.pack(fill="x")
        self.count_lbl = ttk.Label(bar, text="Bulunan ağ: 0")
        self.count_lbl.pack(side="left")
        ttk.Button(bar, text="⌖ Seçili ağı HEDEF yap (Marauder listesine ekle)",
                   command=self.add_selected_as_target).pack(side="right")
        ttk.Label(bar, text="(tabloda bir satıra çift tıkla = hedef yap)",
                  foreground="#789").pack(side="right", padx=8)
        self.tree.bind("<Double-1>", lambda e: self.add_selected_as_target())

    def add_selected_as_target(self):
        """Tablodan seçili AP'yi Marauder'ın iç listesine ekler ve seçer.
        scanap/list -a ekransız kartta listeyi doldurmadığı için köprü budur."""
        sel = self.tree.selection()
        if not sel:
            self.log("!! Önce tablodan bir ağ (satır) seç.\n"); return
        ssid, bssid, ch, rssi, count = self.tree.item(sel[0], "values")
        cmd = f"add -a -b {bssid} -ch {ch}"
        if ssid and ssid != "<gizli>":
            cmd += f" -e {ssid}"
        self.write(cmd)        # Marauder listesine ekler + otomatik seçer
        self.write("list -a")  # index'leri göster
        self.log(f">> HEDEF yapıldı: {ssid} ({bssid}, CH {ch}). "
                 f"Artık 'Saldırı'/'Listeler' sekmelerini kullanabilirsin.\n")

    # ================= HAM KONSOL =================
    def _build_console(self):
        self.out = tk.Text(self.root, height=7, bg="#101418", fg="#9fb0bd", font=("monospace", 9))
        self.out.pack(fill="x", padx=8, pady=(0, 4))
        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8)); bottom.pack(fill="x")
        ttk.Label(bottom, text="Komut:").pack(side="left")
        self.entry = ttk.Entry(bottom); self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", lambda e: self.send_manual())
        ttk.Button(bottom, text="Gönder", command=self.send_manual).pack(side="left")
        ttk.Button(bottom, text="Konsolu temizle", command=lambda: self.out.delete("1.0", "end")).pack(side="left", padx=4)

    # ================= YARDIMCI UI =================
    def _btn_row(self, parent, items):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        for item in items:
            label, cmd = item[0], item[1]
            special = item[2] if len(item) > 2 else None
            b = ttk.Button(row, text=label, command=cmd, width=20)
            b.pack(side="left", padx=2)
            if special == "scan":
                self.scan_btn = b

    def _param_row(self, parent, label, template, hint=""):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=22).pack(side="left")
        e = ttk.Entry(row, width=18); e.pack(side="left", padx=4)
        if hint:
            ttk.Label(row, text=hint, foreground="#789").pack(side="left", padx=4)
        ttk.Button(row, text="Gönder",
                   command=lambda: self.write(template.format(e.get().strip())) if e.get().strip() else None
                   ).pack(side="left", padx=4)

    def _dropdown_row(self, parent, label, options, template):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=22).pack(side="left")
        var = tk.StringVar(value=options[0])
        ttk.Combobox(row, textvariable=var, values=options, width=16, state="readonly").pack(side="left", padx=4)
        ttk.Button(row, text="Gönder", command=lambda: self.write(template.format(var.get()))).pack(side="left", padx=4)

    # ================= PORT / BAĞLANTI =================
    def ports(self):
        return [p.device for p in list_ports.comports()]

    def guess_port(self):
        for p in self.ports():
            if "USB" in p or "ACM" in p:
                return p
        return "/dev/ttyUSB0"

    def toggle_conn(self):
        self.disconnect() if self.ser else self.connect()

    def connect(self):
        port = self.port_var.get().strip()
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
        except Exception as e:
            self.log(f"!! Bağlanılamadı: {e}\n   (Port açık mı? izin/uucp?)\n")
            self.ser = None; return
        self.running = True
        threading.Thread(target=self.read_loop, daemon=True).start()
        self.conn_btn.config(text="Kes")
        self.status.config(text=f"● Bağlı: {port}", foreground="#0a0")
        self.log(f">> Bağlandı: {port}\n")

    def disconnect(self):
        self.scanning = False; self.running = False
        try:
            self.ser and self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.conn_btn.config(text="Bağlan")
        self.status.config(text="● Bağlı değil", foreground="#b00")

    # ================= TARAMA =================
    def toggle_scan(self):
        if self.scanning:
            self.scanning = False
            self.scan_btn.config(text="▶ Ağ Tara (canlı tablo)")
            self.write("stopscan")
        else:
            if not self.ser:
                return
            self.scanning = True
            self.scan_btn.config(text="■ Ağ Tara (durdur)")
            self.write("stopscan"); time.sleep(0.2); self.write("sniffbeacon")
            if self.hop_var.get():
                threading.Thread(target=self.hop_loop, daemon=True).start()

    def hop_loop(self):
        i = 0
        while self.scanning and self.ser:
            self.write(f"channel -s {HOP_CHANNELS[i % len(HOP_CHANNELS)]}")
            i += 1
            t = 0
            while self.scanning and t < HOP_INTERVAL:
                time.sleep(0.1); t += 0.1

    # ================= SERİ =================
    def read_loop(self):
        buf = b""
        while self.running and self.ser:
            try:
                data = self.ser.read(512)
            except Exception as e:
                self.q.put(("log", f"!! Okuma hatası: {e}\n")); break
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.q.put(("line", line.decode("utf-8", "replace")))

    def write(self, cmd):
        if not self.ser:
            self.log("!! Önce Bağlan.\n"); return
        try:
            self.ser.write((cmd + "\n").encode())
            self.log(f"> {cmd}\n")
        except Exception as e:
            self.log(f"!! Yazma hatası: {e}\n")

    def send_manual(self):
        c = self.entry.get().strip()
        if c:
            self.write(c); self.entry.delete(0, "end")

    # ================= İŞLEME =================
    def drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                else:
                    self.handle_line(payload)
        except queue.Empty:
            pass
        self.root.after(80, self.drain)

    def handle_line(self, line):
        m = BEACON_RE.search(line)
        if m:
            rssi, ch, bssid, ssid = int(m.group(1)), int(m.group(2)), m.group(3).lower(), m.group(4).strip()
            with self.lock:
                ap = self.aps.get(bssid)
                if ap:
                    ap["rssi"] = rssi; ap["ch"] = ch; ap["count"] += 1
                    if ssid:
                        ap["ssid"] = ssid
                else:
                    self.aps[bssid] = {"ssid": ssid or "<gizli>", "ch": ch, "rssi": rssi, "count": 1}
        elif line.strip():
            self._append(line + "\n")

    def refresh_table(self):
        with self.lock:
            rows = sorted(self.aps.items(), key=lambda kv: kv[1]["rssi"], reverse=True)
        self.tree.delete(*self.tree.get_children())
        for bssid, ap in rows:
            self.tree.insert("", "end", values=(ap["ssid"], bssid, ap["ch"], ap["rssi"], ap["count"]))
        self.count_lbl.config(text=f"Bulunan ağ: {len(rows)}")
        self.root.after(1000, self.refresh_table)

    def clear_table(self):
        with self.lock:
            self.aps.clear()

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="aglar.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with self.lock:
            rows = sorted(self.aps.items(), key=lambda kv: kv[1]["rssi"], reverse=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["SSID", "BSSID", "Kanal", "Sinyal", "Gorulme"])
            for bssid, ap in rows:
                w.writerow([ap["ssid"], bssid, ap["ch"], ap["rssi"], ap["count"]])
        self.log(f">> Kaydedildi: {path}\n")

    def log(self, text):
        self.q.put(("log", text))

    def _append(self, text):
        self.out.insert("end", text)
        if int(self.out.index("end-1c").split(".")[0]) > 400:
            self.out.delete("1.0", "200.0")
        self.out.see("end")

    def on_close(self):
        self.scanning = False; self.running = False
        try:
            self.ser and self.ser.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Panel(root)
    root.mainloop()
