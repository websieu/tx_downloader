"""
GoLogin Local Profile Creator & Launcher.

Sinh fingerprint profile cho Orbita browser (GoLogin) phía local mà không cần API,
rồi launch trực tiếp chrome.exe của Orbita với --user-data-dir đã chuẩn bị sẵn.

Cấu trúc profile:
    <profile_dir>/<profile_id>/
        First Run
        Local State
        Default/
            Preferences        # chứa key "gologin" với fingerprint
            Bookmarks
            Network/
                Cookies

Usage CLI:
    python -m gologin_ui.gologin_profile_launcher
    python -m gologin_ui.gologin_profile_launcher --proxy "user:pass@host:port"
    python -m gologin_ui.gologin_profile_launcher --proxy "host:port" --automation
"""

import argparse
import json
import os
import pathlib
import random
import secrets
import ssl
import subprocess
import time
import traceback
import urllib.request

try:
    from .proxy_relay import ProxyRelay, is_private_ipv4
except ImportError:
    from proxy_relay import ProxyRelay, is_private_ipv4

# === Paths ===
HOME = str(pathlib.Path.home())
DEFAULT_PROFILE_DIR = os.path.join(HOME, "AppData", "Roaming", "GoLogin", "profiles")
ORBITA_BROWSERS_DIR = os.path.join(HOME, ".gologin", "browser")


def find_latest_orbita():
    """Find newest orbita-browser-XXX directory and its chrome.exe."""
    if not os.path.isdir(ORBITA_BROWSERS_DIR):
        return None, 0
    candidates = []
    for name in os.listdir(ORBITA_BROWSERS_DIR):
        if not name.startswith("orbita-browser-"):
            continue
        try:
            ver = int(name.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            continue
        exe = os.path.join(ORBITA_BROWSERS_DIR, name, "chrome.exe")
        if os.path.isfile(exe):
            candidates.append((ver, exe))
    if not candidates:
        return None, 0
    candidates.sort(reverse=True)
    return candidates[0][1], candidates[0][0]


CHROME_PATH, ORBITA_VERSION = find_latest_orbita()


# === Hardware combos ===
GPU_PROFILES = [
    {"vendor": "Google Inc. (NVIDIA)",
     "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)",
     "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)",
     "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)",
     "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)",
     "renderer": "ANGLE (AMD, AMD Radeon 780M Graphics (0x000015BF) Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)",
     "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)",
     "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)",
     "renderer": "ANGLE (Intel, Intel(R) UHD Graphics (0x00009B41) Direct3D11 vs_5_0 ps_5_0, D3D11)"},
]

HARDWARE_COMBOS = [
    {"cores": 4, "memory": 4},
    {"cores": 4, "memory": 8},
    {"cores": 6, "memory": 8},
    {"cores": 6, "memory": 16},
    {"cores": 8, "memory": 8},
    {"cores": 8, "memory": 16},
    {"cores": 12, "memory": 16},
    {"cores": 12, "memory": 32},
    {"cores": 16, "memory": 16},
    {"cores": 16, "memory": 32},
]

RESOLUTIONS = [
    (1366, 768), (1440, 900), (1536, 864), (1600, 900),
    (1680, 1050), (1920, 1080), (1920, 1200), (2560, 1440),
]


# === Helpers ===

def generate_profile_id():
    """24-char hex giống MongoDB ObjectId — đúng style GoLogin dùng."""
    return secrets.token_hex(12)


def parse_proxy(proxy_str):
    """Parse 'user:pass@host:port' hoặc 'host:port' hoặc 'host:port:user:pass'.
    Returns (host, port, user, pass).
    """
    proxy_str = (proxy_str or "").strip()
    if not proxy_str:
        return None, None, None, None
    for prefix in ["http://", "https://", "socks5://", "socks4://"]:
        if proxy_str.startswith(prefix):
            proxy_str = proxy_str[len(prefix):]
            break

    user = passwd = None
    if "@" in proxy_str:
        auth, hostport = proxy_str.rsplit("@", 1)
        if ":" in auth:
            user, passwd = auth.split(":", 1)
        else:
            user = auth
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
        else:
            host, port = hostport, "80"
    else:
        parts = proxy_str.split(":")
        if len(parts) == 4:
            host, port, user, passwd = parts
        elif len(parts) == 2:
            host, port = parts
        else:
            host, port = proxy_str, "80"
    return host, port, user, passwd


def fetch_json(url, timeout=10, opener=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        if opener:
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [WARN] fetch_json {url}: {e}")
        return None


def get_ip_info(proxy=None):
    """Lookup IP + geolocation. Có proxy thì lấy IP của proxy."""
    print("[*] Looking up IP geolocation...")
    ip = None
    opener = None

    if proxy:
        host, port, user, passwd = parse_proxy(proxy)
        proxy_url = f"http://{host}:{port}"
        if user:
            proxy_url = f"http://{user}:{passwd}@{host}:{port}"
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
        for api in ["http://api.ipify.org?format=json", "http://httpbin.org/ip"]:
            data = fetch_json(api, opener=opener)
            if data:
                ip = data.get("ip") or data.get("origin", "").split(",")[0].strip()
                if ip:
                    break
        if not ip:
            ip = host
    else:
        for api in ["http://api.ipify.org?format=json", "http://httpbin.org/ip"]:
            data = fetch_json(api)
            if data:
                ip = data.get("ip") or data.get("origin", "").split(",")[0].strip()
                if ip:
                    break
        if not ip:
            ip = "127.0.0.1"

    print(f"  IP: {ip}")
    geo = None
    for api in [
        f"http://ip-api.com/json/{ip}?fields=lat,lon,timezone,countryCode,city,query",
        f"https://ipapi.co/{ip}/json/",
    ]:
        data = fetch_json(api)
        if data and (data.get("lat") or data.get("latitude")):
            geo = {
                "ip": ip,
                "lat": data.get("lat") or data.get("latitude"),
                "lon": data.get("lon") or data.get("longitude"),
                "timezone": data.get("timezone"),
                "country_code": data.get("countryCode") or data.get("country_code"),
                "city": data.get("city", ""),
            }
            break
    if not geo:
        print("  [WARN] Geo lookup failed, defaults Hanoi")
        geo = {
            "ip": ip, "lat": 21.0245, "lon": 105.84117,
            "timezone": "Asia/Ho_Chi_Minh", "country_code": "VN", "city": "Hanoi",
        }
    print(f"  Location: {geo['city']} ({geo['country_code']}) | TZ: {geo['timezone']}")
    return geo


# === Fingerprint generation ===

def _media_uid():
    """58-char hex string, kiểu mediaDevices.uid của GoLogin."""
    return secrets.token_hex(29)


def _ua_for_version(orbita_version):
    """Build user agent string mimicking Orbita's Chrome UA."""
    ver = orbita_version or 146
    patch = random.randint(1, 200)
    return (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{ver}.0.7680.{patch} Safari/537.36")


def build_gologin_preferences(geo, proxy=None, name=None, orbita_version=None,
                              canvas_noise=False, webgl_noise=True):
    """Xây dict cho key `gologin` trong Default/Preferences."""
    profile_id = generate_profile_id()
    gpu = random.choice(GPU_PROFILES)
    hw = random.choice(HARDWARE_COMBOS)
    width, height = random.choice(RESOLUTIONS)
    ver = orbita_version or ORBITA_VERSION or 146

    proxy_pref = {"mode": "direct"}
    if proxy:
        host, port, user, passwd = parse_proxy(proxy)
        proxy_pref = {
            "mode": "fixed_servers",
            "schema": "http",
            "server": f"{host}:{port}",
            "username": user or "",
            "password": passwd or "",
        }

    gologin = {
        "profile_id": profile_id,
        "name": name or f"LocalProfile_{random.randint(1000, 9999)}",
        "is_m1": False,
        "userAgent": _ua_for_version(ver),
        "langHeader": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "languages": "vi-VN,vi,en-US,en",
        "screenWidth": width,
        "screenHeight": height,
        "hardwareConcurrency": hw["cores"],
        "deviceMemory": hw["memory"] * 1024,
        "dns": "",
        "doNotTrack": None,
        "startupUrl": "",
        "startup_urls": [""],
        "navigator": {
            "max_touch_points": 0,
            "platform": "Win32",
        },
        "mobile": {
            "enable": False,
            "width": width,
            "height": height,
            "device_scale_factor": 1,
        },
        "timezone": {"id": geo["timezone"]},
        "geoLocation": {
            "mode": "prompt",
            "latitude": float(geo["lat"]),
            "longitude": float(geo["lon"]),
            "accuracy": 100,
        },
        "webRTC": {
            "mode": "alerted" if proxy else "real",
            "enable": True,
            "enabled": True,
            "customize": True,
            "fillBasedOnIp": True,
            "isEmptyIceList": True,
            "localIpMasking": False,
            "localIps": [],
            "publicIp": geo["ip"] if proxy else "",
        },
        "webrtc": {
            "mode": "alerted" if proxy else "real",
            "enable": True,
            "should_fill_empty_ice_list": True,
        },
        "webGl": {
            "mode": True,
            "vendor": gpu["vendor"],
            "renderer": gpu["renderer"],
        },
        "webgl": {
            "metadata": {
                "mode": True,
                "vendor": gpu["vendor"],
                "renderer": gpu["renderer"],
            },
        },
        "webglParams": {
            "antialiasing": True,
            "glCanvas": "webgl2",
            "glParamValues": [
                {"name": "RENDERER", "value": "WebKit WebGL"},
                {"name": "VENDOR", "value": "WebKit"},
            ],
            "shaiderPrecisionFormat": "highp/highp",
            "textureMaxAnisotropyExt": 16,
            "extensions": [
                "EXT_clip_control", "EXT_color_buffer_float", "EXT_color_buffer_half_float",
                "EXT_disjoint_timer_query_webgl2", "EXT_float_blend", "EXT_texture_filter_anisotropic",
                "EXT_texture_norm16", "KHR_parallel_shader_compile", "OES_draw_buffers_indexed",
                "OES_texture_float_linear", "OVR_multiview2", "WEBGL_compressed_texture_s3tc",
                "WEBGL_compressed_texture_s3tc_srgb", "WEBGL_debug_renderer_info",
                "WEBGL_debug_shaders", "WEBGL_lose_context", "WEBGL_multi_draw",
            ],
        },
        "webglNoiceEnable": bool(webgl_noise),
        "webgl_noice_enable": bool(webgl_noise),
        "webgl_noise_enable": bool(webgl_noise),
        "webglNoiseValue": round(random.uniform(5, 80), 3),
        "webgl_noise_value": round(random.uniform(5, 80), 3),
        "webGpu": {
            "api": {"adapter": True, "compat": True, "context": True,
                    "device": True, "gpu": True, "offscreen": True, "twoD": True},
        },
        "canvasMode": "noise" if canvas_noise else "off",
        "canvasNoise": round(random.random(), 8),
        "client_rects_noise_enable": False,
        "getClientRectsNoice": round(random.uniform(0.5, 5), 4),
        "get_client_rects_noise": round(random.uniform(0.5, 5), 4),
        "audioContext": {
            "enable": True,
            "noiseValue": random.uniform(1e-9, 5e-8),
        },
        "mediaDevices": {
            "enable": True,
            "uid": _media_uid(),
            "audioInputs": 1,
            "audioOutputs": 1,
            "videoInputs": 1,
        },
        "plugins": {"all_enable": True, "flash_enable": True},
        "storage": {"enable": True},
        "proxy": proxy_pref,
    }
    return gologin, profile_id


# === Profile files ===

def _top_level_proxy(gologin_section):
    """Build Chrome's top-level Preferences.proxy từ gologin.proxy.

    GoLogin GUI lưu top-level dưới dạng:
        {"mode":"fixed_servers","server":"http://USER:PASS@HOST:PORT"}
    User:pass được embed vào server URL — Chrome std network code đọc field này
    để vừa set proxy vừa auto-auth.
    """
    gp = (gologin_section or {}).get("proxy") or {}
    mode = gp.get("mode")
    if mode != "fixed_servers":
        return None
    server = gp.get("server", "")
    schema = gp.get("schema") or "http"
    user = gp.get("username") or ""
    passwd = gp.get("password") or ""
    if not server:
        return None
    if "://" not in server:
        if user:
            server_url = f"{schema}://{user}:{passwd}@{server}"
        else:
            server_url = f"{schema}://{server}"
    else:
        server_url = server
    return {"mode": "fixed_servers", "server": server_url}


def _minimal_preferences(gologin_section):
    """Stub Preferences đủ cho Chromium boot lên + áp proxy đúng cách."""
    prefs = {
        "browser": {"has_seen_welcome_page": False},
        "credentials_enable_service": True,
        "default_apps_install_state": 3,
        "extensions": {"settings": {}},
        "gologin": gologin_section,
        "intl": {
            "accept_languages": gologin_section.get("languages", "vi,en"),
            "selected_languages": gologin_section.get("languages", "vi,en"),
        },
        "profile": {
            "default_content_setting_values": {"notifications": 2},
            "exit_type": "Normal",
            "exited_cleanly": True,
            "name": gologin_section.get("name", "Profile"),
        },
        "session": {"restore_on_startup": 5, "startup_urls": []},
    }
    tlp = _top_level_proxy(gologin_section)
    if tlp:
        prefs["proxy"] = tlp
    return prefs


def write_profile_files(profile_path, gologin_section):
    """Tạo cấu trúc thư mục + ghi Preferences với key gologin + top-level proxy."""
    default_dir = os.path.join(profile_path, "Default")
    network_dir = os.path.join(default_dir, "Network")
    os.makedirs(network_dir, exist_ok=True)

    preferences = _minimal_preferences(gologin_section)
    pref_path = os.path.join(default_dir, "Preferences")

    # Nếu Preferences đã tồn tại (profile cũ), merge giữ nguyên các key khác
    if os.path.isfile(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing["gologin"] = gologin_section
            # Đồng bộ top-level proxy theo proxy mới (xoá nếu giờ là direct)
            tlp = _top_level_proxy(gologin_section)
            if tlp:
                existing["proxy"] = tlp
            else:
                existing.pop("proxy", None)
            preferences = existing
        except Exception:
            pass

    with open(pref_path, "w", encoding="utf-8") as f:
        json.dump(preferences, f, ensure_ascii=False)

    # Orbita config (intl)
    orbita_cfg = os.path.join(profile_path, "orbita.config")
    if not os.path.exists(orbita_cfg):
        with open(orbita_cfg, "w", encoding="utf-8") as f:
            json.dump({"intl": {
                "accept_languages": gologin_section.get("languages", "vi,en"),
                "selected_languages": gologin_section.get("languages", "vi,en"),
            }}, f, indent="\t")

    local_state = os.path.join(profile_path, "Local State")
    if not os.path.exists(local_state):
        with open(local_state, "w", encoding="utf-8") as f:
            json.dump({"profile": {"info_cache": {}}}, f)
    first_run = os.path.join(profile_path, "First Run")
    if not os.path.exists(first_run):
        open(first_run, "w").close()


# === Launch ===

def build_launch_args(chrome_path, profile_path, gologin_section,
                      proxy=None, automation=False, debug_port=0,
                      dns_leak_protection=False):
    """Build Orbita launch argv. Theo style của GoLogin GUI khi run profile.

    dns_leak_protection: opt-in. Bật --host-resolver-rules='MAP * 0.0.0.0' để buộc
        mọi DNS đi qua proxy. CẢNH BÁO: với HTTP proxy (đặc biệt local/LAN proxy)
        flag này khiến Chrome trả về ERR_ADDRESS_INVALID. Default = False.
    """
    width = gologin_section.get("screenWidth", 1920)
    height = gologin_section.get("screenHeight", 1080)
    name = gologin_section.get("name", "profile")

    args = [
        chrome_path,
        f"--user-data-dir={profile_path}",
        f"--gologin-profile={name}",
        "--password-store=basic",
        "--webrtc-ip-handling-policy=default_public_interface_only",
        "--disable-features=PrintCompositorLPAC",
        "--font-masking-mode=1",
        "--no-default-browser-check",
        f"--lang=vi-VN",
        f"--window-size={width},{height}",
        "--restore-last-session",
    ]

    if dns_leak_protection and proxy:
        host, _, _, _ = parse_proxy(proxy)
        excludes = ["api.gologin.com", "api.gologin.co"]
        if host:
            excludes.append(host)
        hr_rules = "MAP * 0.0.0.0 , " + " , ".join(f"EXCLUDE {h}" for h in excludes)
        args.append(f"--host-resolver-rules={hr_rules}")

    # Orbita >=135 đọc proxy từ Preferences (fixed_servers); với version cũ hơn
    # vẫn truyền --proxy-server cho chắc.
    if proxy and (ORBITA_VERSION or 0) < 135:
        host, port, _, _ = parse_proxy(proxy)
        args.append(f"--proxy-server={host}:{port}")

    if automation and debug_port:
        args.extend([
            f"--remote-debugging-port={debug_port}",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--hide-crash-restore-bubble",
            "--no-first-run",
            "--disable-features=CalculateNativeWinOcclusion",
            "--turn-off-whats-new",
            "--disable-popup-blocking",
        ])
    return args


def launch_profile(profile_path, gologin_section, proxy=None,
                   automation=False, chrome_path=None):
    chrome_path = chrome_path or CHROME_PATH
    if not chrome_path or not os.path.isfile(chrome_path):
        raise FileNotFoundError(
            f"Orbita chrome.exe not found. Run GoLogin once to download it. "
            f"Looked in: {ORBITA_BROWSERS_DIR}")

    debug_port = random.randint(50000, 65000) if automation else 0
    args = build_launch_args(chrome_path, profile_path, gologin_section,
                             proxy=proxy, automation=automation, debug_port=debug_port)
    print(f"[*] Launching: {chrome_path}")
    if debug_port:
        print(f"[*] CDP port: {debug_port}")
    proc = subprocess.Popen(args)
    return proc, debug_port


def maybe_start_relay(proxy):
    """Nếu proxy là private LAN hoặc có auth → start relay 127.0.0.1 và return
    (relay, loopback_proxy_url). Ngược lại return (None, original_proxy).

    Orbita 146 block direct connection tới RFC1918 LAN, nên private proxy phải
    đi qua loopback bridge.
    """
    if not proxy:
        return None, None
    host, port, user, passwd = parse_proxy(proxy)
    if not host or not port:
        return None, None
    needs_relay = bool(user) or is_private_ipv4(host)
    if not needs_relay:
        return None, proxy
    relay = ProxyRelay(host, int(port), user or "", passwd or "")
    relay.start()
    return relay, relay.local_url


def create_and_launch(profile_base_dir=None, proxy=None, name=None,
                      automation=False, canvas_noise=False):
    """Full end-to-end: lookup geo → build fingerprint → start relay (nếu cần)
    → write files → launch. Trả về relay để caller stop khi profile đóng."""
    base = profile_base_dir or DEFAULT_PROFILE_DIR
    os.makedirs(base, exist_ok=True)

    geo = get_ip_info(proxy)

    # Start loopback relay nếu cần (private LAN hoặc proxy có auth)
    relay, effective_proxy = maybe_start_relay(proxy)
    if relay:
        print(f"[*] Loopback relay 127.0.0.1:{relay.local_port} -> "
              f"{relay.upstream_host}:{relay.upstream_port}")

    # Fingerprint vẫn build theo proxy gốc (cho gologin.proxy info), nhưng
    # browser-effective proxy là loopback URL.
    gologin, profile_id = build_gologin_preferences(
        geo, proxy=effective_proxy, name=name, canvas_noise=canvas_noise)
    profile_path = os.path.join(base, profile_id)
    os.makedirs(profile_path, exist_ok=True)
    write_profile_files(profile_path, gologin)

    print(f"[*] Profile ID  : {profile_id}")
    print(f"[*] Profile path: {profile_path}")
    print(f"[*] GPU         : {gologin['webgl']['metadata']['renderer']}")
    print(f"[*] CPU/RAM     : {gologin['hardwareConcurrency']} cores / "
          f"{gologin['deviceMemory']//1024} GB")
    print(f"[*] Resolution  : {gologin['screenWidth']}x{gologin['screenHeight']}")

    try:
        proc, port = launch_profile(profile_path, gologin,
                                    proxy=effective_proxy, automation=automation)
    except Exception:
        if relay:
            relay.stop()
        raise
    print("=" * 60)
    print(f"  Profile ID : {profile_id}")
    print(f"  PID        : {proc.pid}")
    print(f"  IP         : {geo['ip']}")
    print(f"  Location   : {geo.get('city','')} ({geo['country_code']})")
    print(f"  Timezone   : {geo['timezone']}")
    if port:
        print(f"  CDP Port   : {port}  ->  http://127.0.0.1:{port}")
    if relay:
        print(f"  Relay      : 127.0.0.1:{relay.local_port}")
    print("=" * 60)
    return profile_id, profile_path, proc, port, geo, gologin, relay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GoLogin Local Profile Creator & Launcher")
    parser.add_argument("--proxy", "-p", type=str, default=None,
                        help="Proxy: user:pass@host:port hoặc host:port")
    parser.add_argument("--name", "-n", type=str, default=None,
                        help="Profile name")
    parser.add_argument("--dir", "-d", type=str, default=None,
                        help=f"Profile base dir (default: {DEFAULT_PROFILE_DIR})")
    parser.add_argument("--automation", "-a", action="store_true",
                        help="Bật CDP remote debugging")
    parser.add_argument("--canvas-noise", action="store_true",
                        help="Bật canvas noise (off default — noise dễ bị flag trên YouTube)")
    args = parser.parse_args()

    try:
        result = create_and_launch(
            profile_base_dir=args.dir, proxy=args.proxy, name=args.name,
            automation=args.automation, canvas_noise=args.canvas_noise,
        )
        # CLI: keep relay alive while browser runs
        _pid, _path, _proc, _port, _geo, _gl, _relay = result
        try:
            _proc.wait()
        except KeyboardInterrupt:
            pass
        finally:
            if _relay:
                _relay.stop()
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()
