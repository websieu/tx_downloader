"""
BINMUN Profile Manager GUI - PyQt6
SQLite backend, sidebar + table layout.
"""

import json
import os
import sys
import shutil
import sqlite3
import subprocess
import threading
import uuid
import base64
import random
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QScrollArea, QFrame,
    QMessageBox, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from gpm_profile_launcher import (
    parse_proxy, get_ip_info, build_gpm_fg,
)

# === DEFAULTS ===
if getattr(sys, 'frozen', False):
    # PyInstaller
    APP_DIR = os.path.dirname(sys.executable)
elif sys.argv and not os.path.basename(sys.argv[0]).lower().startswith('python'):
    # Nuitka onefile: sys.argv[0] = original exe path
    APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Debug log to check paths at startup
_log_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "startup_debug.log")
try:
    with open(_log_path, "w", encoding="utf-8") as _f:
        _f.write(f"sys.executable = {sys.executable}\n")
        _f.write(f"sys.argv[0]    = {sys.argv[0]}\n")
        _f.write(f"__file__       = {__file__}\n")
        _f.write(f"APP_DIR        = {APP_DIR}\n")
        _icon = os.path.join(APP_DIR, "assets", "binmun_logo.png")
        _f.write(f"icon_path      = {_icon}\n")
        _f.write(f"icon_exists    = {os.path.exists(_icon)}\n")
except Exception:
    pass

DEFAULT_PROFILE_DIR = os.path.join(os.path.expanduser("~"), "gpm_profiles")
SETTINGS_FILE = os.path.join(APP_DIR, "gpm_manager_settings.json")
DB_PATH = os.path.join(APP_DIR, "gpm_profiles.db")

_CHROME_LOCAL = os.path.join(APP_DIR, "GPMLoginData", "Browsers", "ChromiumCore_v144", "chrome.exe")
_CHROME_APPDATA = os.path.join(
    os.environ.get("APPDATA", ""),
    "GPMLoginGlobal", "Browsers", "ChromiumCore_v144", "chrome.exe"
)
CHROME_PATH = _CHROME_LOCAL if os.path.exists(_CHROME_LOCAL) else _CHROME_APPDATA
PAGE_SIZE = 10

# Colors
C_SIDEBAR = "#0f1923"
C_BG = "#131c27"
C_CARD = "#182533"
C_HEADER = "#1a2a3a"
C_ACCENT = "#00b894"
C_RED = "#e74c3c"
C_YELLOW = "#f39c12"
C_GREEN = "#00b894"
C_DIM = "#7f8c9b"
C_BORDER = "#243447"
C_ROW_HOVER = "#1e3044"


# === SQLite ===

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            proxy TEXT DEFAULT '',
            note TEXT DEFAULT '',
            automation INTEGER DEFAULT 0,
            status TEXT DEFAULT 'stopped',
            ip TEXT DEFAULT '',
            location TEXT DEFAULT '',
            timezone TEXT DEFAULT '',
            gpu TEXT DEFAULT '',
            cores INTEGER DEFAULT 0,
            memory INTEGER DEFAULT 0,
            cdp_port INTEGER DEFAULT 0,
            pid INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            last_run TEXT DEFAULT ''
        )
    """)
    for col, default in [("created_at", "''"), ("last_run", "''")]:
        try:
            conn.execute(f"ALTER TABLE profiles ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass
    conn.commit()

    json_db = os.path.join(APP_DIR, "gpm_profiles_db.json")
    if os.path.exists(json_db):
        try:
            with open(json_db, "r", encoding="utf-8") as f:
                old = json.load(f)
            for p in old.get("profiles", []):
                conn.execute(
                    "INSERT OR IGNORE INTO profiles (id,name,proxy,note,automation,ip,location,timezone,gpu,cores,memory) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p.get("name", ""), p.get("proxy", ""), p.get("note", ""),
                     int(p.get("automation", False)),
                     p.get("ip", ""), p.get("location", ""), p.get("timezone", ""),
                     p.get("gpu", ""), p.get("cores", 0), p.get("memory", 0)))
            conn.commit()
            os.rename(json_db, json_db + ".migrated")
        except Exception:
            pass
    count = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    if count == 0:
        _scan_existing_profiles(conn)
    return conn


def _scan_existing_profiles(conn):
    settings = load_settings()
    profile_dir = settings.get("profile_dir", DEFAULT_PROFILE_DIR)
    if not os.path.isdir(profile_dir):
        return

    import re
    uuid_re = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    imported = 0

    for name in os.listdir(profile_dir):
        if not uuid_re.match(name):
            continue
        fg_path = os.path.join(profile_dir, name, "Default", "GPMSoft", "gpm_fg.dat")
        if not os.path.isfile(fg_path):
            continue
        try:
            with open(fg_path, "r") as f:
                raw = f.read()
            data = json.loads(base64.b64decode(raw).decode("utf-8"))
            gpm = data.get("gpm", {})
            profile_name = gpm.get("name", f"Profile_{name[:8]}")
            webrtc = gpm.get("webRTC", {})
            geo = gpm.get("geo_location", {})
            ip = webrtc.get("publicIP", "")
            tz = gpm.get("timezone", "")
            lat = geo.get("latitude", 0)
            lon = geo.get("longitude", 0)
            location = f"({tz.split('/')[-1] if tz else 'Unknown'})" if lat and lon else ""
            webgl = gpm.get("webgl", {})
            param = webgl.get("parameter", {})
            gpu = param.get("UNMASKED_RENDERER_WEBGL", "")
            nav = gpm.get("navigator", {})
            conn.execute(
                "INSERT OR IGNORE INTO profiles "
                "(id, name, proxy, ip, location, timezone, gpu, cores, memory, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'stopped')",
                (name, profile_name, "", ip, location, tz, gpu,
                 nav.get("processorCount", 0), nav.get("deviceMemory", 0))
            )
            imported += 1
        except Exception:
            continue

    if imported:
        conn.commit()
        print(f"[Auto-scan] Imported {imported} existing profiles from {profile_dir}")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"profile_dir": DEFAULT_PROFILE_DIR}


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def find_font_source(profile_dir):
    if not os.path.isdir(profile_dir):
        return None
    for d in os.listdir(profile_dir):
        fp = os.path.join(profile_dir, d, "Default", "GPMSoft", "Fonts")
        if os.path.isdir(fp) and os.listdir(fp):
            return fp
    return None


def check_proxy(proxy_str):
    try:
        geo = get_ip_info(proxy_str)
        if geo and geo.get("ip") and geo["ip"] != "127.0.0.1":
            return geo
    except Exception:
        pass
    return None


_SW_FLAGS = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000


def is_pid_alive(pid):
    if not pid:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True, timeout=5,
                           creationflags=_SW_FLAGS)
        return str(pid) in r.stdout
    except Exception:
        return False


def kill_pid_tree(pid):
    if not pid:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=10,
                       creationflags=_SW_FLAGS)
    except Exception:
        pass


def write_profile_files(profile_path, config):
    gpm = os.path.join(profile_path, "Default", "GPMSoft")
    fp = os.path.join(gpm, "Fonts")
    os.makedirs(fp, exist_ok=True)
    os.makedirs(os.path.join(gpm, "Exporter"), exist_ok=True)

    fs = find_font_source(os.path.dirname(profile_path))
    if fs:
        for f in os.listdir(fs):
            s = os.path.join(fs, f)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(fp, f))

    b64 = base64.b64encode(json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    with open(os.path.join(gpm, "gpm_fg.dat"), "w") as f:
        f.write(b64)
    with open(os.path.join(gpm, "extension_dependencies.json"), "w") as f:
        f.write("[ ] ")
    with open(os.path.join(profile_path, "Local State"), "w") as f:
        f.write("{}")
    with open(os.path.join(profile_path, "First Run"), "w") as f:
        f.write("")


# ============================================================
# Helpers
# ============================================================

def _trunc(text, max_len):
    if not text:
        return "--"
    return text if len(text) <= max_len else text[:max_len - 2] + ".."


def _btn_style(bg, hover=None, radius=6, size=None):
    h = hover or bg
    s = f"QPushButton {{ background: {bg}; border-radius: {radius}px; color: white; border: none; }}"
    s += f" QPushButton:hover {{ background: {h}; }}"
    s += " QPushButton:disabled { opacity: 0.5; }"
    return s


# ============================================================
# ProfileDialog
# ============================================================

class ProfileDialog(QDialog):
    def __init__(self, parent, title="New Profile", data=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(500)
        self.setModal(True)
        self.result = None
        data = data or {}

        self.setStyleSheet(f"background: {C_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 15)
        layout.setSpacing(0)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 12px;")
        layout.addWidget(title_lbl)

        self.fields = {}
        for label, key, default, ph in [
            ("Name", "name", f"Profile_{random.randint(1000, 9999)}", "Profile name"),
            ("Proxy", "proxy", "", "user:pass@host:port or host:port:user:pass"),
            ("Note", "note", "", "Optional note"),
        ]:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {C_DIM}; font-size: 12px; margin-top: 8px; background: transparent;")
            layout.addWidget(lbl)
            entry = QLineEdit(data.get(key, default))
            entry.setPlaceholderText(ph)
            entry.setFixedHeight(36)
            entry.setStyleSheet(f"""
                QLineEdit {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                             border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
                QLineEdit:focus {{ border-color: {C_ACCENT}; }}
            """)
            layout.addWidget(entry)
            self.fields[key] = entry

        self.auto_cb = QCheckBox("Enable Automation (CDP)")
        self.auto_cb.setChecked(data.get("automation", False))
        self.auto_cb.setStyleSheet(f"""
            QCheckBox {{ color: white; margin-top: 12px; background: transparent; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {C_BORDER}; border-radius: 3px; }}
            QCheckBox::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}
        """)
        layout.addWidget(self.auto_cb)

        btn_frame = QWidget()
        btn_frame.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 15, 0, 0)
        btn_layout.setSpacing(10)

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(140, 38)
        save_btn.setStyleSheet(_btn_style(C_ACCENT, "#00a884") + " QPushButton { font-size: 14px; font-weight: bold; }")
        save_btn.clicked.connect(self._ok)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(140, 38)
        cancel_btn.setStyleSheet(_btn_style(C_CARD, C_BORDER) + " QPushButton { font-size: 14px; }")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addWidget(btn_frame)

    def _ok(self):
        name = self.fields["name"].text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Name is required.")
            return
        self.result = {
            "name": name,
            "proxy": self.fields["proxy"].text().strip(),
            "note": self.fields["note"].text().strip(),
            "automation": self.auto_cb.isChecked(),
        }
        self.accept()


# ============================================================
# ProfileRow
# ============================================================

class ProfileRow(QFrame):
    def __init__(self, row_data, on_start, on_stop, on_edit, on_delete):
        super().__init__()
        self.profile_id = row_data["id"]
        status = row_data["status"] or "stopped"

        self.setFixedHeight(52)
        self.setObjectName("ProfileRow")
        self._base_style = f"""
            QFrame#ProfileRow {{ background: transparent; border-bottom: 1px solid {C_BORDER}; }}
        """
        self._hover_style = f"""
            QFrame#ProfileRow {{ background: {C_ROW_HOVER}; border-bottom: 1px solid {C_BORDER}; }}
        """
        self.setStyleSheet(self._base_style)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 6, 12, 6)
        layout.setSpacing(5)

        # Col 0: Name + ID (180px)
        name_widget = QWidget()
        name_widget.setFixedWidth(180)
        name_widget.setStyleSheet("background: transparent;")
        nw_layout = QVBoxLayout(name_widget)
        nw_layout.setContentsMargins(0, 0, 0, 0)
        nw_layout.setSpacing(0)

        name_lbl = QLabel(_trunc(row_data["name"], 20))
        name_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent;")
        id_lbl = QLabel(row_data["id"][:13])
        id_lbl.setStyleSheet("color: #3d4f5f; font-size: 8px; background: transparent;")
        nw_layout.addWidget(name_lbl)
        nw_layout.addWidget(id_lbl)
        layout.addWidget(name_widget)

        # Col 1: Status badge (85px)
        badge_bg, badge_txt = {
            "running": (C_GREEN, "RUNNING"),
            "starting": (C_YELLOW, "STARTING"),
        }.get(status, ("#4b5563", "STOPPED"))
        badge = QLabel(badge_txt)
        badge.setFixedSize(85, 22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {badge_bg}; border-radius: 10px; color: white; "
            f"font-size: 9px; font-weight: bold;"
        )
        layout.addWidget(badge)

        # Col 2: IP + Proxy (170px)
        ip_widget = QWidget()
        ip_widget.setFixedWidth(170)
        ip_widget.setStyleSheet("background: transparent;")
        ip_layout = QVBoxLayout(ip_widget)
        ip_layout.setContentsMargins(0, 0, 0, 0)
        ip_layout.setSpacing(0)

        ip_lbl = QLabel(_trunc(row_data["ip"], 18))
        ip_lbl.setStyleSheet("color: white; font-size: 12px; background: transparent;")
        proxy = row_data["proxy"]
        if proxy:
            h, p, u, _ = parse_proxy(proxy)
            ptxt = _trunc(f"{h}:{p}", 22)
        else:
            ptxt = "Direct"
        proxy_lbl = QLabel(ptxt)
        proxy_lbl.setStyleSheet("color: #3d4f5f; font-size: 9px; background: transparent;")
        ip_layout.addWidget(ip_lbl)
        ip_layout.addWidget(proxy_lbl)
        layout.addWidget(ip_widget)

        # Col 3: Location (130px)
        loc_lbl = QLabel(_trunc(row_data["location"], 18))
        loc_lbl.setFixedWidth(130)
        loc_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        layout.addWidget(loc_lbl)

        # Col 4: Note (80px)
        note_lbl = QLabel(_trunc(row_data["note"], 12) if row_data["note"] else "")
        note_lbl.setFixedWidth(80)
        note_lbl.setStyleSheet("color: #3d4f5f; font-size: 10px; background: transparent;")
        layout.addWidget(note_lbl)

        # Col 5: Actions
        layout.addStretch()

        act_widget = QWidget()
        act_widget.setStyleSheet("background: transparent;")
        act_layout = QHBoxLayout(act_widget)
        act_layout.setContentsMargins(0, 0, 0, 0)
        act_layout.setSpacing(3)

        pid = self.profile_id
        if status == "running":
            ss_btn = QPushButton("Stop")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_RED, "#c0392b", 5) + " QPushButton { font-weight: bold; font-size: 11px; }")
            ss_btn.clicked.connect(lambda: on_stop(pid))
        elif status == "starting":
            ss_btn = QPushButton("...")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_YELLOW, C_YELLOW, 5) + " QPushButton { font-size: 11px; }")
            ss_btn.setEnabled(False)
        else:
            ss_btn = QPushButton("Start")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_GREEN, "#00a884", 5) + " QPushButton { font-weight: bold; font-size: 11px; }")
            ss_btn.clicked.connect(lambda: on_start(pid))

        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(30, 28)
        edit_btn.setStyleSheet(_btn_style(C_CARD, C_BORDER, 5) + " QPushButton { font-size: 13px; }")
        edit_btn.clicked.connect(lambda: on_edit(pid))

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 28)
        del_btn.setStyleSheet(_btn_style(C_CARD, C_RED, 5) + " QPushButton { font-size: 13px; }")
        del_btn.clicked.connect(lambda: on_delete(pid))

        act_layout.addWidget(ss_btn)
        act_layout.addWidget(edit_btn)
        act_layout.addWidget(del_btn)
        layout.addWidget(act_widget)

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, event):
        self.setStyleSheet(self._base_style)


# ============================================================
# App
# ============================================================

class App(QMainWindow):
    sig_render_one = pyqtSignal(str)
    sig_status     = pyqtSignal(str)
    sig_render     = pyqtSignal()
    sig_error      = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BINMUN Profile Manager")
        _icon_path = os.path.join(APP_DIR, "assets", "binmun_logo.png")
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.resize(1150, 700)
        self.setMinimumSize(1000, 550)

        self.settings = load_settings()
        self.conn = get_db()
        self.page = 0
        self.search_text = ""
        self._row_widgets = []
        self._filter = "all"

        self._build_ui()

        # Connect signals (after UI built)
        self.sig_render_one.connect(self._render_one)
        self.sig_status.connect(self.status_lbl.setText)
        self.sig_render.connect(self._render)
        self.sig_error.connect(lambda t, m: QMessageBox.critical(self, t, m))

        self._sync_running_status()
        self._render()
        self._start_watchdog()

    def _tab_style(self, active):
        if active:
            return f"QPushButton {{ background: {C_ACCENT}; border-radius: 4px; color: white; font-size: 11px; font-weight: bold; border: none; }}"
        return f"QPushButton {{ background: transparent; border-radius: 4px; color: white; font-size: 11px; font-weight: bold; border: none; }} QPushButton:hover {{ background: {C_CARD}; }}"

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === Sidebar ===
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background: {C_SIDEBAR};")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(15, 20, 15, 20)
        sb_layout.setSpacing(2)

        logo = QLabel("BINMUN")
        logo.setStyleSheet(f"color: {C_ACCENT}; font-size: 18px; font-weight: bold; background: transparent;")
        sub = QLabel("Profile Manager")
        sub.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        sb_layout.addWidget(logo)
        sb_layout.addWidget(sub)
        sb_layout.addSpacing(10)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C_BORDER};")
        sb_layout.addWidget(sep)
        sb_layout.addSpacing(8)

        for text, active, cmd in [
            ("Profiles", True, None),
            ("Proxies", False, None),
            ("Settings", False, self._open_settings),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(36)
            if active:
                btn.setStyleSheet(f"QPushButton {{ background: {C_ACCENT}; border-radius: 6px; color: white; font-size: 13px; text-align: left; padding-left: 12px; border: none; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background: transparent; border-radius: 6px; color: {C_DIM}; font-size: 13px; text-align: left; padding-left: 12px; border: none; }} QPushButton:hover {{ background: {C_CARD}; color: white; }}")
            if cmd:
                btn.clicked.connect(cmd)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        create_btn = QPushButton("+ Create Profile")
        create_btn.setFixedHeight(40)
        create_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_ACCENT}; border-radius: 8px; color: white;
                           font-size: 13px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background: #00a884; }}
        """)
        create_btn.clicked.connect(self._add)
        sb_layout.addWidget(create_btn)

        main_layout.addWidget(sidebar)

        # === Content ===
        content = QWidget()
        content.setStyleSheet(f"background: {C_BG};")
        ct_layout = QVBoxLayout(content)
        ct_layout.setContentsMargins(0, 0, 0, 0)
        ct_layout.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(50)
        topbar.setStyleSheet(f"background: {C_SIDEBAR};")
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(15, 8, 15, 8)
        tb_layout.setSpacing(5)

        self.search_entry = QLineEdit()
        self.search_entry.setFixedSize(280, 34)
        self.search_entry.setPlaceholderText("Search profiles, proxies or IDs...")
        self.search_entry.setStyleSheet(f"""
            QLineEdit {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                         border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
            QLineEdit:focus {{ border-color: {C_ACCENT}; }}
        """)
        self.search_entry.textChanged.connect(self._do_search)
        tb_layout.addWidget(self.search_entry)
        tb_layout.addSpacing(15)

        self._tab_btns = {}
        for label, key in [("ALL", "all"), ("RUNNING", "running"), ("STOPPED", "stopped")]:
            btn = QPushButton(label)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet(self._tab_style(key == "all"))
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            tb_layout.addWidget(btn)
            self._tab_btns[key] = btn

        tb_layout.addStretch()
        ct_layout.addWidget(topbar)

        # Header
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background: {C_BG};")
        hd_layout = QHBoxLayout(header)
        hd_layout.setContentsMargins(20, 15, 20, 5)

        title_lbl = QLabel("Active Profiles")
        title_lbl.setStyleSheet("color: white; font-size: 22px; font-weight: bold; background: transparent;")
        hd_layout.addWidget(title_lbl)
        hd_layout.addStretch()

        self.count_lbl = QLabel("0 profiles")
        self.count_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 13px; background: transparent;")
        hd_layout.addWidget(self.count_lbl)
        ct_layout.addWidget(header)

        # Table header
        table_hdr = QWidget()
        table_hdr.setFixedHeight(38)
        table_hdr.setStyleSheet(f"background: {C_HEADER};")
        th_layout = QHBoxLayout(table_hdr)
        th_layout.setContentsMargins(15, 0, 15, 0)
        th_layout.setSpacing(5)

        for text, width in [
            ("PROFILE IDENTITY", 180), ("STATE", 85),
            ("IP / INFRASTRUCTURE", 170), ("LOCATION", 130), ("NOTE", 80),
        ]:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
            th_layout.addWidget(lbl)

        th_layout.addStretch()
        actions_hdr = QLabel("ACTIONS")
        actions_hdr.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
        th_layout.addWidget(actions_hdr)
        ct_layout.addWidget(table_hdr)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {C_BG}; }}
            QScrollBar:vertical {{ background: {C_BG}; width: 8px; border: none; }}
            QScrollBar::handle:vertical {{ background: {C_BORDER}; border-radius: 4px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.rows_widget = QWidget()
        self.rows_widget.setStyleSheet(f"background: {C_BG};")
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(20, 0, 20, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.addStretch()

        self.scroll_area.setWidget(self.rows_widget)
        ct_layout.addWidget(self.scroll_area, 1)

        # Bottom area
        bottom = QWidget()
        bottom.setStyleSheet(f"background: {C_SIDEBAR};")
        bot_layout = QVBoxLayout(bottom)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(1)

        # Pagination bar
        paging = QWidget()
        paging.setFixedHeight(44)
        paging.setStyleSheet(f"background: {C_SIDEBAR};")
        pg_layout = QHBoxLayout(paging)
        pg_layout.setContentsMargins(15, 6, 15, 6)
        pg_layout.setSpacing(5)

        self.page_info = QLabel("Showing 0 of 0 profiles")
        self.page_info.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        pg_layout.addWidget(self.page_info)
        pg_layout.addSpacing(15)

        self.btn_prev = QPushButton("❮")
        self.btn_prev.setFixedSize(30, 28)
        self.btn_prev.setStyleSheet(_btn_style(C_CARD, C_BORDER, 4))
        self.btn_prev.clicked.connect(self._prev)
        pg_layout.addWidget(self.btn_prev)

        self.page_lbl = QLabel("1")
        self.page_lbl.setFixedSize(30, 28)
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_lbl.setStyleSheet(f"background: {C_ACCENT}; border-radius: 4px; color: white; font-weight: bold; font-size: 11px;")
        pg_layout.addWidget(self.page_lbl)

        self.btn_next = QPushButton("❯")
        self.btn_next.setFixedSize(30, 28)
        self.btn_next.setStyleSheet(_btn_style(C_CARD, C_BORDER, 4))
        self.btn_next.clicked.connect(self._next)
        pg_layout.addWidget(self.btn_next)

        pg_layout.addStretch()

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        pg_layout.addWidget(self.status_lbl)

        bot_layout.addWidget(paging)

        # Stats bar
        stats_bar = QWidget()
        stats_bar.setFixedHeight(80)
        stats_bar.setStyleSheet(f"background: {C_SIDEBAR};")
        st_layout = QHBoxLayout(stats_bar)
        st_layout.setContentsMargins(20, 10, 20, 10)
        st_layout.setSpacing(5)

        def _stat_card(title, color):
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background: {C_CARD}; border-radius: 8px; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(15, 8, 15, 8)
            cl.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
            v = QLabel("0")
            v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold; background: transparent;")
            cl.addWidget(t)
            cl.addWidget(v)
            return card, v

        card_r, self.stat_running = _stat_card("RUNNING", C_GREEN)
        card_s, self.stat_stopped = _stat_card("STOPPED", C_DIM)
        card_t, self.stat_total   = _stat_card("TOTAL PROFILES", "white")
        st_layout.addWidget(card_r, 1)
        st_layout.addWidget(card_s, 1)
        st_layout.addWidget(card_t, 1)

        bot_layout.addWidget(stats_bar)
        ct_layout.addWidget(bottom)

        main_layout.addWidget(content, 1)

    # --- DB ---

    def _query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def _exec(self, sql, params=()):
        self.conn.execute(sql, params)
        self.conn.commit()

    def _count(self):
        where = self._build_where()
        return self._query(f"SELECT COUNT(*) as c FROM profiles{where}")[0]["c"]

    def _build_where(self):
        conditions = []
        if self._filter == "running":
            conditions.append("status='running'")
        elif self._filter == "stopped":
            conditions.append("status='stopped'")
        if self.search_text:
            q = self.search_text.replace("'", "''")
            conditions.append(
                f"(name LIKE '%{q}%' OR proxy LIKE '%{q}%' OR ip LIKE '%{q}%' "
                f"OR id LIKE '%{q}%' OR note LIKE '%{q}%')")
        return (" WHERE " + " AND ".join(conditions)) if conditions else ""

    def _get_page(self):
        where = self._build_where()
        offset = self.page * PAGE_SIZE
        return self._query(
            f"SELECT * FROM profiles{where} ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (PAGE_SIZE, offset))

    def _get_by_id(self, pid):
        rows = self._query("SELECT * FROM profiles WHERE id=?", (pid,))
        return dict(rows[0]) if rows else None

    # --- Render ---

    def _render(self):
        # Remove all rows from layout (keep trailing stretch)
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_widgets.clear()

        total = self._count()
        max_page = max(0, (total - 1) // PAGE_SIZE) if total > 0 else 0
        if self.page > max_page:
            self.page = max_page

        rows = self._get_page()
        if rows:
            for row in rows:
                w = ProfileRow(dict(row),
                               on_start=self._start, on_stop=self._stop,
                               on_edit=self._edit, on_delete=self._delete)
                # Insert before the stretch (always last item)
                self.rows_layout.insertWidget(self.rows_layout.count() - 1, w)
                self._row_widgets.append(w)
        else:
            lbl = QLabel("No profiles found. Click '+ Create Profile' to get started.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {C_DIM}; font-size: 14px; padding: 50px; background: transparent;")
            self.rows_layout.insertWidget(0, lbl)
            self._row_widgets.append(lbl)

        self._update_stats()

    def _render_one(self, profile_id):
        row_data = self._get_by_id(profile_id)
        if not row_data:
            return
        for i, w in enumerate(self._row_widgets):
            if hasattr(w, "profile_id") and w.profile_id == profile_id:
                idx = self.rows_layout.indexOf(w)
                new_w = ProfileRow(dict(row_data),
                                   on_start=self._start, on_stop=self._stop,
                                   on_edit=self._edit, on_delete=self._delete)
                self.rows_layout.insertWidget(idx, new_w)
                self.rows_layout.removeWidget(w)
                w.deleteLater()
                self._row_widgets[i] = new_w
                break
        self._update_stats()

    def _update_stats(self):
        total = self._count()
        max_page = max(0, (total - 1) // PAGE_SIZE) if total > 0 else 0
        start = self.page * PAGE_SIZE + 1 if total > 0 else 0
        end = min(start + PAGE_SIZE - 1, total)

        self.page_info.setText(f"Showing {start}-{end} of {total} profiles")
        self.page_lbl.setText(str(self.page + 1))
        self.count_lbl.setText(f"{total} profile(s)")
        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(self.page < max_page)

        running  = self._query("SELECT COUNT(*) as c FROM profiles WHERE status='running'")[0]["c"]
        stopped  = self._query("SELECT COUNT(*) as c FROM profiles WHERE status='stopped'")[0]["c"]
        all_total = self._query("SELECT COUNT(*) as c FROM profiles")[0]["c"]
        self.stat_running.setText(str(running))
        self.stat_stopped.setText(str(stopped))
        self.stat_total.setText(str(all_total))

    # --- Filter ---

    def _set_filter(self, key):
        self._filter = key
        self.page = 0
        for k, btn in self._tab_btns.items():
            btn.setStyleSheet(self._tab_style(k == key))
        self._render()

    # --- Watchdog ---

    def _start_watchdog(self):
        def _check():
            rows = self._query("SELECT id, pid FROM profiles WHERE status='running'")
            changed_ids = []
            for row in rows:
                if not is_pid_alive(row["pid"]):
                    self._exec("UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                               (row["id"],))
                    changed_ids.append(row["id"])
            for pid in changed_ids:
                self.sig_render_one.emit(pid)
        threading.Thread(target=_check, daemon=True).start()
        QTimer.singleShot(5000, self._start_watchdog)

    def _sync_running_status(self):
        rows = self._query("SELECT id, pid FROM profiles WHERE status='running'")
        for row in rows:
            if not is_pid_alive(row["pid"]):
                self._exec("UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                           (row["id"],))

    # --- Search / Paging ---

    def _do_search(self):
        self.search_text = self.search_entry.text().strip().lower()
        self.page = 0
        self._render()

    def _prev(self):
        if self.page > 0:
            self.page -= 1
            self._render()

    def _next(self):
        total = self._count()
        if self.page < (total - 1) // PAGE_SIZE:
            self.page += 1
            self._render()

    # --- Settings ---

    def _open_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setFixedSize(550, 280)
        dlg.setModal(True)
        dlg.setStyleSheet(f"background: {C_BG}; color: white;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)

        title_lbl = QLabel("Settings")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white; background: transparent;")
        layout.addWidget(title_lbl)

        folder_lbl = QLabel("Profile Folder:")
        folder_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(folder_lbl)

        dir_frame = QWidget()
        dir_frame.setStyleSheet("background: transparent;")
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(8)

        dir_entry = QLineEdit(self.settings.get("profile_dir", DEFAULT_PROFILE_DIR))
        dir_entry.setFixedHeight(34)
        dir_entry.setStyleSheet(f"""
            QLineEdit {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                         border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
        """)
        dir_layout.addWidget(dir_entry, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setFixedSize(70, 34)
        browse_btn.setStyleSheet(_btn_style(C_CARD, C_BORDER))
        browse_btn.clicked.connect(lambda: self._browse_dir(dir_entry))
        dir_layout.addWidget(browse_btn)
        layout.addWidget(dir_frame)

        def save():
            d = dir_entry.text().strip()
            if d:
                os.makedirs(d, exist_ok=True)
                self.settings["profile_dir"] = d
                save_settings(self.settings)
                self.status_lbl.setText(f"Saved: {d}")
                dlg.accept()

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(120, 36)
        save_btn.setStyleSheet(_btn_style(C_ACCENT, "#00a884") + " QPushButton { font-weight: bold; }")
        save_btn.clicked.connect(save)
        layout.addWidget(save_btn)

        chrome_status = "Found" if os.path.exists(CHROME_PATH) else "NOT FOUND"
        chrome_lbl = QLabel(f"Chrome: {CHROME_PATH}")
        chrome_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 10px; background: transparent;")
        chrome_lbl.setWordWrap(True)
        layout.addWidget(chrome_lbl)

        status_c = QLabel(f"Status: {chrome_status}")
        status_c.setStyleSheet(f"color: {C_GREEN if chrome_status == 'Found' else C_RED}; font-size: 10px; background: transparent;")
        layout.addWidget(status_c)

        dlg.exec()

    def _browse_dir(self, entry):
        d = QFileDialog.getExistingDirectory(self, "Select Profile Folder", entry.text())
        if d:
            entry.setText(d)

    # --- Add ---

    def _add(self):
        dlg = ProfileDialog(self, title="Create Profile")
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result:
            return
        d = dlg.result
        profile_id = str(uuid.uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._exec(
            "INSERT INTO profiles (id, name, proxy, note, automation, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (profile_id, d["name"], d["proxy"], d["note"], int(d["automation"]), now))
        self._render()
        self.status_lbl.setText(f"Created '{d['name']}'")

    # --- Edit ---

    def _edit(self, profile_id):
        row = self._get_by_id(profile_id)
        if not row:
            return
        dlg = ProfileDialog(self, title="Edit Profile", data={
            "name": row["name"], "proxy": row["proxy"],
            "note": row["note"], "automation": bool(row["automation"]),
        })
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result:
            return
        d = dlg.result
        proxy_changed = d["proxy"] != row["proxy"]
        self._exec(
            "UPDATE profiles SET name=?, proxy=?, note=?, automation=?, ip=?, location=?, timezone=? WHERE id=?",
            (d["name"], d["proxy"], d["note"], int(d["automation"]),
             "" if proxy_changed else row["ip"],
             "" if proxy_changed else row["location"],
             "" if proxy_changed else row["timezone"],
             profile_id))
        self._render_one(profile_id)
        self.status_lbl.setText(f"Updated '{d['name']}'")

    # --- Delete ---

    def _delete(self, profile_id):
        row = self._get_by_id(profile_id)
        if not row:
            return
        if row["status"] in ("running", "starting"):
            QMessageBox.warning(self, "Warning", "Stop the profile before deleting.")
            return
        reply = QMessageBox.question(self, "Confirm", f"Delete '{row['name']}'?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        path = os.path.join(self.settings.get("profile_dir", DEFAULT_PROFILE_DIR), profile_id)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except Exception:
                pass
        self._exec("DELETE FROM profiles WHERE id=?", (profile_id,))
        for i, w in enumerate(self._row_widgets):
            if hasattr(w, "profile_id") and w.profile_id == profile_id:
                self.rows_layout.removeWidget(w)
                w.deleteLater()
                self._row_widgets.pop(i)
                break
        if not self._row_widgets or (len(self._row_widgets) == 1 and not hasattr(self._row_widgets[0], "profile_id")):
            self._render()
        else:
            self._update_stats()
        self.status_lbl.setText(f"Deleted '{row['name']}'")

    # --- Start ---

    def _start(self, profile_id):
        row = self._get_by_id(profile_id)
        if not row or row["status"] in ("running", "starting"):
            return

        self._exec("UPDATE profiles SET status='starting' WHERE id=?", (profile_id,))
        self._render_one(profile_id)
        self.status_lbl.setText(f"Starting '{row['name']}'...")

        def _do():
            proxy = row["proxy"].strip() or None
            profile_dir = self.settings.get("profile_dir", DEFAULT_PROFILE_DIR)
            profile_path = os.path.join(profile_dir, profile_id)

            self.sig_status.emit("Checking proxy..." if proxy else "Looking up IP...")
            if proxy:
                geo = check_proxy(proxy)
                if not geo:
                    self._exec("UPDATE profiles SET status='stopped' WHERE id=?", (profile_id,))
                    self.sig_render_one.emit(profile_id)
                    self.sig_error.emit("Proxy Error", f"Proxy not working:\n{proxy}")
                    self.sig_status.emit("Start failed.")
                    return
            else:
                geo = get_ip_info(None)

            self.sig_status.emit("Building profile...")
            config = build_gpm_fg(geo, proxy)
            write_profile_files(profile_path, config)

            args = [
                CHROME_PATH, f"--user-data-dir={profile_path}",
                "--password-store=basic", "--gpm-disable-machine-id",
                "--no-default-browser-check", "--lang=vi",
            ]
            if proxy:
                host, port, _, _ = parse_proxy(proxy)
                args.append(f"--proxy-server={host}:{port}")

            cdp_port = 0
            if row["automation"]:
                cdp_port = random.randint(50000, 65000)
                args.extend([
                    f"--remote-debugging-port={cdp_port}",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--metrics-recording-only", "--hide-crash-restore-bubble",
                    "--no-first-run", "--disable-features=CalculateNativeWinOcclusion",
                    "--turn-off-whats-new", "--disable-popup-blocking",
                ])

            try:
                proc = subprocess.Popen(args)
            except FileNotFoundError:
                self._exec("UPDATE profiles SET status='stopped' WHERE id=?", (profile_id,))
                self.sig_render_one.emit(profile_id)
                self.sig_error.emit("Chrome Not Found",
                    f"Cannot find Chrome at:\n{CHROME_PATH}\n\n"
                    f"Place ChromiumCore in:\n{os.path.join(APP_DIR, 'browser', 'chrome.exe')}")
                self.sig_status.emit("Start failed: Chrome not found.")
                return
            except Exception as e:
                self._exec("UPDATE profiles SET status='stopped' WHERE id=?", (profile_id,))
                self.sig_render_one.emit(profile_id)
                self.sig_error.emit("Start Error", str(e))
                self.sig_status.emit("Start failed.")
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._exec(
                "UPDATE profiles SET status='running', pid=?, cdp_port=?, ip=?, location=?, timezone=?, "
                "gpu=?, cores=?, memory=?, last_run=? WHERE id=?",
                (proc.pid, cdp_port,
                 geo.get("ip", ""), f"{geo.get('city', '')} ({geo.get('country_code', '')})",
                 geo.get("timezone", ""),
                 config["gpm"]["webgl"]["parameter"]["UNMASKED_RENDERER_WEBGL"],
                 config["gpm"]["navigator"]["processorCount"],
                 config["gpm"]["navigator"]["deviceMemory"],
                 now, profile_id))

            self.sig_render_one.emit(profile_id)
            port_msg = f" | CDP: {cdp_port}" if cdp_port else ""
            self.sig_status.emit(f"Started '{row['name']}'{port_msg}")

        threading.Thread(target=_do, daemon=True).start()

    # --- Stop ---

    def _stop(self, profile_id):
        row = self._get_by_id(profile_id)
        if not row or row["status"] != "running":
            return
        kill_pid_tree(row["pid"])
        self._exec("UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?", (profile_id,))
        self._render_one(profile_id)
        self.status_lbl.setText(f"Stopped '{row['name']}'")

    # --- Close ---

    def closeEvent(self, event):
        running = self._query("SELECT id, name, pid FROM profiles WHERE status='running'")
        if not running:
            event.accept()
            return

        names = ", ".join(r["name"] for r in running[:5])
        if len(running) > 5:
            names += f" (+{len(running) - 5} more)"

        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Profiles Running")
        msgbox.setText(
            f"{len(running)} profile(s) still running:\n{names}\n\n"
            "Choose an action:"
        )
        stop_btn = msgbox.addButton("Stop all and exit", QMessageBox.ButtonRole.AcceptRole)
        exit_btn = msgbox.addButton("Exit without stopping", QMessageBox.ButtonRole.DestructiveRole)
        msgbox.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msgbox.exec()

        clicked = msgbox.clickedButton()
        if clicked == stop_btn:
            for row in running:
                kill_pid_tree(row["pid"])
                self._exec("UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                           (row["id"],))
            event.accept()
        elif clicked == exit_btn:
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = App()
    window.show()
    sys.exit(app.exec())
