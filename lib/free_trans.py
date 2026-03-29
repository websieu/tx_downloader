#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate_segments_threaded.py
- Đa luồng: mỗi thread giữ 1 key, lấy job từ queue.
- 2 task:
    * trans: dịch sang tiếng Việt; nếu có --name-folder sẽ nạp danh sách tên (file trùng tên).
             Nếu output còn >= 4 ký tự tiếng Trung:
                 - retry cùng key tối đa 3 lần (sleep 10s giữa các lần)
                 - nếu vẫn còn >= 4 ký tự sau 3 lần -> VẪN GHI FILE, KHÔNG đổi key, log cảnh báo và tiếp tục.
    * get_name: trích xuất tên nhân vật (không cần name-folder).
- 429: sleep 20s, retry <= 3; nếu vẫn 429 -> disable key, xin key khác và thử lại chính job.
- Sau mỗi job thành công: sleep 8s (có thể chỉnh).
- Skip output đã tồn tại, progress bar, in key khi 429, in [DONE]/[FAIL].

Yêu cầu: pip install requests
"""

import random
import os, sys, re, math, time, threading, queue, argparse
from pathlib import Path
from dataclasses import dataclass, field
import traceback
from typing import List, Optional, Tuple
import requests

# from Utils.telegram import send_telegram_message
# from lib.txt.sync_name import check_name_error_content

#MODEL_PRIMARY = "gemini-2.5-flash"
MODEL_PRIMARY = "gemma-3-27b-it"
MODEL_FALLBACK = "gemini-2.5-flash-lite"
MODEL_GEMMA = "gemma-3-27b-it"


def endpoint_for_model(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


FILE_PATTERN = re.compile(r"segment_(\d+)\.txt$", re.IGNORECASE)

TASK_TRANS = "trans"
TASK_GET_NAME = "get_name"
TASK_NORMALIZE = "normalize"

# Ngưỡng ký tự tiếng Trung để coi như cần retry
CHINESE_THRESHOLD = 4

# ------------ Utils ------------
def list_segment_files(in_dir: Path) -> List[Path]:
    items: List[Path] = []
    for p in in_dir.glob("*.txt"):
        if FILE_PATTERN.match(p.name):
            items.append(p)
    items.sort(key=lambda x: int(FILE_PATTERN.match(x.name).group(1)))  # type: ignore
    return items

def load_keys(keys_file: Optional[Path], keys_env: Optional[str] = None) -> List[str]:
    keys: List[str] = []
    if keys_file and keys_file.exists():
        for line in keys_file.read_text(encoding="utf-8").splitlines():
            k = line.strip()
            if k:
                keys.append(k)
    if keys_env:
        for k in keys_env.split(","):
            k = k.strip()
            if k:
                keys.append(k)
    keys = list(dict.fromkeys(keys))
    random.SystemRandom().shuffle(keys)
    return keys

# Đếm ký tự tiếng Trung (CJK Ideographs)
def count_chinese_chars(s: str) -> int:
    cnt = 0
    for ch in s:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF   # CJK Unified Ideographs
            or 0x3400 <= cp <= 0x4DBF  # CJK Ext A
            or 0x20000 <= cp <= 0x2A6DF  # CJK Ext B
            or 0x2A700 <= cp <= 0x2B73F  # CJK Ext C
            or 0x2B740 <= cp <= 0x2B81F  # CJK Ext D
            or 0x2B820 <= cp <= 0x2CEAF  # CJK Ext E
            or 0xF900 <= cp <= 0xFAFF    # CJK Compatibility Ideographs
            or 0x2F800 <= cp <= 0x2FA1F  # CJK Compatibility Ideographs Supplement
        ):
            cnt += 1
    return cnt

# ------------ Payload builders ------------
def build_payload_trans(text: str, system_prompt: Optional[str], names_text: Optional[str], current_model: str) -> dict:
    guide = ""
    if names_text and names_text.strip():
        name_content = names_text.strip()
        name_content = name_content.replace("<cn>","")
        name_content = name_content.replace("</cn>","")
        name_content = name_content.replace("<vi>","")
        name_content = name_content.replace("</vi>","")
        name_content = name_content.replace("```","")
        name_content = name_content.replace("*","")
        guide = (
            "Dịch tên nhân vật dựa vào bảng sau:\n\n"
            f"{name_content}\n"
            "------------------------\n\n"
        )
    user_prompt = (
        
        "---- Nội dung văn bản cần dịch ----\n"
        f"{text}"
        f"{guide}"
    )
    if "gemma" in current_model:
        if system_prompt:
            user_prompt = system_prompt + "\n\n" + user_prompt


        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }
        return payload
    
    payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }

    if system_prompt:
        payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_prompt}]}
    return payload

def build_payload_get_name(text: str, system_prompt: Optional[str], current_model: str) -> dict:
    user_prompt = (
        
        f"{text}"
    )
    if "gemma" in current_model:
        if system_prompt:
            user_prompt = system_prompt + "\n\n" + user_prompt

        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }
        return payload
    else:
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }
        if system_prompt:
            payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_prompt}]}
        return payload

def build_payload(task: str, text: str, system_prompt: Optional[str], names_text: Optional[str], current_model: str) -> dict:
    if task == TASK_TRANS:
        return build_payload_trans(text, system_prompt, names_text, current_model)
    else:
        return build_payload_get_name(text, system_prompt, current_model)

def extract_text_from_gemini(resp_json: dict):
    try:
        for c in resp_json.get("candidates") or []:
            for p in (c.get("content") or {}).get("parts") or []:
                if isinstance(p.get("text"), str):
                    return p["text"]
    except Exception as e:
        print(f"❌ Lỗi khi trích xuất văn bản từ Gemini: {e}")
        traceback.print_exc()
        print(f"Response JSON: {resp_json}")
    return False

# ------------ Progress ------------
@dataclass
class Progress:
    total: int
    completed: int = 0
    start_time: float = field(default_factory=time.time)

def _fmt_eta(seconds: float) -> str:
    if seconds <= 0 or math.isinf(seconds) or math.isnan(seconds):
        return "00:00"
    m, s = divmod(int(seconds), 60); h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def print_bar(pg: Progress):
    width = 30
    done, total = pg.completed, max(1, pg.total)
    frac = min(1.0, done / total)
    filled = int(frac * width)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = max(1e-6, time.time() - pg.start_time)
    rate = done / elapsed
    remain = total - done
    eta = remain / rate if rate > 0 else 0
    # if done % 10 == 0 and done > 0:
    #     send_telegram_message(f"Đang dịch... {done}/{total} ETA {_fmt_eta(eta)}")
    sys.stdout.write(f"\r[{bar}] {done}/{total} ({frac*100:.1f}%)  ETA {_fmt_eta(eta)}")
    sys.stdout.flush()

# ------------ Key pool ------------
class KeyPool:
    def __init__(self, keys: List[str]):
        self._avail = queue.Queue()
        for k in keys:
            self._avail.put(k)
        self._dead = set()
        self._lock = threading.Lock()

    def get_key(self, block=True, timeout=None) -> Optional[str]:
        try:
            return self._avail.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def disable_key(self, key: str):
        with self._lock:
            self._dead.add(key)

    def return_key(self, key: str):
        with self._lock:
            if key in self._dead:
                return
        self._avail.put(key)

# ------------ HTTP sync ------------
# ------------ HTTP sync ------------
def translate_with_key_sync(session: requests.Session, key: str, payload: dict, model: str):
    
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    url = endpoint_for_model(model)
    resp = session.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code >= 400:
        raise requests.HTTPError(resp.text, response=resp)
    return extract_text_from_gemini(resp.json())

# ------------ Worker ------------
def worker_thread(key_pool: KeyPool,
                  job_queue: "queue.Queue[Tuple[Path, Path]]",
                  system_prompt: Optional[str],
                  task: str,
                  name_folder: Optional[Path],
                  pg: Progress,
                  print_lock: threading.Lock,
                  per_job_sleep: float = 8.0):
    session = requests.Session()
    key = key_pool.get_key(block=False)
    if key is None:
        return

    while True:
        try:
            infile, outfile = job_queue.get_nowait()
        except queue.Empty:
            key_pool.return_key(key)
            return

        text = infile.read_text(encoding="utf-8", errors="ignore")

        # Nạp danh sách tên nếu task=trans
        names_text = None
        if task == TASK_TRANS and name_folder:
            name_file = name_folder / infile.name
            if name_file.exists() and name_file.is_file():
                try:
                    names_text = name_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    names_text = None
            else:
                with print_lock:
                    print(f"\n[WARN] Không thấy file tên cho {infile.name} trong {name_folder}")
        current_model = MODEL_PRIMARY
        # if task == TASK_GET_NAME:
        #     current_model = MODEL_FALLBACK  # get_name dùng model nhẹ hơn

        # Giữ job đến khi xong (có thể đổi key trong các trường hợp lỗi 429/NET)
        while True:
            try_count = 0
            while True:
                try:
                    payload = build_payload(task, text, system_prompt, names_text, current_model)
                    
                    vi = translate_with_key_sync(session, key, payload, current_model)
                    if not vi:
                        try_count += 1
                        with print_lock:
                            print(f"\n[RETRY_CN] key={key} file={infile.name}  (retry {try_count}/3)")
                        if try_count < 3:
                            time.sleep(10.0)
                            continue

                    # ✅ Kiểm tra chất lượng riêng cho task=trans:
                    if task == TASK_TRANS:
                        cn = count_chinese_chars(vi)
                        if cn >= CHINESE_THRESHOLD:
                            try_count += 1
                            with print_lock:
                                print(f"\n[RETRY_CN] key={key} file={infile.name} chinese_chars={cn} (retry {try_count}/3)")
                            if try_count < 3:
                                time.sleep(10.0)
                                continue
                            # Sau 3 lần vẫn còn nhiều ký tự Trung -> KHÔNG đổi key, vẫn ghi file & tiếp tục
                            outfile.parent.mkdir(parents=True, exist_ok=True)
                            outfile.write_text(vi, encoding="utf-8")
                            time.sleep(per_job_sleep)
                            with print_lock:
                                pg.completed += 1
                                print(f"\n[DONE_WARN_CN] {infile.name} (key={key[:8]}…, cn={cn}≥{CHINESE_THRESHOLD})")
                                print_bar(pg)
                            job_queue.task_done()
                            break  # xong job (chấp nhận tạm), sang file khác
                    if task == TASK_GET_NAME:
                        check = False
                        if check:
                            try_count += 1
                            with print_lock:
                                print(f"\n[RETRY_NAME] key={key} file={infile.name}  (retry {try_count}/3)")
                            if try_count < 3:
                                time.sleep(5.0)
                                continue
                            # Sau 3 lần vẫn còn nhiều ký tự Trung -> KHÔNG đổi key, vẫn ghi file & tiếp tục
                            outfile.parent.mkdir(parents=True, exist_ok=True)
                            outfile.write_text(vi, encoding="utf-8")
                            time.sleep(per_job_sleep)
                            with print_lock:
                                pg.completed += 1
                                print(f"\n[DONE_WARN_CN] {infile.name} (key={key[:8]}… )")
                                print_bar(pg)
                            job_queue.task_done()
                            break  # xong job (chấp nhận tạm), sang file khác         
                    # Nếu đạt chuẩn (hoặc task=get_name): ghi file bình thường
                    outfile.parent.mkdir(parents=True, exist_ok=True)
                    
                    if vi:
                        outfile.write_text(vi, encoding="utf-8")
                        
                        with print_lock:
                            pg.completed += 1
                            print(f"\n[DONE] {infile.name} (key={key[:8]}…, task={task})")
                            print_bar(pg)
                    else:
                        with print_lock:
                            pg.completed += 1
                            print(f"\n[FAIL_EMPTY] {infile.name} (key={key[:8]}…, task={task})")
                            print_bar(pg)
                    time.sleep(per_job_sleep)
                    job_queue.task_done()
                    break  # xong job -> lấy job mới

                except requests.HTTPError as err:
                    resp = getattr(err, "response", None)
                    status = resp.status_code if resp is not None else -1
                    msg = str(err)[:200]
                    if status == 429:
                        try_count += 1
                        with print_lock:
                            print(f"\n[429] key={key} file={infile.name} (retry {try_count}/3) msg={msg}")
                        if try_count < 3:
                            time.sleep(20.0)
                            continue
                        else:
                            with print_lock:
                                print(f"[DISABLE] key={key} do 429 liên tục. Chuyển sang key khác.")
                            key_pool.disable_key(key)
                            new_key = key_pool.get_key(block=False)
                            if new_key is None:
                                with print_lock:
                                    print(f"[FAIL] {infile.name} (hết key khả dụng)")
                                    pg.completed += 1
                                    print_bar(pg)
                                job_queue.task_done()
                                return
                            key = new_key
                            continue
                    else:
                        if current_model != MODEL_FALLBACK:
                            with print_lock:
                                print(f"\n[FALLBACK_MODEL] key={key} file={infile.name} status={status} → đổi model {MODEL_PRIMARY} → {MODEL_FALLBACK}")
                            current_model = MODEL_FALLBACK
                            time.sleep(5.0)
                            continue

                        try_count += 1
                        if try_count < 3:
                            time.sleep(10.0)
                            continue
                        with print_lock:
                            print(f"\n[FAIL_ERR] {infile.name} (key={key[:8]}…, model={current_model}, status={status}) msg={msg}")
                            pg.completed += 1
                            print_bar(pg)
                        job_queue.task_done()
                        break  # bỏ file này, tiếp file khác

                except (requests.ConnectionError, requests.Timeout) as e:
                    try_count += 1
                    if try_count < 3:
                        time.sleep(10.0)
                        continue
                    with print_lock:
                        print(f"\n[NET_FAIL] {infile.name} (key={key[:8]}…, model={current_model}) err={type(e).__name__}")
                        pg.completed += 1
                        print_bar(pg)
                    job_queue.task_done()
                    break
            break  # job done


SEGMENT_RE = re.compile(r"segment_(\d+)\.txt$", re.IGNORECASE)
def get_segment_number(filename: str) -> int:
    match = SEGMENT_RE.match(filename)
    if not match:
        raise ValueError(f"Filename does not match pattern: {filename}")
    return int(match.group(1))
# ------------ Orchestrator ------------
def run_translate(
    input_dir: Path,
    output_dir: Path,
    keys_file: Optional[Path] = Path("auth_files/keys.txt"),
    keys_env: Optional[str] = None,
    system_prompt_file: Optional[Path] = None,
    name_folder: Optional[Path] = None,
    task: str = TASK_TRANS,
    max_workers: Optional[int] = None,
    start_segment: int = 0,
    end_segment: int = 99999,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    keys = load_keys(keys_file, keys_env or os.getenv("GOOGLE_API_KEYS"))
    if not keys:
        print("⚠️ Chưa có API key."); return
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input folder không tồn tại: {input_dir}"); return
    if task == TASK_TRANS and name_folder is None:
        print("ℹ️ Task 'trans' đang chạy KHÔNG có --name-folder; vẫn dịch nhưng thiếu danh sách tên.")

    system_prompt = None
    if system_prompt_file:
        if not system_prompt_file.exists():
            print(f"⚠️ System prompt file không tồn tại: {system_prompt_file}")
            return
        system_prompt = system_prompt_file.read_text(encoding="utf-8")

    # Build job queue (skip nếu out tồn tại & >0 byte)
    files = list_segment_files(input_dir)
    job_q: "queue.Queue[Tuple[Path, Path]]" = queue.Queue()
    skipped = 0
    for fp in files:
        outp = output_dir / fp.name
        if outp.exists() and outp.stat().st_size > 0:
            skipped += 1
            continue
        if get_segment_number(fp.name) < start_segment or get_segment_number(fp.name) > end_segment:
            skipped += 1
            continue
        job_q.put((fp, outp))
    total_jobs = job_q.qsize()
    if total_jobs == 0:
        print(f"Không có file cần xử lý. (Skip sẵn có: {skipped})"); return
    print(f"Skip sẵn có: {skipped}, Cần xử lý: {total_jobs}, Task: {task}")

    # Key pool & progress
    pool = KeyPool(keys)
    pg = Progress(total=total_jobs)
    print_lock = threading.Lock()
    with print_lock:
        print_bar(pg)

    # Worker threads
    n_workers = max_workers if max_workers is not None else len(keys)
    n_workers = max(1, min(n_workers, len(keys)))  # mỗi thread gắn 1 key
    threads: List[threading.Thread] = []
    for _ in range(n_workers):
        t = threading.Thread(
            target=worker_thread,
            args=(pool, job_q, system_prompt, task, name_folder, pg, print_lock),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Chờ xong
    for t in threads:
        t.join()

    with print_lock:
        sys.stdout.write("\n")

### fix name and fix trans inline ###

# ======================= [ADD] Helpers cho fix_name =======================

# Regex cặp tên <cn>…</cn> - <vi>…</vi>
PAIR_RE = re.compile(r'<cn>\s*(.*?)\s*</cn>\s*[-–—]\s*<vi>\s*(.*?)\s*</vi>', re.IGNORECASE | re.DOTALL)

def has_chinese(s: str) -> bool:
    return count_chinese_chars(s) > 0

def build_payload_fix_one_name(cn_name: str, system_prompt: Optional[str], task: str) -> dict:
    if task == "fix_name":
        user_prompt = f"Dịch tên sau sang tiếng Việt, không giải thích gì thêm.\n\n{cn_name.strip()}"
    else:
        user_prompt = (
             f"Bạn là nhà dịch thuật chuyên nghiệp.\n"
            f"Tôi có một văn bản tiếng Trung, hãy tìm từ tiếng Trung còn sót trong văn bản và thay thế bằng tiếng Việt sao cho hợp lý.\n"

            f"Văn bản đã sửa không được phép có ký tự tiếng Trung.\n"
            f"Nội dung phản hồi là văn bản đã thay thế từ và không giải thích gì thêm.\n\n"
             f"{cn_name.strip()}"
        )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.0},
    }
    if system_prompt:
        payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_prompt}]}
    return payload

# ======================= [ADD] Worker cho fix_name =======================

def worker_thread_fix_name_files(key_pool: KeyPool,
                                 job_queue: "queue.Queue[Path]",
                                 system_prompt: Optional[str],
                                 pg: Progress,
                                 print_lock: threading.Lock,
                                 task: str,
                                 per_name_sleep: float = 5.0):
    """
    Mỗi thread giữ 1 key, xử lý từng file tên:
    - Dò các dòng có cặp <cn>…</cn> - <vi>…</vi>
    - Nếu <vi> còn ký tự Trung -> dịch lại từ <cn> (PRIMARY -> fallback nếu cần)
    - Chỉ đổi key khi 429
    - Ghi đè file in-place khi có thay đổi
    """
    session = requests.Session()
    key = key_pool.get_key(block=False)
    if key is None:
        return

    while True:
        try:
            infile = job_queue.get_nowait()
        except queue.Empty:
            key_pool.return_key(key)
            return

        try:
            lines = infile.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        except Exception as e:
            with print_lock:
                print(f"\n[READ_ERR] {infile.name}: {e}")
                pg.completed += 1
                print_bar(pg)
            job_queue.task_done()
            continue

        updated = False
        out_lines = []

        for line in lines:
            if task == "fix_name":
                m = PAIR_RE.search(line)
                if not m:
                    out_lines.append(line)
                    continue

                cn, vi = m.group(1), m.group(2)
                if not has_chinese(vi):
                    out_lines.append(line)
                    continue
            else:
                if not has_chinese(line):
                    out_lines.append(line)
                    continue
                cn = line.strip()

            current_model = MODEL_PRIMARY
            http_try = 0

            while True:
                try:
                    payload = build_payload_fix_one_name(cn, system_prompt, task)
                    with print_lock:
                        print(f"\n🔄 Translating: {cn.strip()}  (key={key[:8]}…, model={current_model}, file={infile.name})")
                    translated = translate_with_key_sync(session, key, payload, current_model).strip()
                    if not translated:
                        http_try += 1
                        with print_lock:
                            print(f"\n[RETRY_CN] key={key} file={infile.name} chinese_chars={cn} (retry {http_try}/3)")
                        if http_try < 3:
                            time.sleep(10.0)
                            continue
                    translated = translated.replace("\n", " ").strip()
                    if task == "fix_name":
                        new_line = f"<cn> {cn} </cn> - <vi> {translated} </vi>\n"
                    else:
                        new_line = f"{translated}\n"
                    out_lines.append(new_line)
                    updated = True

                    with print_lock:
                        print(f"✅ translated: {translated}")
                    time.sleep(per_name_sleep)
                    break

                except requests.HTTPError as err:
                    resp = getattr(err, "response", None)
                    status = resp.status_code if resp is not None else -1
                    msg = str(err)[:200]

                    if status == 429:
                        http_try += 1
                        with print_lock:
                            print(f"\n[429] key={key} file={infile.name} (retry {http_try}/3) msg={msg}")
                        if http_try < 3:
                            time.sleep(20.0)
                            continue
                        with print_lock:
                            print(f"[DISABLE] key={key} do 429 liên tục. Chuyển sang key khác.")
                        key_pool.disable_key(key)
                        new_key = key_pool.get_key(block=False)
                        if new_key is None:
                            with print_lock:
                                print(f"[NAME_FAIL] {infile.name}: Hết key; giữ dòng cũ.")
                            out_lines.append(line)
                            break
                        key = new_key
                        continue

                    else:
                        # non-429 → fallback model (một lần), sau đó retry ≤3
                        if current_model != MODEL_FALLBACK:
                            with print_lock:
                                print(f"\n[FALLBACK_MODEL] key={key} file={infile.name} status={status} → {MODEL_FALLBACK}")
                            current_model = MODEL_FALLBACK
                            http_try = 0
                            time.sleep(3.0)
                            continue

                        http_try += 1
                        if http_try < 3:
                            time.sleep(10.0)
                            continue

                        with print_lock:
                            print(f"[NAME_FAIL_NON429] {infile.name} status={status} -> giữ dòng cũ.")
                        out_lines.append(line)
                        break

                except (requests.ConnectionError, requests.Timeout) as e:
                    http_try += 1
                    with print_lock:
                        print(f"\n[NET] key={key} file={infile.name} err={type(e).__name__} (retry {http_try}/3)")
                    if http_try < 3:
                        time.sleep(10.0)
                        continue
                    with print_lock:
                        print(f"[NAME_FAIL_NET] {infile.name} -> giữ dòng cũ.")
                    out_lines.append(line)
                    break

        # Ghi file (in-place) nếu có thay đổi
        try:
            if updated:
                infile.write_text("".join(out_lines), encoding="utf-8")
                with print_lock:
                    print(f"\n[FIXED] {infile.name}")
            else:
                with print_lock:
                    print(f"\n[SKIP]  {infile.name} (không cần sửa)")
        except Exception as e:
            with print_lock:
                print(f"\n[WRITE_ERR] {infile.name}: {e}")

        with print_lock:
            pg.completed += 1
            print_bar(pg)
        job_queue.task_done()

# ======================= [ADD] Orchestrator cho fix_name =======================

def run_fix_name_folder(
    name_folder: Path,
    task: str,
    keys_file: Optional[Path] = Path("auth_files/keys.txt"),
    keys_env: Optional[str] = None,
    system_prompt_file: Optional[Path] = None,
    max_workers: Optional[int] = None,
    
    start_segment: int = 0,
    end_segment: int = 99999,
):
    """
    Quét folder chứa file tên (segment_{idx}.txt), tìm dòng có <vi> còn ký tự Trung và dịch lại từ <cn>.
    - Không đụng chạm run_translate / worker_thread hiện có.
    - Dựa trên KeyPool, progress bar, và logic 429/fallback như đã xài.
    """
    keys = load_keys(keys_file, keys_env or os.getenv("GOOGLE_API_KEYS"))
    if not keys:
        print("⚠️ Chưa có API key."); return
    if not name_folder.exists() or not name_folder.is_dir():
        print(f"Folder không tồn tại: {name_folder}"); return

    system_prompt = None
    if system_prompt_file:
        if not system_prompt_file.exists():
            print(f"⚠️ System prompt file không tồn tại: {system_prompt_file}")
            return
        system_prompt = system_prompt_file.read_text(encoding="utf-8")

    files = list_segment_files(name_folder)
    if not files:
        print("Không có file tên (segment_{idx}.txt) để quét."); return

    job_q: "queue.Queue[Path]" = queue.Queue()
    for fp in files:
        if get_segment_number(fp.name) < start_segment or get_segment_number(fp.name) > end_segment:
            continue
        job_q.put(fp)

    total = job_q.qsize()
    print(f"Cần quét/sửa: {total} file tên (fix_name)")

    pool = KeyPool(keys)
    pg = Progress(total=total)
    print_lock = threading.Lock()
    with print_lock:
        print_bar(pg)

    n_workers = max_workers if max_workers is not None else len(keys)
    n_workers = max(1, min(n_workers, len(keys)))

    threads: List[threading.Thread] = []
    for _ in range(n_workers):
        t = threading.Thread(
            target=worker_thread_fix_name_files,
            args=(pool, job_q, system_prompt, pg, print_lock, task),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    with print_lock:
        sys.stdout.write("\n")



# ------------ CLI ------------
def parse_args():
    ap = argparse.ArgumentParser(description="Multithreaded Gemini translate/name-extract with CN retry (no key switch after 3 CN retries).")
    ap.add_argument("--task", choices=[TASK_TRANS, TASK_GET_NAME], default=TASK_TRANS,
                    help="trans: dịch + dùng danh sách tên từ --name-folder; get_name: trích xuất tên.")
    ap.add_argument("--input", "-i", type=Path, required=True, help="Thư mục input có segment_{idx}.txt")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Thư mục output")
    ap.add_argument("--name-folder", type=Path, default=None, help="Thư mục chứa danh sách tên (file trùng tên). Dùng cho task=trans.")
    ap.add_argument("--keys-file", type=Path, default=Path("auth_files/keys.txt"))
    ap.add_argument("--keys-env", type=str, default=None)
    ap.add_argument("--system-prompt-file", type=Path, default=None)
    ap.add_argument("--max-workers", type=int, default=None, help="Số thread chạy song song; mặc định = số key.")
    return ap.parse_args()

def split_and_save_segments(input_folder: Path, output_folder: Path):
        files = list_segment_files(input_folder)
        for fp in files:
            idx = get_segment_number(fp.name)
            out_dir = output_folder / str(idx)
            out_dir.mkdir(parents=True, exist_ok=True)
            text = fp.read_text(encoding="utf-8", errors="ignore")
            parts = [part.strip() for part in text.split('<end-chap>') if part.strip()]
            for i, part in enumerate(parts):
                out_file = out_dir / f"segment_{i}.txt"
                out_file.write_text(part, encoding="utf-8")

if __name__ == "__main__":
    
    # Yêu cầu: scan toàn bộ file segment_{idx}.txt trong input folder,
    # split theo '<end-chapter>', lưu vào output_folder/idx/segment_{idx}.txt

    

    # Ví dụ sử dụng:
    split_and_save_segments(Path("first_chap"), Path("first_chap_out"))
    print("=== Finished splitting chapters into segments ===")

    # for folder in sorted(Path("first_chap_out").iterdir()):
    #     if folder.is_dir():
    #         input_dir = folder
    #         output_dir = folder / "out"
    #         print(f"\n=== Processing folder: {input_dir} ===")
    #         run_translate(
    #             input_dir=input_dir,
    #             output_dir=output_dir,
    #             keys_file=Path("auth_files/keys.txt"),
    #             keys_env=None,
    #             system_prompt_file=Path('templates/check_quality.txt'),
    #             name_folder=None,
    #             task=TASK_NORMALIZE,
    #             max_workers=6,
    #         )
    #         time.sleep(20)
    #         print(f"=== Finished folder: {input_dir} ===\n")
#    while True:
#     run_translate(
#         input_dir=Path('first_chap'),
#         output_dir=Path('first_chap_out'),
#         keys_file=Path("auth_files/keys.txt"),
#         keys_env=None,
#         system_prompt_file=Path("templates/check_quality.txt"),
#         name_folder=Path('first_chap'),
#         task=TASK_NORMALIZE,
#         max_workers=6,
#     )
    #time.sleep(10*60)  # chờ 30 phút rồi dịch lại

    # run_fix_name_folder(
    #     name_folder=Path('/root/wan/output/output_trans'),
    #     task="fix_trans",
    #     keys_file=Path("auth_files/keys.txt"),
    #     keys_env=None,
    #     system_prompt_file=None,
    #     max_workers=5,
    # )
