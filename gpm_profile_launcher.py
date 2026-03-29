"""
GPM Login Profile Creator & Launcher
Tạo profile ChromiumCore với fingerprint noise ngẫu nhiên và launch browser.

Usage:
    # Không proxy
    python gpm_profile_launcher.py

    # Có proxy (hỗ trợ user:pass)
    python gpm_profile_launcher.py --proxy "user:pass@host:port"
    python gpm_profile_launcher.py --proxy "host:port"

    # Bật automation (CDP debug port)
    python gpm_profile_launcher.py --proxy "user:pass@host:port" --automation
"""

import argparse
import base64
import json
import os
import random
import subprocess
import sys
import uuid
import urllib.request
import ssl
import time

# === CONFIG ===
PROFILE_BASE_DIR = r"D:\Youtube\profile"
CHROME_PATH = os.path.join(
    os.environ["APPDATA"],
    "GPMLoginGlobal", "Browsers", "ChromiumCore_v144", "chrome.exe"
)
def _find_font_dir(base_dir):
    """Find any existing profile that has fonts."""
    if not os.path.isdir(base_dir):
        return None
    for d in os.listdir(base_dir):
        fp = os.path.join(base_dir, d, "Default", "GPMSoft", "Fonts")
        if os.path.isdir(fp) and os.listdir(fp):
            return fp
    return None

FONT_SOURCE_DIR = _find_font_dir(PROFILE_BASE_DIR)


# === HARDWARE PROFILES (realistic combinations) ===
GPU_PROFILES = [
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 4318, "deviceId": 9348,
        "maxSamples": 8,
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 4318, "deviceId": 7937,
        "maxSamples": 8,
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 4318, "deviceId": 10114,
        "maxSamples": 8,
    },
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 4098, "deviceId": 26591,
        "maxSamples": 8,
    },
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon 780M Graphics (0x000015BF) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 4098, "deviceId": 29776,
        "maxSamples": 8,
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 32902, "deviceId": 16018,
        "maxSamples": 16,
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 32902, "deviceId": 39497,
        "maxSamples": 16,
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) UHD Graphics (0x00004626) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendorId": 32902, "deviceId": 39424,
        "maxSamples": 16,
    },
]

# Realistic CPU/memory combos
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

FONT_SETS = [
    ["Scriptina", "Aharoni"],
    ["Ouverture script", "WP Greek Courier"],
    ["Scriptina", "WP Greek Courier"],
    ["Aharoni", "Ouverture script"],
    ["Scriptina"],
    ["Aharoni"],
]

CHROME_VERSION = "144.0.7559.110"


def fetch_json(url, timeout=10):
    """Fetch JSON from URL, returns dict or None."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None


def get_ip_info(proxy=None):
    """
    Lấy thông tin IP + geolocation.
    Nếu có proxy, lấy IP của proxy. Nếu không, lấy IP thật.
    Returns: dict {ip, lat, lon, timezone, country_code}
    """
    print("[*] Looking up IP geolocation...")

    if proxy:
        # Parse proxy
        proxy_host, proxy_port, proxy_user, proxy_pass = parse_proxy(proxy)
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        if proxy_user:
            proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"

        # Use proxy to get our outbound IP
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        })
        opener = urllib.request.build_opener(proxy_handler)

        ip = None
        for api in ["http://api.ipify.org?format=json", "http://httpbin.org/ip"]:
            try:
                req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with opener.open(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    ip = data.get("ip") or data.get("origin", "").split(",")[0].strip()
                    if ip:
                        break
            except Exception as e:
                print(f"  [WARN] {api} via proxy failed: {e}")
                continue

        if not ip:
            print("  [ERROR] Cannot determine proxy IP, using proxy host as IP")
            ip = proxy_host
    else:
        # No proxy - get real IP
        ip = None
        for api in ["http://api.ipify.org?format=json", "http://httpbin.org/ip"]:
            data = fetch_json(api)
            if data:
                ip = data.get("ip") or data.get("origin", "").split(",")[0].strip()
                if ip:
                    break
        if not ip:
            ip = "127.0.0.1"

    print(f"  IP: {ip}")

    # Lookup geolocation
    geo = None
    for api in [
        f"http://ip-api.com/json/{ip}?fields=lat,lon,timezone,countryCode,city",
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
        print("  [WARN] Geolocation lookup failed, using defaults (Hanoi)")
        geo = {
            "ip": ip,
            "lat": 21.0245,
            "lon": 105.84117,
            "timezone": "Asia/Ho_Chi_Minh",
            "country_code": "VN",
            "city": "Hanoi",
        }

    print(f"  Location: {geo['city']} ({geo['country_code']})")
    print(f"  Lat/Lon: {geo['lat']}, {geo['lon']}")
    print(f"  Timezone: {geo['timezone']}")
    return geo


def parse_proxy(proxy_str):
    """
    Parse proxy string. Returns (host, port, user, pass).
    Supported formats:
        host:port
        user:pass@host:port
        host:port:user:pass
        http://user:pass@host:port
    """
    proxy_str = proxy_str.strip()
    # Remove protocol prefix if present
    for prefix in ["http://", "https://", "socks5://"]:
        if proxy_str.startswith(prefix):
            proxy_str = proxy_str[len(prefix):]
            break

    user = passwd = None
    if "@" in proxy_str:
        # user:pass@host:port
        auth, hostport = proxy_str.rsplit("@", 1)
        if ":" in auth:
            user, passwd = auth.split(":", 1)
        else:
            user = auth
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
        else:
            host = hostport
            port = "80"
    else:
        parts = proxy_str.split(":")
        if len(parts) == 4:
            # host:port:user:pass
            host, port, user, passwd = parts
        elif len(parts) == 2:
            # host:port
            host, port = parts
        else:
            host = proxy_str
            port = "80"

    return host, port, user, passwd


def generate_noise_values():
    """Generate random but realistic canvas/audio/webgl noise values."""
    return {
        "canvas": {
            "noiseGlobalAlpha": random.random(),
            "noiseShadowBlur": random.random() * 2,
            "noiseShadowOffsetX": random.random(),
            "noiseShadowOffsetY": random.random(),
            "noiseTextX": random.random(),
            "noiseTextY": random.random(),
            "noiseToken": random.randint(100000000, 999999999),
        },
        "audio": round(-random.random() * 10, 15),
        "clientRect": round(random.random() * 20, 15),
        "webgl": {
            "uniform1": round(random.random() * 0.1, 15),
            "uniform2": round(random.random() * 0.5, 15),
            "uniform3": round(random.random() * 0.1, 15),
            "uniform4": round(random.random() * 0.2, 15),
            "readPixelsIndex": float(random.randint(0, 1000)),
            "readPixelsNoiseVal": float(random.randint(0, 255)),
        },
    }


def build_gpm_fg(geo_info, proxy_info=None):
    """Build the full gpm_fg.dat JSON config."""
    gpu = random.choice(GPU_PROFILES)
    hw = random.choice(HARDWARE_COMBOS)
    fonts = random.choice(FONT_SETS)
    noise = generate_noise_values()

    # JS heap size limit - realistic values
    heap_limits = [2147483648, 4294966992, 4294967296, 4294966418]

    proxy_host, proxy_port, proxy_user, proxy_pass = (None, None, None, None)
    if proxy_info:
        proxy_host, proxy_port, proxy_user, proxy_pass = parse_proxy(proxy_info)

    config = {
        "gpm": {
            "version": "2026.01",
            "name": f"AutoProfile_{random.randint(1000, 9999)}",
            "userAgent": "",
            "timezone": geo_info["timezone"],
            "font": {
                "mode": "noise",
                "includes": fonts,
                "excludes": [],
            },
            "screen": {
                "mode": "real",
                "height": -1,
                "width": -1,
                "availHeight": -1,
                "availWidth": -1,
                "maxWindowWidth": -1,
                "maxWindowHeight": -1,
                "maxTouchPoints": 0,
            },
            "navigator": {
                "mode": "noise",
                "processorCount": hw["cores"],
                "deviceMemory": hw["memory"],
                "jsHeapSizeLimit": random.choice(heap_limits),
            },
            "webgpu": {
                "mode": "noise",
                "vendorId": gpu["vendorId"],
                "deviceId": gpu["deviceId"],
            },
            "audio": {
                "mode": "noise",
                "noise": noise["audio"],
                "numberInput": 1,
                "numberOutput": 1,
            },
            "canvas": {
                "mode": "noise",
                **noise["canvas"],
            },
            "clientRect": {
                "mode": "noise",
                "noise": noise["clientRect"],
            },
            "webgl": {
                "mode": "noise",
                "webglMetaMode": "noise",
                "uniform1Noise": noise["webgl"]["uniform1"],
                "uniform2Noise": noise["webgl"]["uniform2"],
                "uniform3Noise": noise["webgl"]["uniform3"],
                "uniform4Noise": noise["webgl"]["uniform4"],
                "readPixelsIndex": noise["webgl"]["readPixelsIndex"],
                "readPixelsNoiseVal": noise["webgl"]["readPixelsNoiseVal"],
                "extensions": None,
                "parameter": {
                    "SHADING_LANGUAGE_VERSION": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
                    "VERSION": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
                    "RENDERER": "WebKit WebGL",
                    "VENDOR": "WebKit",
                    "UNMASKED_VENDOR_WEBGL": gpu["vendor"],
                    "UNMASKED_RENDERER_WEBGL": gpu["renderer"],
                    "MAX_FRAGMENT_UNIFORM_VECTORS": 1024,
                    "MAX_3D_TEXTURE_SIZE": 2048,
                    "MAX_ARRAY_TEXTURE_LAYERS": 2048,
                    "MAX_COLOR_ATTACHMENTS": 8,
                    "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 32,
                    "MAX_COMBINED_UNIFORM_BLOCKS": 24,
                    "MAX_CUBE_MAP_TEXTURE_SIZE": 16384,
                    "MAX_DRAW_BUFFERS": 8,
                    "MAX_FRAGMENT_INPUT_COMPONENTS": 120,
                    "MAX_FRAGMENT_UNIFORM_BLOCKS": 12,
                    "MAX_PROGRAM_TEXEL_OFFSET": 7,
                    "MAX_RENDERBUFFER_SIZE": 16384,
                    "MAX_SAMPLES": gpu["maxSamples"],
                    "MAX_TEXTURE_IMAGE_UNITS": 16,
                    "MAX_TEXTURE_LOD_BIAS": 2.0,
                    "MAX_TEXTURE_SIZE": 16384,
                    "MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS": 120,
                    "MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS": 4,
                    "MAX_TRANSFORM_FEEDBACK_SEPARATE_COMPONENTS": 4,
                    "MAX_UNIFORM_BLOCK_SIZE": 65536,
                    "MAX_UNIFORM_BUFFER_BINDINGS": 24,
                    "MAX_VARYING_COMPONENTS": 120,
                    "MAX_VARYING_VECTORS": 30,
                    "MAX_VERTEX_ATTRIBS": 16,
                    "MAX_VERTEX_OUTPUT_COMPONENTS": 120,
                    "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 16,
                    "MAX_VERTEX_UNIFORM_BLOCKS": 12,
                    "MAX_VERTEX_UNIFORM_COMPONENTS": 16384,
                    "MAX_VERTEX_UNIFORM_VECTORS": 4096,
                    "MAX_FRAGMENT_UNIFORM_COMPONENTS": 4096,
                    "MIN_PROGRAM_TEXEL_OFFSET": -8,
                    "UNIFORM_BUFFER_OFFSET_ALIGNMENT": 256,
                    "MAX_COMBINED_VERTEX_UNIFORM_COMPONENTS": 212992,
                    "MAX_COMBINED_FRAGMENT_UNIFORM_COMPONENTS": 200704,
                    "MAX_VIEWPORT_DIMS": [32767, 32767],
                    "ALIASED_LINE_WIDTH_RANGE": [1.0, 1.0],
                    "ALIASED_POINT_SIZE_RANGE": [1.0, 1024.0],
                },
            },
            "advance": {
                "maxVertexUniform": float(random.choice([0, 4096, 4364])),
                "maxFragmentUniform": float(random.choice([0, 1024, 1030])),
            },
            "license": {
                "key": "",
                "machineId": "",
                "thirdparty_key": "",
            },
            "proxyAuth": {
                "autoAuth": bool(proxy_user),
                "username": proxy_user or "",
                "password": proxy_pass or "",
                "support_udp_associate": False,
                "bypass_extensions": "",
            },
            "brand": {
                "version": CHROME_VERSION,
            },
            "webRTC": {
                "mode": "fake" if proxy_info else "real",
                "publicIP": geo_info["ip"],
                "stun_server": "stun:stun.12voip.com:3478",
                "port_protect": "",
            },
            "geo_location": {
                "mode": "fake",
                "latitude": geo_info["lat"],
                "longitude": geo_info["lon"],
                "accuracy": 0.0,
                "add_small_random": False,
            },
            "password_config": {
                "show_prompt": True,
                "auto_save": False,
            },
            "extension": {
                "commandline_extension_load_with_store_extension": True,
            },
            "overlay_icon": {
                "short_title": str(random.randint(1, 9)),
                "background_color_hex": "#{:06x}".format(random.randint(0, 0xFFFFFF)),
                "force_color_hex": "#FFFFFF",
            },
            "fake_os": None,
        }
    }

    return config


def create_profile(proxy=None, automation=False):
    """Create profile directory, write config, and launch browser."""

    profile_id = str(uuid.uuid4())
    profile_path = os.path.join(PROFILE_BASE_DIR, profile_id)
    gpm_soft_path = os.path.join(profile_path, "Default", "GPMSoft")
    fonts_path = os.path.join(gpm_soft_path, "Fonts")
    exporter_path = os.path.join(gpm_soft_path, "Exporter")

    print(f"[*] Creating profile: {profile_id}")

    # 1. Lookup IP & geo
    geo = get_ip_info(proxy)

    # 2. Build config
    config = build_gpm_fg(geo, proxy)
    print(f"[*] GPU: {config['gpm']['webgl']['parameter']['UNMASKED_RENDERER_WEBGL']}")
    print(f"[*] CPU cores: {config['gpm']['navigator']['processorCount']}, "
          f"RAM: {config['gpm']['navigator']['deviceMemory']}GB")
    print(f"[*] Canvas token: {config['gpm']['canvas']['noiseToken']}")

    # 3. Create directories
    os.makedirs(fonts_path, exist_ok=True)
    os.makedirs(exporter_path, exist_ok=True)

    # 4. Copy fonts if available
    if os.path.isdir(FONT_SOURCE_DIR):
        import shutil
        for f in os.listdir(FONT_SOURCE_DIR):
            src = os.path.join(FONT_SOURCE_DIR, f)
            dst = os.path.join(fonts_path, f)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

    # 5. Write gpm_fg.dat (base64 encoded JSON)
    fg_json = json.dumps(config, ensure_ascii=False, indent=2)
    fg_b64 = base64.b64encode(fg_json.encode("utf-8")).decode("ascii")
    with open(os.path.join(gpm_soft_path, "gpm_fg.dat"), "w") as f:
        f.write(fg_b64)

    # 6. Write extension_dependencies.json
    with open(os.path.join(gpm_soft_path, "extension_dependencies.json"), "w") as f:
        f.write("[ ] ")

    # 7. Write minimal Local State & First Run
    with open(os.path.join(profile_path, "Local State"), "w") as f:
        f.write("{}")
    with open(os.path.join(profile_path, "First Run"), "w") as f:
        f.write("")

    print(f"[*] Profile written to: {profile_path}")

    # 8. Build launch command
    args = [
        CHROME_PATH,
        f'--user-data-dir={profile_path}',
        "--password-store=basic",
        "--gpm-disable-machine-id",
        "--no-default-browser-check",
        "--lang=vi",
    ]

    if proxy:
        proxy_host, proxy_port, _, _ = parse_proxy(proxy)
        args.append(f"--proxy-server={proxy_host}:{proxy_port}")

    if automation:
        debug_port = random.randint(50000, 65000)
        args.extend([
            f"--remote-debugging-port={debug_port}",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--metrics-recording-only",
            "--hide-crash-restore-bubble",
            "--no-first-run",
            "--disable-features=CalculateNativeWinOcclusion",
            "--turn-off-whats-new",
            "--disable-popup-blocking",
        ])
        print(f"[*] Automation CDP port: {debug_port}")

    # 9. Launch
    print(f"[*] Launching browser...")
    subprocess.Popen(args)

    print()
    print("=" * 60)
    print(f"  Profile ID : {profile_id}")
    print(f"  IP         : {geo['ip']}")
    print(f"  Location   : {geo.get('city', '')} ({geo['country_code']})")
    print(f"  Timezone   : {geo['timezone']}")
    if automation:
        print(f"  CDP Port   : {debug_port}")
        print(f"  Connect    : http://localhost:{debug_port}")
    print("=" * 60)

    return profile_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPM Login Profile Creator & Launcher")
    parser.add_argument("--proxy", "-p", type=str, default=None,
                        help="Proxy string: user:pass@host:port or host:port")
    parser.add_argument("--automation", "-a", action="store_true",
                        help="Enable CDP remote debugging for automation")
    args = parser.parse_args()

    create_profile(proxy=args.proxy, automation=args.automation)
