"""
GoLogin Local Profile Manager GUI - PyQt6.
Same UX as gpm_manager nhưng cho profile Orbita (GoLogin) sinh từ local.
"""

import os
import sys

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")

import json
import random
import shutil
import sqlite3
import subprocess
import threading
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QScrollArea, QFrame,
    QMessageBox, QFileDialog, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon

# Cho phép chạy cả `python -m gologin_ui.gologin_manager` lẫn `python gologin_manager.py`
_HERE = os.path.dirname(os.path.abspath(__file__))
if __package__ in (None, ""):
    sys.path.insert(0, _HERE)
    from gologin_profile_launcher import (
        DEFAULT_PROFILE_DIR, CHROME_PATH, ORBITA_BROWSERS_DIR, ORBITA_VERSION,
        find_latest_orbita, parse_proxy, get_ip_info,
        build_gologin_preferences, write_profile_files, build_launch_args,
        generate_profile_id, maybe_start_relay,
    )
else:
    from .gologin_profile_launcher import (
        DEFAULT_PROFILE_DIR, CHROME_PATH, ORBITA_BROWSERS_DIR, ORBITA_VERSION,
        find_latest_orbita, parse_proxy, get_ip_info,
        build_gologin_preferences, write_profile_files, build_launch_args,
        generate_profile_id, maybe_start_relay,
    )


# === Paths / settings ===
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
elif sys.argv and not os.path.basename(sys.argv[0]).lower().startswith("python"):
    APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    APP_DIR = _HERE

SETTINGS_FILE = os.path.join(APP_DIR, "gologin_manager_settings.json")
DB_PATH = os.path.join(APP_DIR, "gologin_profiles.db")
PAGE_SIZE = 10

# Colors (dùng lại theme của gpm_manager)
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


# === Settings ===

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"profile_dir": DEFAULT_PROFILE_DIR}


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# === DB ===

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
            canvas_noise INTEGER DEFAULT 0,
            orbita_version INTEGER DEFAULT 0,
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
    for col, default in [
        ("orbita_version", "0"),
        ("canvas_noise", "0"),
        ("last_run", "''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE profiles ADD COLUMN {col} INTEGER DEFAULT {default}"
                         if default == "0" else
                         f"ALTER TABLE profiles ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass
    conn.commit()
    return conn


# === Process helpers ===

_SW_FLAGS = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000


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


# === UI helpers ===

def _trunc(text, n):
    if not text:
        return "--"
    return text if len(text) <= n else text[:n - 2] + ".."


def _btn_style(bg, hover=None, radius=6):
    h = hover or bg
    return (f"QPushButton {{ background: {bg}; border-radius: {radius}px; "
            f"color: white; border: none; }} "
            f"QPushButton:hover {{ background: {h}; }} "
            f"QPushButton:disabled {{ opacity: 0.5; }}")


# === ProfileDialog ===

class ProfileDialog(QDialog):
    def __init__(self, parent, title="New Profile", data=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(520)
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
            ("Name", "name", f"GLProfile_{random.randint(1000, 9999)}", "Profile name"),
            ("Proxy", "proxy", "", "user:pass@host:port (để trống = direct)"),
            ("Note", "note", "", "Optional"),
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

        # Orbita version selector
        ver_lbl = QLabel("Orbita version")
        ver_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 12px; margin-top: 8px; background: transparent;")
        layout.addWidget(ver_lbl)
        self.ver_combo = QComboBox()
        self.ver_combo.setFixedHeight(34)
        self.ver_combo.setStyleSheet(f"""
            QComboBox {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                         border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
            QComboBox QAbstractItemView {{ background: {C_CARD}; color: white;
                                           selection-background-color: {C_ACCENT}; }}
        """)
        versions = _list_orbita_versions()
        self.ver_combo.addItem("Auto (latest)", 0)
        for v in versions:
            self.ver_combo.addItem(f"orbita-browser-{v}", v)
        sel = data.get("orbita_version") or 0
        idx = self.ver_combo.findData(sel)
        if idx >= 0:
            self.ver_combo.setCurrentIndex(idx)
        layout.addWidget(self.ver_combo)

        cb_style = f"""
            QCheckBox {{ color: white; margin-top: 10px; background: transparent; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {C_BORDER}; border-radius: 3px; }}
            QCheckBox::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}
        """
        self.auto_cb = QCheckBox("Enable Automation (CDP debug port)")
        self.auto_cb.setChecked(bool(data.get("automation", False)))
        self.auto_cb.setStyleSheet(cb_style)
        layout.addWidget(self.auto_cb)

        self.canvas_noise_cb = QCheckBox("Canvas Noise (off default — noise dễ bị flag trên YouTube)")
        self.canvas_noise_cb.setChecked(bool(data.get("canvas_noise", False)))
        self.canvas_noise_cb.setStyleSheet(cb_style)
        layout.addWidget(self.canvas_noise_cb)

        btn_frame = QWidget()
        btn_frame.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 18, 0, 0)
        btn_layout.setSpacing(10)

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(140, 38)
        save_btn.setStyleSheet(_btn_style(C_ACCENT, "#00a884") +
                               " QPushButton { font-size: 14px; font-weight: bold; }")
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
            "canvas_noise": self.canvas_noise_cb.isChecked(),
            "orbita_version": int(self.ver_combo.currentData() or 0),
        }
        self.accept()


def _list_orbita_versions():
    if not os.path.isdir(ORBITA_BROWSERS_DIR):
        return []
    out = []
    for name in os.listdir(ORBITA_BROWSERS_DIR):
        if not name.startswith("orbita-browser-"):
            continue
        try:
            v = int(name.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            continue
        if os.path.isfile(os.path.join(ORBITA_BROWSERS_DIR, name, "chrome.exe")):
            out.append(v)
    return sorted(out, reverse=True)


# === ProfileRow ===

class ProfileRow(QFrame):
    def __init__(self, row, on_start, on_stop, on_edit, on_delete, on_open_folder):
        super().__init__()
        self.profile_id = row["id"]
        status = row["status"] or "stopped"

        self.setFixedHeight(52)
        self.setObjectName("ProfileRow")
        self._base = f"QFrame#ProfileRow {{ background: transparent; border-bottom: 1px solid {C_BORDER}; }}"
        self._hover = f"QFrame#ProfileRow {{ background: {C_ROW_HOVER}; border-bottom: 1px solid {C_BORDER}; }}"
        self.setStyleSheet(self._base)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 6, 12, 6)
        layout.setSpacing(5)

        # Col 0: Name + ID
        nw = QWidget()
        nw.setFixedWidth(190)
        nw.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(nw)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(0)
        name_lbl = QLabel(_trunc(row["name"], 22))
        name_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent;")
        id_lbl = QLabel(row["id"])
        id_lbl.setStyleSheet("color: #3d4f5f; font-size: 8px; background: transparent;")
        nl.addWidget(name_lbl)
        nl.addWidget(id_lbl)
        layout.addWidget(nw)

        # Col 1: Status badge
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

        # Col 2: IP + Proxy
        ipw = QWidget()
        ipw.setFixedWidth(170)
        ipw.setStyleSheet("background: transparent;")
        il = QVBoxLayout(ipw)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)
        ip_lbl = QLabel(_trunc(row["ip"], 18))
        ip_lbl.setStyleSheet("color: white; font-size: 12px; background: transparent;")
        proxy = row["proxy"]
        if proxy:
            h, p, _, _ = parse_proxy(proxy)
            ptxt = _trunc(f"{h}:{p}", 22)
        else:
            ptxt = "Direct"
        proxy_lbl = QLabel(ptxt)
        proxy_lbl.setStyleSheet("color: #3d4f5f; font-size: 9px; background: transparent;")
        il.addWidget(ip_lbl)
        il.addWidget(proxy_lbl)
        layout.addWidget(ipw)

        # Col 3: Location
        loc_lbl = QLabel(_trunc(row["location"], 18))
        loc_lbl.setFixedWidth(130)
        loc_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        layout.addWidget(loc_lbl)

        # Col 4: Note
        note_lbl = QLabel(_trunc(row["note"], 12) if row["note"] else "")
        note_lbl.setFixedWidth(80)
        note_lbl.setStyleSheet("color: #3d4f5f; font-size: 10px; background: transparent;")
        layout.addWidget(note_lbl)

        layout.addStretch()

        # Actions
        act = QWidget()
        act.setStyleSheet("background: transparent;")
        al = QHBoxLayout(act)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(3)

        pid = self.profile_id
        if status == "running":
            ss_btn = QPushButton("Stop")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_RED, "#c0392b", 5) +
                                 " QPushButton { font-weight: bold; font-size: 11px; }")
            ss_btn.clicked.connect(lambda: on_stop(pid))
        elif status == "starting":
            ss_btn = QPushButton("...")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_YELLOW, C_YELLOW, 5) + " QPushButton { font-size: 11px; }")
            ss_btn.setEnabled(False)
        else:
            ss_btn = QPushButton("Start")
            ss_btn.setFixedSize(68, 28)
            ss_btn.setStyleSheet(_btn_style(C_GREEN, "#00a884", 5) +
                                 " QPushButton { font-weight: bold; font-size: 11px; }")
            ss_btn.clicked.connect(lambda: on_start(pid))

        folder_btn = QPushButton("📁")
        folder_btn.setFixedSize(30, 28)
        folder_btn.setStyleSheet(_btn_style(C_CARD, C_BORDER, 5) + " QPushButton { font-size: 12px; }")
        folder_btn.clicked.connect(lambda: on_open_folder(pid))

        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(30, 28)
        edit_btn.setStyleSheet(_btn_style(C_CARD, C_BORDER, 5) + " QPushButton { font-size: 13px; }")
        edit_btn.clicked.connect(lambda: on_edit(pid))

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 28)
        del_btn.setStyleSheet(_btn_style(C_CARD, C_RED, 5) + " QPushButton { font-size: 13px; }")
        del_btn.clicked.connect(lambda: on_delete(pid))

        al.addWidget(ss_btn)
        al.addWidget(folder_btn)
        al.addWidget(edit_btn)
        al.addWidget(del_btn)
        layout.addWidget(act)

    def enterEvent(self, event):
        self.setStyleSheet(self._hover)

    def leaveEvent(self, event):
        self.setStyleSheet(self._base)


# === App ===

class App(QMainWindow):
    sig_render_one = pyqtSignal(str)
    sig_render = pyqtSignal()
    sig_status = pyqtSignal(str)
    sig_error = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GoLogin Local Profile Manager")
        self.resize(1180, 720)
        self.setMinimumSize(1000, 560)

        self.settings = load_settings()
        self.conn = get_db()
        self._db_lock = threading.Lock()
        self._relays = {}  # profile_id -> ProxyRelay (alive while profile runs)
        self.page = 0
        self.search_text = ""
        self._row_widgets = []
        self._filter = "all"

        self._build_ui()

        self.sig_render_one.connect(self._render_one)
        self.sig_render.connect(self._render)
        self.sig_status.connect(self.status_lbl.setText)
        self.sig_error.connect(lambda t, m: QMessageBox.critical(self, t, m))

        self._sync_running_status()
        self._render()
        self._start_watchdog()

    # ---- DB ----
    def _query(self, sql, params=()):
        with self._db_lock:
            return self.conn.execute(sql, params).fetchall()

    def _exec(self, sql, params=()):
        with self._db_lock:
            self.conn.execute(sql, params)
            self.conn.commit()

    def _build_where(self):
        cond = []
        if self._filter == "running":
            cond.append("status='running'")
        elif self._filter == "stopped":
            cond.append("status='stopped'")
        if self.search_text:
            q = self.search_text.replace("'", "''")
            cond.append(f"(name LIKE '%{q}%' OR proxy LIKE '%{q}%' OR ip LIKE '%{q}%' "
                        f"OR id LIKE '%{q}%' OR note LIKE '%{q}%')")
        return (" WHERE " + " AND ".join(cond)) if cond else ""

    def _count(self):
        return self._query(f"SELECT COUNT(*) c FROM profiles{self._build_where()}")[0]["c"]

    def _get_page(self):
        offset = self.page * PAGE_SIZE
        return self._query(
            f"SELECT * FROM profiles{self._build_where()} ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (PAGE_SIZE, offset))

    def _get_by_id(self, pid):
        rows = self._query("SELECT * FROM profiles WHERE id=?", (pid,))
        return dict(rows[0]) if rows else None

    # ---- UI ----
    def _tab_style(self, active):
        if active:
            return (f"QPushButton {{ background: {C_ACCENT}; border-radius: 4px; "
                    f"color: white; font-size: 11px; font-weight: bold; border: none; }}")
        return (f"QPushButton {{ background: transparent; border-radius: 4px; "
                f"color: white; font-size: 11px; font-weight: bold; border: none; }} "
                f"QPushButton:hover {{ background: {C_CARD}; }}")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet(f"background: {C_SIDEBAR};")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(15, 20, 15, 20)
        sb.setSpacing(2)

        logo = QLabel("GoLogin")
        logo.setStyleSheet(f"color: {C_ACCENT}; font-size: 18px; font-weight: bold; background: transparent;")
        sub = QLabel("Local Profile Manager")
        sub.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        sb.addWidget(logo)
        sb.addWidget(sub)
        sb.addSpacing(10)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C_BORDER};")
        sb.addWidget(sep)
        sb.addSpacing(8)

        for text, active, cmd in [
            ("Profiles", True, None),
            ("Settings", False, self._open_settings),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(36)
            if active:
                btn.setStyleSheet(f"QPushButton {{ background: {C_ACCENT}; border-radius: 6px; "
                                  f"color: white; font-size: 13px; text-align: left; padding-left: 12px; border: none; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background: transparent; border-radius: 6px; "
                                  f"color: {C_DIM}; font-size: 13px; text-align: left; padding-left: 12px; border: none; }} "
                                  f"QPushButton:hover {{ background: {C_CARD}; color: white; }}")
            if cmd:
                btn.clicked.connect(cmd)
            sb.addWidget(btn)

        sb.addStretch()

        create_btn = QPushButton("+ Create Profile")
        create_btn.setFixedHeight(40)
        create_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_ACCENT}; border-radius: 8px; color: white;
                           font-size: 13px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background: #00a884; }}
        """)
        create_btn.clicked.connect(self._add)
        sb.addWidget(create_btn)

        main.addWidget(sidebar)

        # Content
        content = QWidget()
        content.setStyleSheet(f"background: {C_BG};")
        ct = QVBoxLayout(content)
        ct.setContentsMargins(0, 0, 0, 0)
        ct.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(50)
        top.setStyleSheet(f"background: {C_SIDEBAR};")
        tb = QHBoxLayout(top)
        tb.setContentsMargins(15, 8, 15, 8)
        tb.setSpacing(5)

        self.search_entry = QLineEdit()
        self.search_entry.setFixedSize(280, 34)
        self.search_entry.setPlaceholderText("Search profiles, proxies, IDs...")
        self.search_entry.setStyleSheet(f"""
            QLineEdit {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                         border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
            QLineEdit:focus {{ border-color: {C_ACCENT}; }}
        """)
        self.search_entry.textChanged.connect(self._do_search)
        tb.addWidget(self.search_entry)
        tb.addSpacing(15)

        self._tab_btns = {}
        for label, key in [("ALL", "all"), ("RUNNING", "running"), ("STOPPED", "stopped")]:
            btn = QPushButton(label)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet(self._tab_style(key == "all"))
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            tb.addWidget(btn)
            self._tab_btns[key] = btn

        tb.addStretch()

        # Orbita info badge
        orbita_lbl = QLabel(
            f"Orbita: {ORBITA_VERSION or 'N/A'}" if CHROME_PATH else "Orbita: NOT FOUND")
        orbita_lbl.setStyleSheet(
            f"color: {C_GREEN if CHROME_PATH else C_RED}; font-size: 11px; "
            f"background: {C_CARD}; padding: 4px 10px; border-radius: 4px;")
        tb.addWidget(orbita_lbl)

        ct.addWidget(top)

        # Header
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background: {C_BG};")
        hd = QHBoxLayout(header)
        hd.setContentsMargins(20, 15, 20, 5)
        title_lbl = QLabel("Active Profiles")
        title_lbl.setStyleSheet("color: white; font-size: 22px; font-weight: bold; background: transparent;")
        hd.addWidget(title_lbl)
        hd.addStretch()
        self.count_lbl = QLabel("0 profiles")
        self.count_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 13px; background: transparent;")
        hd.addWidget(self.count_lbl)
        ct.addWidget(header)

        # Table header
        thdr = QWidget()
        thdr.setFixedHeight(38)
        thdr.setStyleSheet(f"background: {C_HEADER};")
        th = QHBoxLayout(thdr)
        th.setContentsMargins(15, 0, 15, 0)
        th.setSpacing(5)
        for text, w in [
            ("PROFILE IDENTITY", 190), ("STATE", 85),
            ("IP / INFRASTRUCTURE", 170), ("LOCATION", 130), ("NOTE", 80),
        ]:
            l = QLabel(text)
            l.setFixedWidth(w)
            l.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
            th.addWidget(l)
        th.addStretch()
        actions_hdr = QLabel("ACTIONS")
        actions_hdr.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
        th.addWidget(actions_hdr)
        ct.addWidget(thdr)

        # Scroll
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
        ct.addWidget(self.scroll_area, 1)

        # Bottom
        bottom = QWidget()
        bottom.setStyleSheet(f"background: {C_SIDEBAR};")
        bot = QVBoxLayout(bottom)
        bot.setContentsMargins(0, 0, 0, 0)
        bot.setSpacing(1)

        paging = QWidget()
        paging.setFixedHeight(44)
        paging.setStyleSheet(f"background: {C_SIDEBAR};")
        pg = QHBoxLayout(paging)
        pg.setContentsMargins(15, 6, 15, 6)
        pg.setSpacing(5)
        self.page_info = QLabel("Showing 0 of 0 profiles")
        self.page_info.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        pg.addWidget(self.page_info)
        pg.addSpacing(15)
        self.btn_prev = QPushButton("❮")
        self.btn_prev.setFixedSize(30, 28)
        self.btn_prev.setStyleSheet(_btn_style(C_CARD, C_BORDER, 4))
        self.btn_prev.clicked.connect(self._prev)
        pg.addWidget(self.btn_prev)
        self.page_lbl = QLabel("1")
        self.page_lbl.setFixedSize(30, 28)
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_lbl.setStyleSheet(
            f"background: {C_ACCENT}; border-radius: 4px; color: white; font-weight: bold; font-size: 11px;")
        pg.addWidget(self.page_lbl)
        self.btn_next = QPushButton("❯")
        self.btn_next.setFixedSize(30, 28)
        self.btn_next.setStyleSheet(_btn_style(C_CARD, C_BORDER, 4))
        self.btn_next.clicked.connect(self._next)
        pg.addWidget(self.btn_next)
        pg.addStretch()
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 11px; background: transparent;")
        pg.addWidget(self.status_lbl)
        bot.addWidget(paging)

        # Stats
        stats = QWidget()
        stats.setFixedHeight(80)
        stats.setStyleSheet(f"background: {C_SIDEBAR};")
        st = QHBoxLayout(stats)
        st.setContentsMargins(20, 10, 20, 10)
        st.setSpacing(5)

        def _card(title, color):
            f = QFrame()
            f.setStyleSheet(f"QFrame {{ background: {C_CARD}; border-radius: 8px; }}")
            cl = QVBoxLayout(f)
            cl.setContentsMargins(15, 8, 15, 8)
            cl.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("color: #5a6a7a; font-size: 9px; font-weight: bold; background: transparent;")
            v = QLabel("0")
            v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold; background: transparent;")
            cl.addWidget(t)
            cl.addWidget(v)
            return f, v

        c_r, self.stat_running = _card("RUNNING", C_GREEN)
        c_s, self.stat_stopped = _card("STOPPED", C_DIM)
        c_t, self.stat_total = _card("TOTAL", "white")
        st.addWidget(c_r, 1)
        st.addWidget(c_s, 1)
        st.addWidget(c_t, 1)

        bot.addWidget(stats)
        ct.addWidget(bottom)
        main.addWidget(content, 1)

    # ---- Render ----
    def _render(self):
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
                w = ProfileRow(
                    dict(row),
                    on_start=self._start, on_stop=self._stop,
                    on_edit=self._edit, on_delete=self._delete,
                    on_open_folder=self._open_folder,
                )
                self.rows_layout.insertWidget(self.rows_layout.count() - 1, w)
                self._row_widgets.append(w)
        else:
            lbl = QLabel("No profiles. Click '+ Create Profile' để bắt đầu.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {C_DIM}; font-size: 14px; padding: 50px; background: transparent;")
            self.rows_layout.insertWidget(0, lbl)
            self._row_widgets.append(lbl)

        self._update_stats()

    def _render_one(self, pid):
        row = self._get_by_id(pid)
        if not row:
            return
        for i, w in enumerate(self._row_widgets):
            if hasattr(w, "profile_id") and w.profile_id == pid:
                idx = self.rows_layout.indexOf(w)
                new_w = ProfileRow(
                    row,
                    on_start=self._start, on_stop=self._stop,
                    on_edit=self._edit, on_delete=self._delete,
                    on_open_folder=self._open_folder,
                )
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

        running = self._query("SELECT COUNT(*) c FROM profiles WHERE status='running'")[0]["c"]
        stopped = self._query("SELECT COUNT(*) c FROM profiles WHERE status='stopped'")[0]["c"]
        all_t = self._query("SELECT COUNT(*) c FROM profiles")[0]["c"]
        self.stat_running.setText(str(running))
        self.stat_stopped.setText(str(stopped))
        self.stat_total.setText(str(all_t))

    # ---- Filter / Search / Paging ----
    def _set_filter(self, key):
        self._filter = key
        self.page = 0
        for k, btn in self._tab_btns.items():
            btn.setStyleSheet(self._tab_style(k == key))
        self._render()

    def _do_search(self):
        self.search_text = self.search_entry.text().strip().lower()
        self.page = 0
        self._render()

    def _prev(self):
        if self.page > 0:
            self.page -= 1
            self._render()

    def _next(self):
        if self.page < (self._count() - 1) // PAGE_SIZE:
            self.page += 1
            self._render()

    # ---- Watchdog ----
    def _start_watchdog(self):
        def _check():
            rows = self._query("SELECT id, pid FROM profiles WHERE status='running'")
            for row in rows:
                if not is_pid_alive(row["pid"]):
                    self._stop_relay(row["id"])
                    self._exec(
                        "UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                        (row["id"],))
                    self.sig_render_one.emit(row["id"])

        threading.Thread(target=_check, daemon=True).start()
        QTimer.singleShot(5000, self._start_watchdog)

    def _sync_running_status(self):
        rows = self._query("SELECT id, pid FROM profiles WHERE status='running'")
        for row in rows:
            if not is_pid_alive(row["pid"]):
                self._exec(
                    "UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                    (row["id"],))

    # ---- Settings ----
    def _open_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setFixedSize(560, 320)
        dlg.setModal(True)
        dlg.setStyleSheet(f"background: {C_BG}; color: white;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        title_lbl = QLabel("Settings")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white; background: transparent;")
        layout.addWidget(title_lbl)

        ent_style = f"""
            QLineEdit {{ background: {C_CARD}; border: 1px solid {C_BORDER};
                         border-radius: 6px; padding: 0 10px; color: white; font-size: 12px; }}
            QLineEdit:focus {{ border-color: {C_ACCENT}; }}
        """

        folder_lbl = QLabel("Profile Folder:")
        folder_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(folder_lbl)

        dir_frame = QWidget()
        dir_frame.setStyleSheet("background: transparent;")
        dl = QHBoxLayout(dir_frame)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(8)
        dir_entry = QLineEdit(self.settings.get("profile_dir", DEFAULT_PROFILE_DIR))
        dir_entry.setFixedHeight(34)
        dir_entry.setStyleSheet(ent_style)
        dl.addWidget(dir_entry, 1)
        browse = QPushButton("Browse")
        browse.setFixedSize(70, 34)
        browse.setStyleSheet(_btn_style(C_CARD, C_BORDER))
        browse.clicked.connect(lambda: self._browse(dir_entry))
        dl.addWidget(browse)
        layout.addWidget(dir_frame)

        # Orbita chrome path (read-only auto-detected)
        chrome_lbl = QLabel("Orbita chrome.exe (auto-detect):")
        chrome_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(chrome_lbl)

        chrome_entry = QLineEdit(CHROME_PATH or "NOT FOUND")
        chrome_entry.setReadOnly(True)
        chrome_entry.setFixedHeight(34)
        chrome_entry.setStyleSheet(ent_style)
        layout.addWidget(chrome_entry)

        info_lbl = QLabel(
            f"Orbita version: {ORBITA_VERSION or 'N/A'}  |  "
            f"Browsers dir: {ORBITA_BROWSERS_DIR}"
        )
        info_lbl.setStyleSheet(f"color: {C_DIM}; font-size: 10px; background: transparent;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        layout.addStretch()

        def _save():
            d = dir_entry.text().strip()
            if d:
                os.makedirs(d, exist_ok=True)
                self.settings["profile_dir"] = d
            save_settings(self.settings)
            self.status_lbl.setText("Settings saved")
            dlg.accept()

        save = QPushButton("Save")
        save.setFixedSize(120, 36)
        save.setStyleSheet(_btn_style(C_ACCENT, "#00a884") + " QPushButton { font-weight: bold; }")
        save.clicked.connect(_save)
        layout.addWidget(save)

        dlg.exec()

    def _browse(self, entry):
        d = QFileDialog.getExistingDirectory(self, "Select Profile Folder", entry.text())
        if d:
            entry.setText(d)

    # ---- Add ----
    def _add(self):
        dlg = ProfileDialog(self, title="Create Profile")
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result:
            return
        d = dlg.result
        pid = generate_profile_id()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._exec(
            "INSERT INTO profiles (id, name, proxy, note, automation, canvas_noise, orbita_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, d["name"], d["proxy"], d["note"],
             int(d["automation"]), int(d["canvas_noise"]),
             int(d["orbita_version"]), now))
        self._render()
        self.status_lbl.setText(f"Created '{d['name']}'")

    # ---- Edit ----
    def _edit(self, pid):
        row = self._get_by_id(pid)
        if not row:
            return
        if row["status"] in ("running", "starting"):
            QMessageBox.warning(self, "Warning", "Cannot edit while profile is running.")
            return
        dlg = ProfileDialog(self, title="Edit Profile", data={
            "name": row["name"], "proxy": row["proxy"], "note": row["note"],
            "automation": bool(row["automation"]),
            "canvas_noise": bool(row.get("canvas_noise") or 0),
            "orbita_version": int(row.get("orbita_version") or 0),
        })
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result:
            return
        d = dlg.result
        proxy_changed = d["proxy"] != row["proxy"]
        self._exec(
            "UPDATE profiles SET name=?, proxy=?, note=?, automation=?, canvas_noise=?, "
            "orbita_version=?, ip=?, location=?, timezone=? WHERE id=?",
            (d["name"], d["proxy"], d["note"],
             int(d["automation"]), int(d["canvas_noise"]),
             int(d["orbita_version"]),
             "" if proxy_changed else row["ip"],
             "" if proxy_changed else row["location"],
             "" if proxy_changed else row["timezone"],
             pid))
        self._render_one(pid)
        self.status_lbl.setText(f"Updated '{d['name']}'")

    # ---- Delete ----
    def _delete(self, pid):
        row = self._get_by_id(pid)
        if not row:
            return
        if row["status"] in ("running", "starting"):
            QMessageBox.warning(self, "Warning", "Stop the profile before deleting.")
            return
        if QMessageBox.question(self, "Confirm", f"Delete '{row['name']}'?\n\n"
                                                  f"Folder và DB entry sẽ bị xoá.") != QMessageBox.StandardButton.Yes:
            return
        path = os.path.join(self.settings.get("profile_dir", DEFAULT_PROFILE_DIR), pid)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                print(f"rmtree failed: {e}")
        self._exec("DELETE FROM profiles WHERE id=?", (pid,))
        self._render()
        self.status_lbl.setText(f"Deleted '{row['name']}'")

    # ---- Open Folder ----
    def _open_folder(self, pid):
        path = os.path.join(self.settings.get("profile_dir", DEFAULT_PROFILE_DIR), pid)
        if not os.path.isdir(path):
            QMessageBox.information(self, "Folder", f"Folder chưa tồn tại.\nSẽ tạo khi Start lần đầu.\n{path}")
            return
        try:
            subprocess.Popen(["explorer", path])
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ---- Start ----
    def _start(self, pid):
        row = self._get_by_id(pid)
        if not row or row["status"] in ("running", "starting"):
            return
        if not CHROME_PATH:
            QMessageBox.critical(
                self, "Orbita Not Found",
                f"Không tìm thấy Orbita chrome.exe ở:\n{ORBITA_BROWSERS_DIR}\n\n"
                f"Mở GoLogin app 1 lần để nó download Orbita về.")
            return

        self._exec("UPDATE profiles SET status='starting' WHERE id=?", (pid,))
        self._render_one(pid)
        self.sig_status.emit(f"Starting '{row['name']}'...")

        def _do():
            relay = None
            try:
                proxy = (row["proxy"] or "").strip() or None
                profile_dir = self.settings.get("profile_dir", DEFAULT_PROFILE_DIR)
                profile_path = os.path.join(profile_dir, pid)
                os.makedirs(profile_path, exist_ok=True)

                # Lookup geo / IP via UPSTREAM proxy (relay chưa start)
                self.sig_status.emit("Checking proxy/IP..." if proxy else "Looking up IP...")
                geo = get_ip_info(proxy)
                if proxy and (not geo or not geo.get("ip") or geo["ip"] == "127.0.0.1"):
                    self._abort_start(pid, "Proxy Error", f"Proxy không lookup được IP:\n{proxy}")
                    return

                # Start loopback relay nếu LAN proxy / có auth — Orbita không kết nối
                # được trực tiếp tới RFC1918, phải đi qua 127.0.0.1
                effective_proxy = proxy
                if proxy:
                    relay, effective_proxy = maybe_start_relay(proxy)
                    if relay:
                        self._relays[pid] = relay
                        self.sig_status.emit(
                            f"Loopback relay 127.0.0.1:{relay.local_port} -> "
                            f"{relay.upstream_host}:{relay.upstream_port}")

                # Build fingerprint (chỉ build khi chưa có Preferences, không thì giữ nguyên fingerprint cũ)
                pref_path = os.path.join(profile_path, "Default", "Preferences")
                gologin = None
                if os.path.isfile(pref_path):
                    try:
                        with open(pref_path, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                        gologin = existing.get("gologin")
                        if gologin:
                            gologin["timezone"] = {"id": geo["timezone"]}
                            gologin["geoLocation"] = {
                                "mode": "prompt",
                                "latitude": float(geo["lat"]),
                                "longitude": float(geo["lon"]),
                                "accuracy": 100,
                            }
                            if effective_proxy:
                                gologin.setdefault("webRTC", {})
                                gologin["webRTC"]["publicIp"] = geo["ip"]
                                h, p, u, pw = parse_proxy(effective_proxy)
                                gologin["proxy"] = {
                                    "mode": "fixed_servers", "schema": "http",
                                    "server": f"{h}:{p}",
                                    "username": u or "", "password": pw or "",
                                }
                            else:
                                gologin["proxy"] = {"mode": "direct"}
                            gologin["name"] = row["name"]
                    except Exception:
                        gologin = None

                if not gologin:
                    self.sig_status.emit("Building fingerprint...")
                    ov = int(row.get("orbita_version") or 0) or None
                    cn = bool(row.get("canvas_noise") or 0)
                    gologin, _new_id = build_gologin_preferences(
                        geo, proxy=effective_proxy, name=row["name"],
                        orbita_version=ov, canvas_noise=cn,
                    )
                    gologin["profile_id"] = pid

                write_profile_files(profile_path, gologin)

                # Pick chrome
                chrome = CHROME_PATH
                ov = int(row.get("orbita_version") or 0)
                if ov:
                    candidate = os.path.join(ORBITA_BROWSERS_DIR, f"orbita-browser-{ov}", "chrome.exe")
                    if os.path.isfile(candidate):
                        chrome = candidate

                cdp_port = random.randint(50000, 65000) if row["automation"] else 0
                args = build_launch_args(
                    chrome, profile_path, gologin,
                    proxy=effective_proxy, automation=bool(row["automation"]),
                    debug_port=cdp_port,
                )

                try:
                    proc = subprocess.Popen(args)
                except Exception as e:
                    if relay:
                        relay.stop()
                        self._relays.pop(pid, None)
                    self._abort_start(pid, "Launch Error", str(e))
                    traceback.print_exc()
                    return

                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                gpu = gologin.get("webgl", {}).get("metadata", {}).get("renderer", "")
                self._exec(
                    "UPDATE profiles SET status='running', pid=?, cdp_port=?, ip=?, location=?, "
                    "timezone=?, gpu=?, cores=?, memory=?, last_run=? WHERE id=?",
                    (proc.pid, cdp_port, geo["ip"],
                     f"{geo.get('city','')} ({geo.get('country_code','')})",
                     geo["timezone"], gpu,
                     gologin.get("hardwareConcurrency", 0),
                     (gologin.get("deviceMemory", 0) or 0) // 1024,
                     now, pid))
                self.sig_render_one.emit(pid)
                port_msg = f" | CDP: {cdp_port}" if cdp_port else ""
                self.sig_status.emit(f"Started '{row['name']}'{port_msg}")
            except Exception as e:
                traceback.print_exc()
                self._abort_start(pid, "Start Error", str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _abort_start(self, pid, title, msg):
        self._exec("UPDATE profiles SET status='stopped' WHERE id=?", (pid,))
        self.sig_render_one.emit(pid)
        self.sig_error.emit(title, msg)
        self.sig_status.emit("Start failed.")

    # ---- Stop ----
    def _stop(self, pid):
        row = self._get_by_id(pid)
        if not row or row["status"] != "running":
            return
        kill_pid_tree(row["pid"])
        self._stop_relay(pid)
        self._exec("UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?", (pid,))
        self._render_one(pid)
        self.status_lbl.setText(f"Stopped '{row['name']}'")

    def _stop_relay(self, pid):
        relay = self._relays.pop(pid, None)
        if relay:
            try:
                relay.stop()
            except Exception:
                pass

    # ---- Close ----
    def closeEvent(self, event):
        running = self._query("SELECT id, name, pid FROM profiles WHERE status='running'")
        if not running:
            event.accept()
            return
        names = ", ".join(r["name"] for r in running[:5])
        if len(running) > 5:
            names += f" (+{len(running) - 5} more)"
        reply = QMessageBox.question(
            self, "Profiles Running",
            f"{len(running)} profile(s) đang chạy:\n{names}\n\nStop all & exit?")
        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        for row in running:
            kill_pid_tree(row["pid"])
            self._stop_relay(row["id"])
            self._exec(
                "UPDATE profiles SET status='stopped', pid=0, cdp_port=0 WHERE id=?",
                (row["id"],))
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
