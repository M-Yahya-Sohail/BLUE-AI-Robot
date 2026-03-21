import customtkinter as ctk
import tkinter as tk
import subprocess
import os
import socket
import re
import platform
import random
import math

# OS Check for Cross-Platform Testing
IS_PI = platform.system() == "Linux"


# ==========================================
# 🔌 SECTION 1: HARDWARE HELPERS
# ==========================================
def get_pi_temp():
    if not IS_PI:
        return 45.0
    try:
        temp_raw = subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8")
        return float(temp_raw.replace("temp=", "").replace("'C\n", ""))
    except Exception:
        return 0.0


def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_wifi_status():
    if not IS_PI:
        return "Signal: Excellent"
    try:
        eth_state = (
            subprocess.check_output(["cat", "/sys/class/net/eth0/operstate"])
            .decode("utf-8")
            .strip()
        )
        if eth_state == "up":
            return "Mode: Ethernet (LAN)"

        cmd_out = subprocess.check_output(["iwconfig", "wlan0"]).decode("utf-8")
        match = re.search(r"Link Quality=(\d+)/(\d+)", cmd_out)
        if match:
            perc = (int(match.group(1)) / int(match.group(2))) * 100
            if perc >= 80:
                return "Signal: Excellent"
            elif perc >= 60:
                return "Signal: Good"
            else:
                return "Signal: Weak"
        return "Signal: Disconnected"
    except Exception:
        return "Mode: LAN Active"


# ==========================================
# 🤖 SECTION 2: BLUE PREMIUM GUI
# ==========================================
class BluePremiumFace(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Settings ---
        self.attributes("-fullscreen", True)
        self.configure(fg_color="#000000")
        self.bind("<Escape>", lambda e: self.on_closing())
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- INTERNAL STATES ---
        self.current_mic_mode = "Online"
        self.current_op_mode = "Performance"
        self.current_vol = 70
        self.current_mic_gain = 50
        self._running = True
        self.mode = "IDLE"
        self.angle = 0
        self.blink_counter = 0

        # --- LAYOUT: SIDEBAR ---
        self.menu_open = False
        self.drawer_container = ctk.CTkFrame(
            self,
            width=0,
            corner_radius=0,
            fg_color="#121212",
            border_width=1,
            border_color="#222222",
        )
        self.drawer_container.pack(side="left", fill="y")
        self.drawer_container.pack_propagate(False)

        self.drawer = ctk.CTkScrollableFrame(
            self.drawer_container, fg_color="transparent", corner_radius=0
        )
        self.drawer.pack(fill="both", expand=True, padx=5, pady=5)

        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.pack(side="right", expand=True, fill="both")

        # --- Eyes Canvas (LOCKED ENGINE) ---
        self.canvas = tk.Canvas(
            self.main_area, width=800, height=480, bg="#000000", highlightthickness=0
        )
        self.canvas.pack(expand=True)
        self.COLORS = {
            "IDLE": "#00e5ff",
            "LISTENING": "#2ecc71",
            "THINKING": "#f1c40f",
            "TRACKING": "#e056fd",
            "SPEAKING": "#FFFFFF",
        }

        self.l_eye = self.canvas.create_oval(
            250, 190, 350, 290, fill=self.COLORS["IDLE"], outline=""
        )
        self.r_eye = self.canvas.create_oval(
            450, 190, 550, 290, fill=self.COLORS["IDLE"], outline=""
        )

        # Thinking Animation Elements
        self.think_arc = self.canvas.create_arc(
            240,
            180,
            360,
            300,
            start=0,
            extent=150,
            outline=self.COLORS["THINKING"],
            width=6,
            style="arc",
            state="hidden",
        )
        self.trail_dots = [
            self.canvas.create_oval(
                0, 0, 0, 0, fill=self.COLORS["THINKING"], state="hidden"
            )
            for _ in range(3)
        ]

        # --- Subtitle Bar ---
        self.sub_frame = ctk.CTkFrame(
            self.main_area,
            fg_color="#1a1a1a",
            corner_radius=15,
            border_width=1,
            border_color="#333333",
        )
        self.sub_frame.pack(side="bottom", pady=40, padx=100, fill="x")
        self.sub_label = ctk.CTkLabel(
            self.sub_frame,
            text="System: Ready",
            font=("Arial", 18),
            text_color="#aaaaaa",
        )
        self.sub_label.pack(pady=12)

        # --- Hamburger Button ---
        self.menu_btn = ctk.CTkButton(
            self.main_area,
            text="☰",
            width=70,
            height=70,
            fg_color="#1c1c1c",
            text_color="#00e5ff",
            font=("Arial", 35, "bold"),
            corner_radius=15,
            command=self.toggle_menu,
        )
        self.menu_btn.place(x=30, y=30)

        self.setup_drawer_content()
        self.animate()
        self.update_hardware_stats()

    def setup_drawer_content(self):
        ctk.CTkLabel(
            self.drawer,
            text="BLUE COMMAND",
            font=("Arial", 24, "bold"),
            text_color="#00e5ff",
        ).pack(pady=20)

        # Power & Health
        self.section_header("POWER & HEALTH")
        self.stat_temp = ctk.CTkLabel(
            self.drawer,
            text="🌡️ CPU: --°C (Nominal)",
            text_color="#00e5ff",
            font=("Arial", 14),
        )
        self.stat_temp.pack(padx=30, anchor="w")
        self.stat_batt = ctk.CTkLabel(
            self.drawer,
            text="🔋 Battery: 100% (Plugged)",
            text_color="#2ecc71",
            font=("Arial", 14),
        )
        self.stat_batt.pack(padx=30, anchor="w")

        # Audio
        self.section_header("AUDIO & MICROPHONE")
        self.mic_switch = ctk.CTkSwitch(
            self.drawer,
            text="Mic Active",
            progress_color="#2ecc71",
            command=self.toggle_mic_hw,
        )
        self.mic_switch.select()
        self.mic_switch.pack(pady=5, padx=30, anchor="w")

        ctk.CTkLabel(
            self.drawer, text="Speaker Volume", font=("Arial", 11), text_color="#888888"
        ).pack(padx=30, anchor="w")
        self.vol_slider = ctk.CTkSlider(
            self.drawer,
            from_=0,
            to=100,
            button_color="#00e5ff",
            command=self.change_volume,
        )
        self.vol_slider.set(self.current_vol)
        self.vol_slider.pack(pady=(2, 10), padx=30, fill="x")

        ctk.CTkLabel(
            self.drawer, text="Mic Gain", font=("Arial", 11), text_color="#888888"
        ).pack(padx=30, anchor="w")
        self.gain_slider = ctk.CTkSlider(
            self.drawer,
            from_=0,
            to=100,
            button_color="#e056fd",
            command=self.change_gain,
        )
        self.gain_slider.set(self.current_mic_gain)
        self.gain_slider.pack(pady=(2, 10), padx=30, fill="x")

        self.mic_seg = ctk.CTkSegmentedButton(
            self.drawer,
            values=["Online", "Offline"],
            selected_color="#00e5ff",
            command=self.update_mic_mode,
        )
        self.mic_seg.set(self.current_mic_mode)
        self.mic_seg.pack(pady=10, padx=30, fill="x")

        # Network
        self.section_header("NETWORK & CONNECTIVITY")
        self.ip_label = ctk.CTkLabel(
            self.drawer,
            text=f"🌐 IP: {get_ip_address()}",
            text_color="#aaaaaa",
            font=("Arial", 13),
        )
        self.ip_label.pack(padx=30, anchor="w")
        self.wifi_label = ctk.CTkLabel(
            self.drawer,
            text=get_wifi_status(),
            text_color="#aaaaaa",
            font=("Arial", 13),
        )
        self.wifi_label.pack(padx=30, anchor="w")

        # Robot Operation Modes
        self.section_header("ROBOT MODES")
        self.op_mode = ctk.CTkSegmentedButton(
            self.drawer,
            values=["Performance", "Personal", "Independant"],
            selected_color="#e056fd",
            command=self.update_op_mode,
        )
        self.op_mode.set(self.current_op_mode)
        self.op_mode.pack(pady=10, padx=30, fill="x")

        # System
        self.section_header("SYSTEM")
        ctk.CTkButton(
            self.drawer,
            text="REBOOT SYSTEM",
            fg_color="#cc8400",
            command=self.reboot_pi,
        ).pack(pady=5, padx=30, fill="x")
        ctk.CTkButton(
            self.drawer, text="SHUT DOWN", fg_color="#990000", command=self.shutdown_pi
        ).pack(pady=5, padx=30, fill="x")

    def section_header(self, text):
        ctk.CTkLabel(
            self.drawer, text=text, font=("Arial", 12, "bold"), text_color="#555555"
        ).pack(pady=(25, 8), padx=25, anchor="w")

    # --- UPDATER FUNCTIONS (SIGNAL LOGS) ---
    def update_subtitle(self, text):
        self.sub_label.configure(text=text)

    def set_expression(self, expression):
        mapping = {
            "NEUTRAL": "IDLE",
            "LISTENING": "LISTENING",
            "THINKING": "THINKING",
            "SPEAKING": "SPEAKING",
            "TRACKING": "TRACKING",
        }
        self.mode = mapping.get(expression.upper(), "IDLE")
        color = self.COLORS.get(self.mode, "#00e5ff")
        self.canvas.itemconfig(self.l_eye, fill=color, state="normal")
        self.canvas.itemconfig(self.r_eye, fill=color, state="normal")
        self.canvas.itemconfig(self.think_arc, state="hidden")
        for dot in self.trail_dots:
            self.canvas.itemconfig(dot, state="hidden", fill=color)

    def change_volume(self, value):
        self.current_vol = int(value)
        print(f"SIGNAL: Speaker Volume -> {self.current_vol}%")
        if IS_PI:
            os.system(f"amixer set Master {self.current_vol}% > /dev/null 2>&1")

    def update_mic_mode(self, val):
        self.current_mic_mode = val
        print(f"SIGNAL: Mic Mode -> {val}")

    def update_op_mode(self, val):
        self.current_op_mode = val
        print(f"SIGNAL: Operation Mode -> {val}")

    def change_gain(self, value):
        self.current_mic_gain = int(value)
        print(f"SIGNAL: Mic Gain -> {self.current_mic_gain}")

    def toggle_mic_hw(self):
        val = self.mic_switch.get()
        print(f"SIGNAL: Mic Mute -> {'OFF' if val == 1 else 'ON'}")
        if IS_PI:
            cmd = "cap" if val == 1 else "nocap"
            os.system(f"amixer set Capture {cmd} > /dev/null 2>&1")

    def shutdown_pi(self):
        print("SIGNAL: System -> Shutdown Triggered")
        if IS_PI:
            os.system("sudo shutdown -h now")
        else:
            self.on_closing()

    def reboot_pi(self):
        print("SIGNAL: System -> Reboot Triggered")
        if IS_PI:
            os.system("sudo reboot")

    # --- ANIMATION ENGINE ---
    def animate(self):
        if not self._running:
            return
        self.angle += 0.15

        if self.mode in ["IDLE", "SPEAKING"]:
            self.blink_counter += 1
            if self.blink_counter >= 40:
                self.canvas.itemconfigure(self.l_eye, state="hidden")
                self.canvas.itemconfigure(self.r_eye, state="hidden")
                if self.blink_counter >= 43:
                    self.canvas.itemconfigure(self.l_eye, state="normal")
                    self.canvas.itemconfigure(self.r_eye, state="normal")
                    self.blink_counter = 0

        elif self.mode == "LISTENING":
            s = 12 * math.sin(self.angle * 0.7)
            self.canvas.coords(self.l_eye, 250 - s, 190 - s, 350 + s, 290 + s)
            self.canvas.coords(self.r_eye, 450 - s, 190 - s, 550 + s, 290 + s)

        elif self.mode == "THINKING":
            self.canvas.itemconfig(self.l_eye, state="hidden")
            self.canvas.itemconfig(self.r_eye, state="hidden")
            self.canvas.itemconfig(
                self.think_arc, state="normal", start=(self.angle * 60) % 360
            )
            for i, dot in enumerate(self.trail_dots):
                self.canvas.itemconfig(dot, state="normal")
                d_angle = (self.angle * 4.5) - (i * 0.6)
                dx, dy = 500 + 45 * math.cos(d_angle), 240 + 45 * math.sin(d_angle)
                self.canvas.coords(dot, dx - 8, dy - 8, dx + 8, dy + 8)

        elif self.mode == "TRACKING":
            if int(self.angle * 10) % 25 == 0:
                tx, ty = random.choice([-35, 0, 35]), random.choice([-25, 0, 25])
                self.canvas.coords(self.l_eye, 250 + tx, 190 + ty, 350 + tx, 290 + ty)
                self.canvas.coords(self.r_eye, 450 + tx, 190 + ty, 550 + tx, 290 + ty)

        self.after(50, self.animate)

    def update_hardware_stats(self):
        if not self._running:
            return
        temp = get_pi_temp()
        color = "#00e5ff" if temp < 70 else ("#f1c40f" if temp < 80 else "#e74c3c")
        self.stat_temp.configure(text=f"🌡️ CPU: {temp}°C", text_color=color)
        self.ip_label.configure(text=f"🌐 IP: {get_ip_address()}")
        self.wifi_label.configure(text=get_wifi_status())
        self.after(5000, self.update_hardware_stats)

    def on_closing(self):
        self._running = False
        self.destroy()

    def toggle_menu(self):
        width = 340 if not self.menu_open else 0
        self.drawer_container.configure(width=width)
        self.menu_open = not self.menu_open


if __name__ == "__main__":
    app = BluePremiumFace()
    # Test expression:
    app.after(1000, lambda: app.set_expression("tracking"))
    app.update_subtitle("Hello! I am Blue")
    app.mainloop()
