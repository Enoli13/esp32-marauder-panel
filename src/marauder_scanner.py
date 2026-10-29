#!/usr/bin/env python3
"""
Marauder Scanner GUI — ekransız ESP32 WROOM için grafik WiFi tarayıcı.

Çalışan 'sniffbeacon' çıktısını ayrıştırıp ağları canlı bir tabloda gösterir.
Otomatik kanal gezme ile tüm kanallardaki ağları toplar.
scanap/list -a'ya ihtiyaç duymaz.

Kurulum (CachyOS/Arch):
    sudo pacman -S --needed python-pyserial tk
Çalıştırma:
    python marauder_scanner.py
ÖNEMLİ: Porta bağlı başka program (tio/screen/eski GUI) varsa önce kapat.
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
HOP_INTERVAL = 1.5  # saniye

# Örn satır:  -67 Ch: 1 ec:be:5f:c4:53:e6 ESSID: FiberHGW_VE53E1_2.4GHz
BEACON_RE = re.compile(
    r'(-?\d+)\s+Ch:\s*(\d+)\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+ESSID:\s?(.*)'
)


class Scanner:
    def __init__(self, root):
        self.root = root
        self.ser = None
        self.running = False      # seri okuma
        self.scanning = False     # tarama (sniff + hop)
        self.q = queue.Queue()
        self.aps = {}             # bssid -> dict
        self.lock = threading.Lock()

        root.title("Marauder WiFi Tarayıcı")
        root.geometry("1000x680")

        # --- üst bar ---
        top = ttk.Frame(root, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=self.guess_port())
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=20,
                                    values=self.ports())
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(top, text="Yenile", command=lambda: self.port_cb.config(values=self.ports())).pack(side="left")
        self.conn_btn = ttk.Button(top, text="Bağlan", command=self.toggle_conn)
        self.conn_btn.pack(side="left", padx=8)
        self.scan_btn = ttk.Button(top, text="▶ Ağları Tara", command=self.toggle_scan, state="disabled")
        self.scan_btn.pack(side="left", padx=4)
        self.hop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Kanal gez", variable=self.hop_var).pack(side="left", padx=6)
        ttk.Button(top, text="Tabloyu Temizle", command=self.clear_table).pack(side="left", padx=4)
        ttk.Button(top, text="CSV Kaydet", command=self.save_csv).pack(side="left", padx=4)
        self.status = ttk.Label(top, text="● Bağlı değil", foreground="#b00"); self.status.pack(side="left", padx=8)

        # --- tablo ---
        cols = ("ssid", "bssid", "ch", "rssi", "count")
        titles = ("Ağ Adı (SSID)", "MAC (BSSID)", "Kanal", "Sinyal", "Görülme")
        widths = (330, 170, 70, 80, 90)
        frame = ttk.Frame(root, padding=(8, 0)); frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=16)
        for c, t, w in zip(cols, titles, widths):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c != "ssid" else "w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.count_lbl = ttk.Label(root, text="Bulunan ağ: 0", padding=(10, 2))
        self.count_lbl.pack(anchor="w")

        # --- ham çıktı (küçük) ---
        ttk.Label(root, text="Ham seri çıktı / komut:", padding=(10, 0)).pack(anchor="w")
        self.out = tk.Text(root, height=8, bg="#101418", fg="#9fb0bd", font=("monospace", 9))
        self.out.pack(fill="x", padx=8, pady=(0, 4))
        bottom = ttk.Frame(root, padding=(8, 0, 8, 8)); bottom.pack(fill="x")
        self.entry = ttk.Entry(bottom); self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_manual())
        ttk.Button(bottom, text="Gönder", command=self.send_manual).pack(side="left", padx=4)

        self.root.after(80, self.drain)
        self.root.after(1000, self.refresh_table)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- port ----
    def ports(self):
        return [p.device for p in list_ports.comports()]

    def guess_port(self):
        for p in self.ports():
            if "USB" in p or "ACM" in p:
                return p
        return "/dev/ttyUSB0"

    # ---- bağlantı ----
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
        self.scan_btn.config(state="normal")
        self.status.config(text=f"● Bağlı: {port}", foreground="#0a0")
        self.log(f">> Bağlandı: {port}\n")

    def disconnect(self):
        self.stop_scan()
        self.running = False
        try:
            self.ser and self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.conn_btn.config(text="Bağlan")
        self.scan_btn.config(state="disabled")
        self.status.config(text="● Bağlı değil", foreground="#b00")

    # ---- tarama ----
    def toggle_scan(self):
        self.stop_scan() if self.scanning else self.start_scan()

    def start_scan(self):
        if not self.ser:
            return
        self.scanning = True
        self.scan_btn.config(text="■ Durdur")
        self.write("stopscan")      # önce temiz başla
        time.sleep(0.2)
        self.write("sniffbeacon")
        if self.hop_var.get():
            threading.Thread(target=self.hop_loop, daemon=True).start()
        self.log(">> Tarama başladı (sniffbeacon)\n")

    def stop_scan(self):
        if not self.scanning:
            return
        self.scanning = False
        self.scan_btn.config(text="▶ Ağları Tara")
        self.write("stopscan")
        self.log(">> Tarama durdu\n")

    def hop_loop(self):
        i = 0
        while self.scanning and self.ser:
            ch = HOP_CHANNELS[i % len(HOP_CHANNELS)]
            self.write(f"channel -s {ch}")
            i += 1
            t = 0
            while self.scanning and t < HOP_INTERVAL:
                time.sleep(0.1); t += 0.1

    # ---- seri ----
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
        try:
            self.ser and self.ser.write((cmd + "\n").encode())
        except Exception as e:
            self.log(f"!! Yazma hatası: {e}\n")

    def send_manual(self):
        c = self.entry.get().strip()
        if c:
            self.write(c); self.log(f"> {c}\n"); self.entry.delete(0, "end")

    # ---- işleme ----
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
        else:
            # komut yankısı / diğer mesajlar ham pencereye
            if line.strip():
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
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="aglar.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with self.lock:
            rows = sorted(self.aps.items(), key=lambda kv: kv[1]["rssi"], reverse=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["SSID", "BSSID", "Kanal", "Sinyal(dBm)", "Gorulme"])
            for bssid, ap in rows:
                w.writerow([ap["ssid"], bssid, ap["ch"], ap["rssi"], ap["count"]])
        self.log(f">> Kaydedildi: {path}\n")

    # ---- çıktı ----
    def log(self, text):
        self.q.put(("log", text))

    def _append(self, text):
        self.out.insert("end", text)
        # pencereyi makul tut
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
    Scanner(root)
    root.mainloop()
