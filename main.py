import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import ctypes
import gc
import psutil

# ============================================================
# HyperBoost X Pro
# Safe Windows utility and gaming dashboard
# ============================================================


APP_NAME = "HyperBoost X Pro"
APP_VERSION = "3.0.0"
APP_SIZE = "1280x780"

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "hyperboost.log"

DEFAULT_CONFIG = {
    "theme": "dark",
    "auto_refresh_ms": 1000,
    "confirm_cleanup": True,
    "gameloop_path": "",
    "language": "English",
    "start_page": "Dashboard",
    "confirm_close_gameloop": True,
    "show_clock_seconds": True,
    "compact_sidebar": False,
}


DARK = {
    "window": "#070B14",
    "sidebar": "#0C1220",
    "panel": "#111827",
    "panel_alt": "#172033",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "accent": "#00C2FF",
    "accent_hover": "#009DD6",
    "secondary": "#7C5CFC",
    "secondary_hover": "#6548D9",
    "danger": "#EF4444",
    "danger_hover": "#C93636",
    "success": "#22C55E",
    "success_hover": "#169447",
    "warning": "#F59E0B",
    "entry": "#0B1220",
    "border": "#25324A",
}

LIGHT = {
    "window": "#F1F5F9",
    "sidebar": "#FFFFFF",
    "panel": "#FFFFFF",
    "panel_alt": "#E8EEF7",
    "text": "#0F172A",
    "muted": "#64748B",
    "accent": "#0284C7",
    "accent_hover": "#0369A1",
    "secondary": "#6D4AFF",
    "secondary_hover": "#5837D6",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "success": "#16A34A",
    "success_hover": "#15803D",
    "warning": "#D97706",
    "entry": "#F8FAFC",
    "border": "#CBD5E1",
}


def safe_username() -> str:
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USERNAME", "User")


def bytes_to_gb(value: int) -> float:
    return round(value / (1024 ** 3), 1)


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

            if isinstance(saved, dict):
                config.update(saved)

        except (OSError, json.JSONDecodeError):
            pass

    return config


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(config, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


def append_file_log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"[{stamp}] {message}\n")


class HyperBoostApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.config_data = load_config()
        self.palette = DARK if self.config_data["theme"] == "dark" else LIGHT
        self.current_page = ""
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.status_var = tk.StringVar(value="Ready")
        self.clock_var = tk.StringVar(value="")
        self.monitor_job = None
        self.clock_job = None
        self.cleanup_thread = None
        self.restart_requested = False

        self.title(f"⚡ {APP_NAME}")
        self.geometry(APP_SIZE)
        self.minsize(1120, 700)
        self.configure(bg=self.palette["window"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_style()
        self._build_layout()
        self._build_pages()
        start_page = self.config_data.get("start_page", "Dashboard")
        self.show_page(start_page if start_page in self.pages else "Dashboard")
        self._start_clock()
        self.bind("<Control-1>", lambda _event: self.show_page("Dashboard"))
        self.bind("<Control-2>", lambda _event: self.show_page("Gaming"))
        self.bind("<Control-3>", lambda _event: self.show_page("Performance"))
        self.bind("<Control-4>", lambda _event: self.show_page("Processes"))
        self.bind("<Control-5>", lambda _event: self.show_page("Cleaner"))
        self.bind("<F5>", lambda _event: self._refresh_current_page())

        append_file_log("Application started")

    # --------------------------------------------------------
    # Base style
    # --------------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "HB.Horizontal.TProgressbar",
            troughcolor=self.palette["panel_alt"],
            background=self.palette["accent"],
            bordercolor=self.palette["panel_alt"],
            lightcolor=self.palette["accent"],
            darkcolor=self.palette["accent"],
            thickness=14,
        )

        style.configure(
            "HB.Treeview",
            background=self.palette["panel"],
            fieldbackground=self.palette["panel"],
            foreground=self.palette["text"],
            rowheight=30,
            borderwidth=0,
        )

        style.configure(
            "HB.Treeview.Heading",
            background=self.palette["panel_alt"],
            foreground=self.palette["text"],
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )

        style.map(
            "HB.Treeview",
            background=[("selected", self.palette["accent"])],
            foreground=[("selected", "white")],
        )

    # --------------------------------------------------------
    # Main layout
    # --------------------------------------------------------

    def _build_layout(self) -> None:
        sidebar_width = 190 if self.config_data.get("compact_sidebar", False) else 230

        self.sidebar = tk.Frame(
            self,
            bg=self.palette["sidebar"],
            width=sidebar_width,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content_shell = tk.Frame(
            self,
            bg=self.palette["window"],
        )
        self.content_shell.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(
            self.content_shell,
            bg=self.palette["window"],
        )
        self.content.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        self.status_bar = tk.Frame(
            self.content_shell,
            bg=self.palette["sidebar"],
            height=32,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)

        tk.Label(
            self.status_bar,
            textvariable=self.status_var,
            bg=self.palette["sidebar"],
            fg=self.palette["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left", padx=12, fill="x", expand=True)

        tk.Label(
            self.status_bar,
            textvariable=self.clock_var,
            bg=self.palette["sidebar"],
            fg=self.palette["muted"],
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(side="right", padx=12)

        self._build_sidebar()

    def _build_sidebar(self) -> None:
        tk.Label(
            self.sidebar,
            text="⚡ HYPERBOOST\nX PRO",
            bg=self.palette["sidebar"],
            fg=self.palette["text"],
            font=("Segoe UI", 22, "bold"),
            justify="left",
        ).pack(anchor="w", padx=22, pady=(28, 8))

        tk.Label(
            self.sidebar,
            text=f"VERSION {APP_VERSION}  •  FINAL",
            bg=self.palette["sidebar"],
            fg=self.palette["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=24, pady=(0, 10))

        tk.Label(
            self.sidebar,
            text="●  SYSTEM READY",
            bg=self.palette["panel_alt"],
            fg=self.palette["success"],
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
        ).pack(anchor="w", padx=22, pady=(0, 18))

        tk.Frame(
            self.sidebar,
            bg=self.palette["accent"],
            height=3,
        ).pack(fill="x", padx=18, pady=(0, 14))

        items = [
            ("Dashboard", "🏠"),
            ("Gaming", "🎮"),
            ("Performance", "⚡"),
            ("Processes", "📋"),
            ("Cleaner", "🧹"),
            ("System", "💻"),
            ("Settings", "⚙"),
            ("About", "ℹ"),
        ]

        for name, icon in items:
            button = tk.Button(
                self.sidebar,
                text=f"{icon}  {name}",
                command=lambda page=name: self.show_page(page),
                anchor="w",
                font=("Segoe UI", 11, "bold"),
                bg=self.palette["sidebar"],
                fg=self.palette["text"],
                activebackground=self.palette["accent_hover"],
                activeforeground="white",
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=20,
                pady=11,
            )
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[name] = button

        tk.Frame(
            self.sidebar,
            bg=self.palette["border"],
            height=1,
        ).pack(fill="x", padx=16, pady=16)

        tk.Label(
            self.sidebar,
            text=f"Signed in as  {safe_username()}",
            bg=self.palette["sidebar"],
            fg=self.palette["muted"],
            font=("Segoe UI", 9),
            justify="left",
        ).pack(side="bottom", anchor="w", padx=22, pady=(0, 18))

        tk.Label(
            self.sidebar,
            text="LOCAL • SAFE • PRIVATE",
            bg=self.palette["sidebar"],
            fg=self.palette["accent"],
            font=("Segoe UI", 8, "bold"),
            justify="left",
        ).pack(side="bottom", anchor="w", padx=22, pady=(10, 5))

    # --------------------------------------------------------
    # Page management
    # --------------------------------------------------------

    def _build_pages(self) -> None:
        self.pages["Dashboard"] = DashboardPage(self.content, self)
        self.pages["Gaming"] = GamingPage(self.content, self)
        self.pages["Performance"] = PerformancePage(self.content, self)
        self.pages["Processes"] = ProcessManagerPage(self.content, self)
        self.pages["Cleaner"] = CleanerPage(self.content, self)
        self.pages["System"] = SystemPage(self.content, self)
        self.pages["Settings"] = SettingsPage(self.content, self)
        self.pages["About"] = AboutPage(self.content, self)

        for page in self.pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

    def show_page(self, name: str) -> None:
        if name not in self.pages:
            return

        self.current_page = name
        self.pages[name].tkraise()

        for page_name, button in self.nav_buttons.items():
            active = page_name == name

            button.configure(
                bg=self.palette["accent"] if active else self.palette["sidebar"],
                fg="white" if active else self.palette["text"],
            )

        self.status_var.set(f"{name} page")

        performance_page = self.pages.get("Performance")
        process_page = self.pages.get("Processes")

        if name == "Performance":
            self.pages[name].start_monitoring()
        elif performance_page:
            performance_page.stop_monitoring()

        if name == "Processes":
            self.pages[name].start_monitoring()
        elif process_page:
            process_page.stop_monitoring()

        if hasattr(self.pages[name], "on_show"):
            self.pages[name].on_show()

    def _refresh_current_page(self) -> None:
        page = self.pages.get(self.current_page)
        if not page:
            return

        for method_name in ("refresh_processes", "refresh_info", "_refresh_metrics"):
            method = getattr(page, method_name, None)
            if callable(method):
                method()
                self.status_var.set(f"{self.current_page} refreshed")
                return

        self.status_var.set(f"{self.current_page} is already live")

    # --------------------------------------------------------
    # Shared helpers
    # --------------------------------------------------------

    def log(self, message: str) -> None:
        append_file_log(message)
        self.status_var.set(message)

        dashboard = self.pages.get("Dashboard")

        if dashboard and hasattr(dashboard, "append_log"):
            dashboard.append_log(message)

    def set_theme(self, theme: str) -> None:
        if theme not in ("dark", "light"):
            return

        self.config_data["theme"] = theme
        save_config(self.config_data)

        messagebox.showinfo(
            "Theme saved",
            "Theme saved. Restart the app to apply it everywhere.",
        )

    def _start_clock(self) -> None:
        clock_format = (
            "%d/%m/%Y  %H:%M:%S"
            if self.config_data.get("show_clock_seconds", True)
            else "%d/%m/%Y  %H:%M"
        )
        self.clock_var.set(datetime.now().strftime(clock_format))
        self.clock_job = self.after(1000, self._start_clock)

    def request_restart(self) -> None:
        """Rebuild the app automatically so saved theme changes apply immediately."""
        self.restart_requested = True

        if self.clock_job:
            try:
                self.after_cancel(self.clock_job)
            except tk.TclError:
                pass

        performance = self.pages.get("Performance")
        processes = self.pages.get("Processes")

        if performance:
            performance.stop_monitoring()
        if processes:
            processes.stop_monitoring()

        append_file_log("Application interface reloaded")
        self.destroy()

    def on_close(self) -> None:
        self.restart_requested = False

        if self.clock_job:
            try:
                self.after_cancel(self.clock_job)
            except tk.TclError:
                pass

        performance = self.pages.get("Performance")
        processes = self.pages.get("Processes")

        if performance:
            performance.stop_monitoring()
        if processes:
            processes.stop_monitoring()

        append_file_log("Application closed")
        self.destroy()


class BasePage(tk.Frame):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, bg=app.palette["window"])
        self.app = app
        self.palette = app.palette

    def page_header(self, title: str, subtitle: str) -> None:
        tk.Label(
            self,
            text=title,
            bg=self.palette["window"],
            fg=self.palette["text"],
            font=("Segoe UI", 28, "bold"),
        ).pack(anchor="w", pady=(6, 3))

        tk.Label(
            self,
            text=subtitle,
            bg=self.palette["window"],
            fg=self.palette["muted"],
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(0, 10))

        tk.Frame(
            self,
            bg=self.palette["accent"],
            height=2,
            width=90,
        ).pack(anchor="w", pady=(0, 16))

    def panel(self, parent: tk.Widget | None = None) -> tk.Frame:
        return tk.Frame(
            parent or self,
            bg=self.palette["panel"],
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )

    def button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        danger: bool = False,
        width: int = 22,
        variant: str = "primary",
    ) -> tk.Button:
        if danger:
            variant = "danger"

        variants = {
            "primary": ("accent", "accent_hover"),
            "secondary": ("secondary", "secondary_hover"),
            "success": ("success", "success_hover"),
            "danger": ("danger", "danger_hover"),
        }
        normal_key, hover_key = variants.get(variant, variants["primary"])
        bg = self.palette[normal_key]
        hover = self.palette[hover_key]

        button = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            font=("Segoe UI", 10, "bold"),
            bg=bg,
            fg="white",
            activebackground=hover,
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=11,
            pady=10,
            highlightthickness=0,
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg))
        return button


class DashboardPage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.cpu_var = tk.StringVar(value="0%")
        self.ram_var = tk.StringVar(value="0%")
        self.disk_var = tk.StringVar(value="0%")
        self.download_var = tk.StringVar(value="0.0 KB/s")
        self.upload_var = tk.StringVar(value="0.0 KB/s")
        self.health_var = tk.StringVar(value="Checking...")
        net = psutil.net_io_counters()
        self._last_net_sent = net.bytes_sent
        self._last_net_recv = net.bytes_recv
        self._last_net_time = time.monotonic()

        self.page_header(
            "🏠 Dashboard",
            "Live system overview and quick actions.",
        )

        cards = tk.Frame(self, bg=self.palette["window"])
        cards.pack(fill="x")

        self._metric_card(cards, "CPU Usage", self.cpu_var, 0)
        self._metric_card(cards, "RAM Usage", self.ram_var, 1)
        self._metric_card(cards, "Disk C:", self.disk_var, 2)

        network = tk.Frame(self, bg=self.palette["window"])
        network.pack(fill="x", pady=(10, 0))
        self._metric_card(network, "Download", self.download_var, 0)
        self._metric_card(network, "Upload", self.upload_var, 1)
        self._metric_card(network, "System Health", self.health_var, 2)

        quick = self.panel()
        quick.pack(fill="x", pady=16)

        tk.Label(
            quick,
            text="Quick Actions",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        actions = tk.Frame(quick, bg=self.palette["panel"])
        actions.pack(fill="x", padx=18, pady=(0, 18))

        self.button(
            actions,
            "🚀 Launch & Boost",
            lambda: self.app.pages["Gaming"].launch_and_boost(),
        ).pack(side="left", padx=(0, 10))

        self.button(
            actions,
            "🧹 Clean Temporary Files",
            lambda: self.app.pages["Cleaner"].start_cleanup(),
        ).pack(side="left", padx=(0, 10))

        self.button(
            actions,
            "⚡ Open Performance",
            lambda: self.app.show_page("Performance"),
        ).pack(side="left")
        self.progress = ttk.Progressbar(
            quick,
            orient="horizontal",
            mode="determinate",
            length=500,
        )

        self.progress.pack(
            fill="x",
            padx=18,
            pady=(0, 18),
        )

        log_panel = self.panel()
        log_panel.pack(fill="both", expand=True)

        log_header = tk.Frame(log_panel, bg=self.palette["panel"])
        log_header.pack(fill="x", padx=18, pady=(16, 10))

        tk.Label(
            log_header,
            text="Activity Log",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        self.button(
            log_header,
            "📄 Open Log",
            self.open_log_file,
            width=12,
        ).pack(side="right", padx=(8, 0))

        self.button(
            log_header,
            "🧽 Clear",
            self.clear_log,
            width=10,
        ).pack(side="right")

        self.log_box = tk.Text(
            log_panel,
            height=11,
            bg=self.palette["entry"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            bd=0,
            font=("Consolas", 9),
            state="disabled",
        )
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self._refresh_metrics()

    def _metric_card(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        column: int,
    ) -> None:
        card = self.panel(parent)
        card.grid(row=0, column=column, sticky="nsew", padx=6)

        parent.grid_columnconfigure(column, weight=1)

        tk.Label(
            card,
            text=label,
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=16, pady=(14, 4))

        tk.Label(
            card,
            textvariable=variable,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _refresh_metrics(self) -> None:
        if not self.winfo_exists():
            return

        self.cpu_var.set(f"{psutil.cpu_percent()}%")
        self.ram_var.set(f"{psutil.virtual_memory().percent}%")
        self.disk_var.set(f"{psutil.disk_usage('C:\\').percent}%")

        now = time.monotonic()
        net = psutil.net_io_counters()
        elapsed = max(now - self._last_net_time, 0.001)
        down_bps = max(0, net.bytes_recv - self._last_net_recv) / elapsed
        up_bps = max(0, net.bytes_sent - self._last_net_sent) / elapsed
        self.download_var.set(self._format_speed(down_bps))
        self.upload_var.set(self._format_speed(up_bps))

        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("C:\\").percent
        pressure = max(cpu, ram, disk)
        if pressure < 60:
            health = "🟢 Excellent"
        elif pressure < 80:
            health = "🟡 Good"
        else:
            health = "🔴 Busy"
        self.health_var.set(health)

        self._last_net_recv = net.bytes_recv
        self._last_net_sent = net.bytes_sent
        self._last_net_time = now

        self.after(1000, self._refresh_metrics)

    @staticmethod
    def _format_speed(bytes_per_second: float) -> str:
        if bytes_per_second >= 1024 ** 2:
            return f"{bytes_per_second / (1024 ** 2):.2f} MB/s"
        return f"{bytes_per_second / 1024:.1f} KB/s"

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")

        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.app.status_var.set("Dashboard log cleared")

    def open_log_file(self) -> None:
        try:
            LOG_FILE.touch(exist_ok=True)
            os.startfile(LOG_FILE)
        except (OSError, AttributeError) as error:
            messagebox.showerror("Open log", str(error))


class GamingPage(BasePage):
    COMMON_GAMELOOP_PATHS = [
        r"C:\Program Files\TxGameAssistant\AppMarket\AppMarket.exe",
        r"C:\Program Files\TxGameAssistant\AppMarket\GameLoader.exe",
        r"C:\Program Files\TxGameAssistant\ui\AndroidEmulator.exe",
        r"C:\Program Files (x86)\TxGameAssistant\AppMarket\AppMarket.exe",
        r"C:\Program Files (x86)\TxGameAssistant\AppMarket\GameLoader.exe",
        r"C:\Program Files (x86)\TxGameAssistant\ui\AndroidEmulator.exe",
    ]

    GAMELOOP_PROCESS_NAMES = {
        "AndroidEmulator.exe",
        "AndroidEmulatorEn.exe",
        "AndroidEmulatorEx.exe",
        "AppMarket.exe",
        "GameLoader.exe",
        "aow_exe.exe",
        "QMEmulatorService.exe",
    }

    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)



        self.path_var = tk.StringVar(
            value=self.app.config_data.get("gameloop_path", "")
        )
        self.state_var = tk.StringVar(value="🔴 Not running")
        self.gameloop_uptime_var = tk.StringVar(value="Uptime: --")
        self.boost_status_var = tk.StringVar(value="Ready")
        self.boost_progress_var = tk.DoubleVar(value=0)
        self.boost_thread = None

        self.page_header(
            "🎮 Gaming Center",
            "Launch and manage GameLoop safely.",
        )

        status_panel = self.panel()
        status_panel.pack(fill="x")

        tk.Label(
            status_panel,
            text="GameLoop status",
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=(16, 4))

        tk.Label(
            status_panel,
            textvariable=self.state_var,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=18, pady=(0, 4))

        tk.Label(
            status_panel,
            textvariable=self.gameloop_uptime_var,
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=(0, 16))

        path_panel = self.panel()
        path_panel.pack(fill="x", pady=16)

        tk.Label(
            path_panel,
            text="GameLoop executable",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 8))

        row = tk.Frame(path_panel, bg=self.palette["panel"])
        row.pack(fill="x", padx=18, pady=(0, 16))

        tk.Entry(
            row,
            textvariable=self.path_var,
            bg=self.palette["entry"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            font=("Segoe UI", 10),
        ).pack(side="left", fill="x", expand=True, ipady=8)

        self.button(
            row,
            "Browse",
            self.browse_gameloop,
            width=10,
        ).pack(side="left", padx=(10, 0))

        actions = self.panel()  
        actions.pack(fill="x")

        tk.Label(
            actions,
            text="Actions",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        primary_buttons = tk.Frame(actions, bg=self.palette["panel"])
        primary_buttons.pack(fill="x", padx=18, pady=(0, 10))

        self.boost_button = self.button(
            primary_buttons,
            "🚀 Launch & Boost",
            self.launch_and_boost,
            width=19,
        )
        self.boost_button.pack(side="left", padx=(0, 10))

        self.button(
            primary_buttons,
            "⚡ Ultimate Boost",
            self.boost_now,
            width=19,
            variant="secondary",
        ).pack(side="left", padx=(0, 10))

        self.button(
            primary_buttons,
            "🧠 Optimize RAM",
            self.optimize_ram,
            width=19,
            variant="success",
        ).pack(side="left")

        secondary_buttons = tk.Frame(actions, bg=self.palette["panel"])
        secondary_buttons.pack(fill="x", padx=18, pady=(0, 12))

        self.button(
            secondary_buttons,
            "📂 Open GameLoop Folder",
            self.open_gameloop_folder,
            width=22,
        ).pack(side="left", padx=(0, 10))

        self.button(
            secondary_buttons,
            "🔄 Restart GameLoop",
            self.restart_gameloop,
            width=20,
        ).pack(side="left", padx=(0, 10))

        self.button(
            secondary_buttons,
            "⛔ Close GameLoop",
            self.close_gameloop,
            danger=True,
            width=20,
        ).pack(side="left")

        tools_buttons = tk.Frame(actions, bg=self.palette["panel"])
        tools_buttons.pack(fill="x", padx=18, pady=(0, 12))

        self.button(
            tools_buttons,
            "🧰 Task Manager",
            self.open_task_manager,
            width=19,
        ).pack(side="left", padx=(0, 10))

        self.button(
            tools_buttons,
            "🎮 Windows Game Mode",
            self.open_game_mode_settings,
            width=22,
            variant="secondary",
        ).pack(side="left")

        tk.Label(
            actions,
            textvariable=self.boost_status_var,
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 6))

        ttk.Progressbar(
            actions,
            variable=self.boost_progress_var,
            maximum=100,
            style="HB.Horizontal.TProgressbar",
        ).pack(fill="x", padx=18, pady=(0, 18))

        self._refresh_state()

    def find_gameloop(self) -> str:
        custom = self.path_var.get().strip().strip('"')

        if custom and Path(custom).is_file():
            return custom

        for path in self.COMMON_GAMELOOP_PATHS:
            if Path(path).is_file():
                self.path_var.set(path)
                self.app.config_data["gameloop_path"] = path
                save_config(self.app.config_data)
                return path

        return ""

    def browse_gameloop(self) -> None:
        path = filedialog.askopenfilename(
            title="Select GameLoop executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
        )

        if path:
            self.path_var.set(path)
            self.app.config_data["gameloop_path"] = path
            save_config(self.app.config_data)
            self.app.log("GameLoop path saved")

    def _is_gameloop_running(self) -> bool:
        for process in psutil.process_iter(["name"]):
            try:
                if process.info["name"] in self.GAMELOOP_PROCESS_NAMES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def launch_gameloop(self) -> bool:
        if self._is_gameloop_running():
            self.app.log("GameLoop is already running")
            return True

        path = self.find_gameloop()
        if not path:
            self.after(0, lambda: messagebox.showwarning(
                "GameLoop not found",
                "Select the GameLoop executable using Browse.",
            ))
            return False

        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                path,
                None,
                str(Path(path).parent),
                1,
            )
            if result > 32:
                self.app.log("GameLoop launched as administrator")
                return True

            self.after(0, lambda: messagebox.showerror(
                "Launch failed",
                f"Windows launch error code: {result}",
            ))
        except Exception as error:
            self.after(0, lambda err=str(error): messagebox.showerror(
                "Launch failed", err
            ))
        return False

    def launch_and_boost(self) -> None:
        if self.boost_thread and self.boost_thread.is_alive():
            messagebox.showinfo("Launch & Boost", "Boost is already running.")
            return

        self.boost_progress_var.set(0)
        self.boost_status_var.set("Starting...")
        self.boost_button.configure(state="disabled", text="⏳ Boosting...")
        self.boost_thread = threading.Thread(
            target=self._boost_worker,
            daemon=True,
        )
        self.boost_thread.start()

    def _set_boost_state(self, progress: float, status: str) -> None:
        self.after(0, lambda: self.boost_progress_var.set(progress))
        self.after(0, lambda: self.boost_status_var.set(status))

        dashboard = self.app.pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "progress"):
            self.after(0, lambda: dashboard.progress.configure(value=progress))

        self.app.log(status)

    def _boost_worker(self) -> None:
        self.app.log("========== Launch & Boost ==========")

        self._set_boost_state(10, "Cleaning user TEMP...")
        removed, skipped = self._clean_user_temp()
        self.app.log(f"TEMP cleaned: {removed} removed, {skipped} skipped")

        self._set_boost_state(45, "Flushing DNS cache...")
        dns_ok = self._flush_dns_quiet()
        self.app.log("DNS cache flushed" if dns_ok else "DNS flush was not completed")

        self._set_boost_state(70, "Enabling High Performance...")
        power_ok = self._enable_high_performance()
        self.app.log(
            "High Performance enabled"
            if power_ok
            else "Power plan could not be changed"
        )

        self._set_boost_state(90, "Launching GameLoop...")
        launched = self.launch_gameloop()

        if launched:
            self._set_boost_state(100, "✔ Boost complete — GameLoop launched")
        else:
            self._set_boost_state(100, "Boost finished — GameLoop was not launched")

        self.after(0, lambda: self.boost_button.configure(
            state="normal", text="🚀 Launch & Boost"
        ))

    def _clean_user_temp(self) -> tuple[int, int]:
        removed = 0
        skipped = 0
        temp_dir = Path(tempfile.gettempdir())

        try:
            items = list(temp_dir.iterdir())
        except OSError:
            return 0, 1

        for item in items:
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                removed += 1
            except OSError:
                skipped += 1

        return removed, skipped

    def _flush_dns_quiet(self) -> bool:
        try:
            result = subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _enable_high_performance(self) -> bool:
        try:
            result = subprocess.run(
                ["powercfg", "/setactive", "SCHEME_MIN"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def open_task_manager(self) -> None:
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                "taskmgr.exe",
                None,
                None,
                1,
            )
            if result > 32:
                self.app.log("Task Manager opened")
            else:
                messagebox.showerror(
                    "Task Manager",
                    f"Windows launch error code: {result}",
                )
        except Exception as error:
            messagebox.showerror("Task Manager", str(error))

    def open_game_mode_settings(self) -> None:
        try:
            os.startfile("ms-settings:gaming-gamemode")
            self.app.log("Windows Game Mode settings opened")
        except (OSError, AttributeError) as error:
            messagebox.showerror("Game Mode", str(error))

    def open_gameloop_folder(self) -> None:
        path = self.find_gameloop()
        if not path:
            messagebox.showwarning(
                "GameLoop not found",
                "Select the GameLoop executable first.",
            )
            return

        subprocess.Popen(["explorer", str(Path(path).parent)])

    def _gameloop_processes(self) -> list[psutil.Process]:
        running: list[psutil.Process] = []
        for process in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                if process.info["name"] in self.GAMELOOP_PROCESS_NAMES:
                    running.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return running

    def close_gameloop(self, ask_confirmation: bool = True) -> bool:
        running = self._gameloop_processes()
        if not running:
            if ask_confirmation:
                messagebox.showinfo("GameLoop", "GameLoop is not running.")
            return True

        if ask_confirmation and not messagebox.askyesno(
            "Close GameLoop",
            "Close all detected GameLoop processes?",
        ):
            return False

        closed = 0
        for process in running:
            try:
                process.terminate()
                closed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        gone, alive = psutil.wait_procs(running, timeout=3)
        for process in alive:
            try:
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self.app.log(f"Closed {closed} GameLoop process(es)")
        return True

    def restart_gameloop(self) -> None:
        if not messagebox.askyesno(
            "Restart GameLoop",
            "Close GameLoop and start it again?",
        ):
            return

        self.boost_status_var.set("Restarting GameLoop...")
        self.close_gameloop(ask_confirmation=False)
        self.after(1200, self._finish_restart)

    def _finish_restart(self) -> None:
        launched = self.launch_gameloop()
        self.boost_status_var.set(
            "✅ GameLoop restarted" if launched else "❌ Restart failed"
        )

    def _refresh_state(self) -> None:
        if not self.winfo_exists():
            return

        processes = self._gameloop_processes()
        running = bool(processes)
        self.state_var.set("🟢 Running" if running else "🔴 Not running")

        if running:
            try:
                started = min(p.create_time() for p in processes)
                seconds = max(0, int(time.time() - started))
                hours, remainder = divmod(seconds, 3600)
                minutes, secs = divmod(remainder, 60)
                self.gameloop_uptime_var.set(
                    f"Uptime: {hours:02d}:{minutes:02d}:{secs:02d}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                self.gameloop_uptime_var.set("Uptime: --")
        else:
            self.gameloop_uptime_var.set("Uptime: --")

        self.after(1500, self._refresh_state)

    def optimize_ram(self) -> None:
        """Safely refresh Python memory and trim only this app's working set."""
        memory_before = psutil.virtual_memory()
        before = psutil.Process().memory_info().rss / (1024 ** 2)
        available_before = memory_before.available / (1024 ** 2)

        self.boost_status_var.set("🧠 Optimizing RAM...")
        self.app.log("RAM optimization started")

        gc.collect()

        try:
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(handle)
        except (AttributeError, OSError):
            pass

        memory_after = psutil.virtual_memory()
        after = psutil.Process().memory_info().rss / (1024 ** 2)
        available_after = memory_after.available / (1024 ** 2)
        reduced = max(0.0, before - after)
        gained = max(0.0, available_after - available_before)

        message = (
            f"✅ RAM {memory_before.percent:.1f}% → {memory_after.percent:.1f}% | "
            f"app reduced {reduced:.1f} MB | available +{gained:.1f} MB"
        )
        self.boost_status_var.set(message)
        self.app.log(message)

    def boost_now(self):

        self.app.log("========== ULTIMATE BOOST ==========")

        self.boost_status_var.set("🧹 Cleaning TEMP...")

        self.app.pages["Cleaner"].start_cleanup()

        self.boost_status_var.set("🌐 Flushing DNS...")

        subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True,
        )

        self.boost_status_var.set("⚡ High Performance...")

        subprocess.run(
            [
                "powercfg",
                "/setactive",
                "SCHEME_MIN",
            ],
            capture_output=True,
        )

        self.boost_status_var.set("🎮 Launching GameLoop...")

        self.launch_gameloop()

        self.boost_status_var.set("✅ Boost Complete")

        self.app.log("========== DONE ==========")


class PerformancePage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.monitor_job = None
        self.cpu_var = tk.StringVar(value="CPU: 0%")
        self.ram_var = tk.StringVar(value="RAM: 0%")
        self.disk_var = tk.StringVar(value="Disk: 0%")
        self.uptime_var = tk.StringVar(value="Uptime: --")

        self.page_header(
            "⚡ Performance",
            "Live resource monitoring.",
        )

        values = self.panel()
        values.pack(fill="x")

        for index, variable in enumerate(
            [self.cpu_var, self.ram_var, self.disk_var, self.uptime_var]
        ):
            card = self.panel(values)
            card.grid(row=0, column=index, sticky="nsew", padx=5, pady=5)
            values.grid_columnconfigure(index, weight=1)

            tk.Label(
                card,
                textvariable=variable,
                bg=self.palette["panel"],
                fg=self.palette["text"],
                font=("Segoe UI", 14, "bold"),
            ).pack(padx=14, pady=18)

        bars = self.panel()
        bars.pack(fill="x", pady=16)

        self.cpu_bar = self._bar_row(bars, "CPU")
        self.ram_bar = self._bar_row(bars, "RAM")
        self.disk_bar = self._bar_row(bars, "Disk C:")

        process_panel = self.panel()
        process_panel.pack(fill="both", expand=True)

        tk.Label(
            process_panel,
            text="Top memory processes",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        self.process_tree = ttk.Treeview(
            process_panel,
            columns=("name", "memory"),
            show="headings",
            style="HB.Treeview",
            height=10,
        )
        self.process_tree.heading("name", text="Process")
        self.process_tree.heading("memory", text="Memory (MB)")
        self.process_tree.column("name", width=420, anchor="w")
        self.process_tree.column("memory", width=150, anchor="center")
        self.process_tree.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _bar_row(self, parent: tk.Widget, title: str) -> ttk.Progressbar:
        row = tk.Frame(parent, bg=self.palette["panel"])
        row.pack(fill="x", padx=18, pady=10)

        tk.Label(
            row,
            text=title,
            width=10,
            anchor="w",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        bar = ttk.Progressbar(
            row,
            maximum=100,
            style="HB.Horizontal.TProgressbar",
        )
        bar.pack(side="left", fill="x", expand=True)

        return bar

    def start_monitoring(self) -> None:
        if self.monitor_job is None:
            self._update_monitor()

    def stop_monitoring(self) -> None:
        if self.monitor_job is not None:
            try:
                self.after_cancel(self.monitor_job)
            except tk.TclError:
                pass

            self.monitor_job = None

    def _update_monitor(self) -> None:
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        boot = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes = remainder // 60

        self.cpu_var.set(f"CPU: {cpu}%")
        self.ram_var.set(f"RAM: {memory.percent}%")
        self.disk_var.set(f"Disk: {disk.percent}%")
        self.uptime_var.set(
            f"Uptime: {uptime.days}d {hours}h {minutes}m"
        )

        self.cpu_bar["value"] = cpu
        self.ram_bar["value"] = memory.percent
        self.disk_bar["value"] = disk.percent

        self._refresh_processes()

        interval = int(self.app.config_data.get("auto_refresh_ms", 1000))
        interval = max(500, min(interval, 5000))
        self.monitor_job = self.after(interval, self._update_monitor)

    def _refresh_processes(self) -> None:
        processes = []

        for process in psutil.process_iter(["name", "memory_info"]):
            try:
                memory_mb = process.info["memory_info"].rss / (1024 ** 2)
                processes.append(
                    (
                        process.info["name"] or "Unknown",
                        round(memory_mb, 1),
                    )
                )

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda item: item[1], reverse=True)

        for item in self.process_tree.get_children():
            self.process_tree.delete(item)

        for name, memory in processes[:8]:
            self.process_tree.insert("", "end", values=(name, memory))





class ProcessManagerPage(BasePage):
    """A cautious process viewer with an opt-in terminate action."""

    PROTECTED_NAMES = {
        "system",
        "registry",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "winlogon.exe",
        "dwm.exe",
    }

    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.monitor_job = None
        self.search_var = tk.StringVar(value="")
        self.advisor_var = tk.StringVar(
            value="Smart Advisor: analyzing running programs..."
        )
        self.summary_var = tk.StringVar(value="0 processes")

        self.page_header(
            "📋 Process Manager",
            "See which programs use the most memory and close only what you choose.",
        )

        advisor = self.panel()
        advisor.pack(fill="x")

        tk.Label(
            advisor,
            textvariable=self.advisor_var,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=18, pady=16)

        toolbar = self.panel()
        toolbar.pack(fill="x", pady=16)

        tk.Label(
            toolbar,
            text="Search",
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(18, 8), pady=14)

        search = tk.Entry(
            toolbar,
            textvariable=self.search_var,
            bg=self.palette["entry"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            font=("Segoe UI", 10),
            width=28,
        )
        search.pack(side="left", ipady=7, pady=12)
        search.bind("<KeyRelease>", lambda _event: self.refresh_processes())

        self.button(
            toolbar,
            "🔄 Refresh",
            self.refresh_processes,
            width=14,
        ).pack(side="left", padx=10)

        self.button(
            toolbar,
            "📂 Open Location",
            self.open_selected_location,
            width=16,
        ).pack(side="left", padx=(0, 10))

        self.button(
            toolbar,
            "⛔ End Selected",
            self.end_selected_process,
            danger=True,
            width=16,
        ).pack(side="left")

        tk.Label(
            toolbar,
            textvariable=self.summary_var,
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 9),
        ).pack(side="right", padx=18)

        table_panel = self.panel()
        table_panel.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            table_panel,
            columns=("pid", "name", "cpu", "memory", "status"),
            show="headings",
            style="HB.Treeview",
            height=14,
        )
        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Process")
        self.tree.heading("cpu", text="CPU %")
        self.tree.heading("memory", text="Memory MB")
        self.tree.heading("status", text="Status")
        self.tree.column("pid", width=80, anchor="center")
        self.tree.column("name", width=300, anchor="w")
        self.tree.column("cpu", width=100, anchor="center")
        self.tree.column("memory", width=130, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=18, pady=18)

    def start_monitoring(self) -> None:
        if self.monitor_job is None:
            self.refresh_processes()

    def stop_monitoring(self) -> None:
        if self.monitor_job is not None:
            try:
                self.after_cancel(self.monitor_job)
            except tk.TclError:
                pass
            self.monitor_job = None

    def refresh_processes(self) -> None:
        if not self.winfo_exists():
            return

        query = self.search_var.get().strip().lower()
        rows = []

        for process in psutil.process_iter(
            ["pid", "name", "memory_info", "status", "exe"]
        ):
            try:
                name = process.info["name"] or "Unknown"
                if query and query not in name.lower():
                    continue

                memory_mb = process.info["memory_info"].rss / (1024 ** 2)
                cpu = process.cpu_percent(interval=None)
                rows.append(
                    (
                        process.info["pid"],
                        name,
                        round(cpu, 1),
                        round(memory_mb, 1),
                        process.info["status"] or "unknown",
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue

        rows.sort(key=lambda item: item[3], reverse=True)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in rows[:100]:
            self.tree.insert("", "end", values=row)

        self.summary_var.set(f"{len(rows)} matching process(es)")
        self._update_advisor(rows)

        if self.app.current_page == "Processes":
            self.monitor_job = self.after(2000, self.refresh_processes)
        else:
            self.monitor_job = None

    def _update_advisor(self, rows: list[tuple]) -> None:
        if not rows:
            self.advisor_var.set("Smart Advisor: no matching processes found.")
            return

        browsers_and_apps = {
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "discord.exe",
            "code.exe",
            "telegram.exe",
        }
        candidate = next(
            (row for row in rows if row[1].lower() in browsers_and_apps),
            None,
        )

        if candidate and candidate[3] >= 300:
            self.advisor_var.set(
                f"Smart Advisor: {candidate[1]} is using {candidate[3]:.1f} MB. "
                "Close it only if you are not using it and saved your work."
            )
        else:
            top = rows[0]
            self.advisor_var.set(
                f"Smart Advisor: highest memory use is {top[1]} at "
                f"{top[3]:.1f} MB. No automatic process closing is performed."
            )

    def _selected_pid(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Process Manager", "Select a process first.")
            return None

        values = self.tree.item(selected[0], "values")
        try:
            return int(values[0])
        except (TypeError, ValueError, IndexError):
            return None

    def end_selected_process(self) -> None:
        pid = self._selected_pid()
        if pid is None:
            return

        try:
            process = psutil.Process(pid)
            name = process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
            messagebox.showerror("Process Manager", str(error))
            return

        if name.lower() in self.PROTECTED_NAMES or pid in (0, 4):
            messagebox.showwarning(
                "Protected process",
                "HyperBoost will not close this Windows system process.",
            )
            return

        if not messagebox.askyesno(
            "End process",
            f"End {name} (PID {pid})?\n\nUnsaved work in that program may be lost.",
        ):
            return

        try:
            process.terminate()
            process.wait(timeout=3)
            self.app.log(f"Ended process {name} (PID {pid})")
        except psutil.TimeoutExpired:
            messagebox.showwarning(
                "Process Manager",
                "The process did not close in time. It was not force-killed.",
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
            messagebox.showerror("Process Manager", str(error))

        self.refresh_processes()

    def open_selected_location(self) -> None:
        pid = self._selected_pid()
        if pid is None:
            return

        try:
            path = psutil.Process(pid).exe()
            if not path:
                raise FileNotFoundError("Executable path is unavailable.")
            subprocess.Popen(["explorer", "/select,", path])
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as error:
            messagebox.showerror("Open location", str(error))


class CleanerPage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.cleanup_thread = None
        self.result_var = tk.StringVar(value="Ready to scan.")
        self.temp_summary_var = tk.StringVar(value="TEMP: Not scanned")
        self.last_action_var = tk.StringVar(value="Last action: None")
        self.progress_var = tk.DoubleVar(value=0)

        self.page_header(
            "🧹 Cleaner & Quick Tune-Up",
            "Free storage and refresh safe Windows caches.",
        )

        info_panel = self.panel()
        info_panel.pack(fill="x")

        tk.Label(
            info_panel,
            text=(
                "Safe tools only: user TEMP, DNS cache, and Recycle Bin. "
                "Files currently in use are skipped."
            ),
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
            wraplength=800,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(16, 10))

        summary_row = tk.Frame(info_panel, bg=self.palette["panel"])
        summary_row.pack(fill="x", padx=18, pady=(0, 16))

        for variable in (self.temp_summary_var, self.last_action_var):
            card = self.panel(summary_row)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(
                card,
                textvariable=variable,
                bg=self.palette["panel"],
                fg=self.palette["text"],
                font=("Segoe UI", 11, "bold"),
                anchor="w",
            ).pack(fill="x", padx=14, pady=14)

        action_panel = self.panel()
        action_panel.pack(fill="x", pady=16)

        tk.Label(
            action_panel,
            textvariable=self.result_var,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 10))

        self.progress = ttk.Progressbar(
            action_panel,
            variable=self.progress_var,
            maximum=100,
            style="HB.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", padx=18, pady=(0, 16))

        first_row = tk.Frame(action_panel, bg=self.palette["panel"])
        first_row.pack(fill="x", padx=18, pady=(0, 10))

        self.button(first_row, "🔍 Scan TEMP", self.scan_temp, width=18).pack(
            side="left", padx=(0, 10)
        )
        self.button(first_row, "🧹 Clean TEMP", self.start_cleanup, width=18).pack(
            side="left", padx=(0, 10)
        )
        self.button(first_row, "🌐 Flush DNS", self.flush_dns, width=18).pack(
            side="left", padx=(0, 10)
        )
        self.button(first_row, "🗑 Empty Recycle Bin", self.empty_recycle_bin, width=20).pack(
            side="left"
        )

        second_row = tk.Frame(action_panel, bg=self.palette["panel"])
        second_row.pack(fill="x", padx=18, pady=(0, 18))

        self.button(second_row, "⚡ Safe Tune-Up", self.start_safe_tuneup, width=22, variant="secondary").pack(
            side="left", padx=(0, 10)
        )
        self.button(second_row, "📂 Open TEMP Folder", self.open_temp_folder, width=22).pack(
            side="left"
        )

        details = self.panel()
        details.pack(fill="both", expand=True)
        tk.Label(
            details,
            text="What Safe Tune-Up does",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Label(
            details,
            text=(
                "• Removes removable files from your user TEMP folder\n"
                "• Refreshes the Windows DNS cache\n"
                "• Skips locked files and does not alter game files\n"
                "• May free storage; it does not promise artificial FPS gains"
            ),
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 18))

    def _temp_items(self) -> list[Path]:
        temp_dir = Path(tempfile.gettempdir())
        try:
            return list(temp_dir.iterdir())
        except OSError:
            return []

    def _scan_temp_stats(self) -> tuple[int, int, int]:
        files = 0
        folders = 0
        total_size = 0

        for item in self._temp_items():
            try:
                if item.is_file() or item.is_symlink():
                    files += 1
                    try:
                        total_size += item.stat().st_size
                    except OSError:
                        pass
                elif item.is_dir():
                    folders += 1
                    for child in item.rglob("*"):
                        try:
                            if child.is_file():
                                total_size += child.stat().st_size
                        except OSError:
                            continue
            except OSError:
                continue

        return files, folders, total_size

    def scan_temp(self) -> None:
        self.result_var.set("Scanning TEMP...")
        self.progress_var.set(20)
        files, folders, total_size = self._scan_temp_stats()
        size_mb = total_size / (1024 ** 2)
        self.progress_var.set(100)
        self.temp_summary_var.set(
            f"TEMP: {files} files, {folders} folders, about {size_mb:.1f} MB"
        )
        self.result_var.set("TEMP scan completed.")
        self.last_action_var.set(f"Last action: Scan at {datetime.now():%H:%M:%S}")
        self.app.log("TEMP scan completed")

    def start_cleanup(self) -> None:
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            messagebox.showinfo("Cleaner", "A cleaner task is already running.")
            return

        if self.app.config_data.get("confirm_cleanup", True):
            if not messagebox.askyesno(
                "Clean TEMP",
                "Delete removable files from your TEMP folder?",
            ):
                return

        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker,
            daemon=True,
        )
        self.cleanup_thread.start()

    def _cleanup_worker(self) -> None:
        items = self._temp_items()
        total = max(len(items), 1)
        removed = 0
        skipped = 0
        freed = 0

        self.after(0, lambda: self.result_var.set("Cleaning temporary files..."))
        self.after(0, lambda: self.progress_var.set(0))

        for index, item in enumerate(items, start=1):
            try:
                if item.is_file() or item.is_symlink():
                    try:
                        freed += item.stat().st_size
                    except OSError:
                        pass
                    item.unlink()
                    removed += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    removed += 1
            except OSError:
                skipped += 1

            progress = (index / total) * 100
            self.after(0, lambda value=progress: self.progress_var.set(value))

        freed_mb = freed / (1024 ** 2)
        message = (
            f"Removed {removed} item(s), skipped {skipped}, "
            f"freed at least {freed_mb:.1f} MB."
        )
        self.after(0, lambda: self.result_var.set(message))
        self.after(0, lambda: self.temp_summary_var.set("TEMP: Cleaned — scan again for details"))
        self.after(0, lambda: self.last_action_var.set(
            f"Last action: TEMP cleaned at {datetime.now():%H:%M:%S}"
        ))
        self.app.log(message)

    def flush_dns(self) -> None:
        self.result_var.set("Flushing DNS cache...")
        self.progress_var.set(35)
        try:
            result = subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                self.progress_var.set(100)
                self.result_var.set("DNS cache flushed successfully.")
                self.last_action_var.set(
                    f"Last action: DNS refreshed at {datetime.now():%H:%M:%S}"
                )
                self.app.log("DNS cache flushed")
            else:
                self.progress_var.set(0)
                self.result_var.set("DNS flush failed.")
                messagebox.showerror(
                    "DNS flush failed",
                    result.stderr or result.stdout or "Unknown error",
                )
        except (OSError, subprocess.SubprocessError) as error:
            self.progress_var.set(0)
            messagebox.showerror("DNS flush failed", str(error))

    def empty_recycle_bin(self) -> None:
        if not messagebox.askyesno(
            "Empty Recycle Bin",
            "Permanently remove all items currently in the Recycle Bin?",
        ):
            return

        try:
            flags = 0x00000001 | 0x00000002 | 0x00000004
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            if result == 0:
                self.progress_var.set(100)
                self.result_var.set("Recycle Bin emptied successfully.")
                self.last_action_var.set(
                    f"Last action: Recycle Bin emptied at {datetime.now():%H:%M:%S}"
                )
                self.app.log("Recycle Bin emptied")
            else:
                messagebox.showerror(
                    "Recycle Bin",
                    f"Windows returned error code: {result}",
                )
        except (AttributeError, OSError) as error:
            messagebox.showerror("Recycle Bin", str(error))

    def open_temp_folder(self) -> None:
        try:
            subprocess.Popen(["explorer", tempfile.gettempdir()])
            self.app.log("TEMP folder opened")
        except OSError as error:
            messagebox.showerror("Open TEMP", str(error))

    def start_safe_tuneup(self) -> None:
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            messagebox.showinfo("Safe Tune-Up", "A cleaner task is already running.")
            return

        self.cleanup_thread = threading.Thread(
            target=self._safe_tuneup_worker,
            daemon=True,
        )
        self.cleanup_thread.start()

    def _safe_tuneup_worker(self) -> None:
        self.after(0, lambda: self.result_var.set("Safe Tune-Up: cleaning TEMP..."))
        self.after(0, lambda: self.progress_var.set(10))

        items = self._temp_items()
        total = max(len(items), 1)
        removed = 0
        skipped = 0
        freed = 0

        for index, item in enumerate(items, start=1):
            try:
                if item.is_file() or item.is_symlink():
                    try:
                        freed += item.stat().st_size
                    except OSError:
                        pass
                    item.unlink()
                    removed += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    removed += 1
            except OSError:
                skipped += 1

            progress = 10 + ((index / total) * 65)
            self.after(0, lambda value=progress: self.progress_var.set(value))

        self.after(0, lambda: self.result_var.set("Safe Tune-Up: refreshing DNS..."))
        self.after(0, lambda: self.progress_var.set(85))
        dns_ok = False
        try:
            result = subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            dns_ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass

        freed_mb = freed / (1024 ** 2)
        final = (
            f"Tune-Up complete: {removed} removed, {skipped} skipped, "
            f"at least {freed_mb:.1f} MB freed; "
            f"DNS {'refreshed' if dns_ok else 'not refreshed'}."
        )
        self.after(0, lambda: self.progress_var.set(100))
        self.after(0, lambda: self.result_var.set(final))
        self.after(0, lambda: self.temp_summary_var.set("TEMP: Cleaned — scan again for details"))
        self.after(0, lambda: self.last_action_var.set(
            f"Last action: Safe Tune-Up at {datetime.now():%H:%M:%S}"
        ))
        self.app.log(final)


class SystemPage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.page_header(
            "💻 System Information",
            "Hardware and Windows details.",
        )

        panel = self.panel()
        panel.pack(fill="both", expand=True)

        self.info_box = tk.Text(
            panel,
            bg=self.palette["entry"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            bd=0,
            font=("Consolas", 10),
            wrap="word",
        )
        self.info_box.pack(fill="both", expand=True, padx=18, pady=18)

        buttons = tk.Frame(self, bg=self.palette["window"])
        buttons.pack(fill="x", pady=(14, 0))

        self.button(
            buttons,
            "🔄 Refresh",
            self.refresh_info,
            width=16,
        ).pack(side="left", padx=(0, 10))

        self.button(
            buttons,
            "📄 Export Report",
            self.export_report,
            width=16,
        ).pack(side="left")

        self.refresh_info()

    def system_report(self) -> str:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        boot = datetime.fromtimestamp(psutil.boot_time())

        lines = [
            f"{APP_NAME} System Report",
            "=" * 58,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            f"Computer name: {platform.node()}",
            f"User: {safe_username()}",
            f"Hostname: {socket.gethostname()}",
            "",
            f"Operating system: {platform.system()} {platform.release()}",
            f"Windows version: {platform.version()}",
            f"Architecture: {platform.machine()}",
            "",
            f"Processor: {platform.processor() or 'Unknown'}",
            f"Physical cores: {psutil.cpu_count(logical=False)}",
            f"Logical processors: {psutil.cpu_count(logical=True)}",
            "",
            f"Installed RAM: {bytes_to_gb(memory.total)} GB",
            f"Available RAM: {bytes_to_gb(memory.available)} GB",
            f"RAM usage: {memory.percent}%",
            "",
            f"Disk C total: {bytes_to_gb(disk.total)} GB",
            f"Disk C used: {bytes_to_gb(disk.used)} GB",
            f"Disk C free: {bytes_to_gb(disk.free)} GB",
            f"Disk C usage: {disk.percent}%",
            "",
            f"Last boot: {boot:%Y-%m-%d %H:%M:%S}",
            f"Python: {platform.python_version()}",
        ]

        return "\n".join(lines)

    def refresh_info(self) -> None:
        report = self.system_report()

        self.info_box.configure(state="normal")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", report)
        self.info_box.configure(state="disabled")

        self.app.log("System information refreshed")

    def export_report(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export system report",
            defaultextension=".txt",
            initialfile="HyperBoost_System_Report.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        if not path:
            return

        try:
            Path(path).write_text(self.system_report(), encoding="utf-8")
            self.app.log("System report exported")
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")

        except OSError as error:
            messagebox.showerror("Export failed", str(error))


class SettingsPage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.theme_var = tk.StringVar(value=app.config_data["theme"])
        self.refresh_var = tk.StringVar(
            value=str(app.config_data["auto_refresh_ms"])
        )
        self.start_page_var = tk.StringVar(
            value=app.config_data.get("start_page", "Dashboard")
        )
        self.confirm_var = tk.BooleanVar(
            value=bool(app.config_data["confirm_cleanup"])
        )
        self.confirm_close_var = tk.BooleanVar(
            value=bool(app.config_data.get("confirm_close_gameloop", True))
        )
        self.clock_seconds_var = tk.BooleanVar(
            value=bool(app.config_data.get("show_clock_seconds", True))
        )
        self.compact_sidebar_var = tk.BooleanVar(
            value=bool(app.config_data.get("compact_sidebar", False))
        )

        self.page_header(
            "⚙ Settings",
            "Customize appearance, startup, and safety options.",
        )

        columns = tk.Frame(self, bg=self.palette["window"])
        columns.pack(fill="both", expand=True)
        columns.grid_columnconfigure(0, weight=1)
        columns.grid_columnconfigure(1, weight=1)

        appearance = self.panel(columns)
        appearance.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))

        behavior = self.panel(columns)
        behavior.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        self._section_title(appearance, "🎨 Appearance")
        self._setting_label(appearance, "Theme")

        theme_row = tk.Frame(appearance, bg=self.palette["panel"])
        theme_row.pack(fill="x", padx=18, pady=(0, 12))

        for value, text in (("dark", "Dark"), ("light", "Light")):
            tk.Radiobutton(
                theme_row,
                text=text,
                variable=self.theme_var,
                value=value,
                bg=self.palette["panel"],
                fg=self.palette["text"],
                selectcolor=self.palette["entry"],
                activebackground=self.palette["panel"],
                activeforeground=self.palette["text"],
                font=("Segoe UI", 10),
            ).pack(side="left", padx=(0, 18))

        self._check(
            appearance,
            "Compact sidebar",
            self.compact_sidebar_var,
        )
        self._check(
            appearance,
            "Show seconds in the clock",
            self.clock_seconds_var,
        )

        self._section_title(behavior, "⚙ Behavior")
        self._setting_label(behavior, "Start page")

        ttk.Combobox(
            behavior,
            textvariable=self.start_page_var,
            values=(
                "Dashboard",
                "Gaming",
                "Performance",
                "Processes",
                "Cleaner",
                "System",
                "Settings",
            ),
            state="readonly",
            width=22,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self._setting_label(behavior, "Performance refresh interval")

        ttk.Combobox(
            behavior,
            textvariable=self.refresh_var,
            values=("500", "1000", "1500", "2000", "3000", "5000"),
            state="readonly",
            width=22,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self._check(
            behavior,
            "Ask before cleaning TEMP",
            self.confirm_var,
        )
        self._check(
            behavior,
            "Ask before closing GameLoop",
            self.confirm_close_var,
        )

        actions = self.panel()
        actions.pack(fill="x")

        tk.Label(
            actions,
            text="Changes to theme and sidebar size reload the interface automatically.",
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        button_row = tk.Frame(actions, bg=self.palette["panel"])
        button_row.pack(fill="x", padx=18, pady=(0, 18))

        self.button(
            button_row,
            "💾 Save Settings",
            self.save,
            width=18,
            variant="success",
        ).pack(side="left", padx=(0, 10))

        self.button(
            button_row,
            "↩ Reset Defaults",
            self.reset_defaults,
            width=18,
            danger=True,
        ).pack(side="left")

    def _section_title(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))

    def _setting_label(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=18, pady=(12, 6))

    def _check(
        self,
        parent: tk.Widget,
        text: str,
        variable: tk.BooleanVar,
    ) -> None:
        tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            selectcolor=self.palette["entry"],
            activebackground=self.palette["panel"],
            activeforeground=self.palette["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=6)

    def save(self) -> None:
        try:
            refresh = int(self.refresh_var.get())
        except ValueError:
            refresh = 1000

        old_theme = self.app.config_data.get("theme", "dark")
        old_compact = bool(self.app.config_data.get("compact_sidebar", False))

        self.app.config_data.update(
            {
                "theme": self.theme_var.get(),
                "auto_refresh_ms": refresh,
                "start_page": self.start_page_var.get(),
                "confirm_cleanup": self.confirm_var.get(),
                "confirm_close_gameloop": self.confirm_close_var.get(),
                "show_clock_seconds": self.clock_seconds_var.get(),
                "compact_sidebar": self.compact_sidebar_var.get(),
            }
        )

        save_config(self.app.config_data)
        self.app.log("Settings saved")

        needs_reload = (
            self.theme_var.get() != old_theme
            or self.compact_sidebar_var.get() != old_compact
        )

        if needs_reload:
            self.app.status_var.set("Applying settings...")
            self.app.after(150, self.app.request_restart)
        else:
            messagebox.showinfo("Settings", "Settings saved successfully.")

    def reset_defaults(self) -> None:
        if not messagebox.askyesno(
            "Reset settings",
            "Restore all settings to their default values?",
        ):
            return

        self.theme_var.set(DEFAULT_CONFIG["theme"])
        self.refresh_var.set(str(DEFAULT_CONFIG["auto_refresh_ms"]))
        self.start_page_var.set(DEFAULT_CONFIG["start_page"])
        self.confirm_var.set(DEFAULT_CONFIG["confirm_cleanup"])
        self.confirm_close_var.set(DEFAULT_CONFIG["confirm_close_gameloop"])
        self.clock_seconds_var.set(DEFAULT_CONFIG["show_clock_seconds"])
        self.compact_sidebar_var.set(DEFAULT_CONFIG["compact_sidebar"])
        self.save()


class AboutPage(BasePage):
    def __init__(self, master: tk.Widget, app: HyperBoostApp) -> None:
        super().__init__(master, app)

        self.page_header(
            "ℹ About",
            "Information about this project.",
        )

        panel = self.panel()
        panel.pack(fill="both", expand=True)

        tk.Label(
            panel,
            text="⚡ HYPERBOOST X PRO",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 28, "bold"),
        ).pack(pady=(45, 8))

        tk.Label(
            panel,
            text=f"VERSION {APP_VERSION}  •  FINAL",
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=("Segoe UI", 11),
        ).pack()

        description = (
            "A safe Windows gaming dashboard built with Python and Tkinter.\n\n"
            "Features include live system monitoring, GameLoop launching,\n"
            "temporary-file cleanup, DNS flushing, system reports, and themes.\n\n"
            "This app does not alter game files, bypass anti-cheat systems,\n"
            "or promise fake FPS gains."
        )

        tk.Label(
            panel,
            text=description,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI", 12),
            justify="center",
        ).pack(pady=28)

        tk.Label(
            panel,
            text="DESIGNED & BUILT BY BODYY",
            bg=self.palette["panel"],
            fg=self.palette["accent"],
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=10)


def main() -> None:
    while True:
        app = HyperBoostApp()
        app.mainloop()

        if not app.restart_requested:
            break


if __name__ == "__main__":
    main()