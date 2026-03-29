#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch translate .txt files named segment_{idx}.txt using DeepSeek API.
- Loads a system prompt from a text file
- Multithreaded for speed
- Retries with exponential backoff (max 3); skips file if still failing
- Writes output with the same filename to output folder ONLY on success

Usage:
    python translate_deepseek.py \
        --input_dir /path/to/input \
        --output_dir /path/to/output \
        --system_prompt /path/to/system_prompt.txt \
        --model deepseek-chat \
        --max_workers 8 \
        --timeout 60 \
        --endpoint https://api.deepseek.com/v1/chat/completions

Env:
    DEEPSEEK_API_KEY=<your_api_key>
"""

import os
import re
import json
import time
import math
import random
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Tuple
import concurrent.futures as cf

import requests

from lib.free_trans import split_and_save_segments

# -------------------- Config & Logging --------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

DEFAULT_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"  # override via --endpoint if bạn dùng endpoint khác
DEFAULT_MODEL = "deepseek-chat"  # thay theo model bạn dùng (vd: deepseek-chat, deepseek-reasoner, ...)
MAX_RETRIES = 3
API_KEY = 'sk-05eef9d6beac4471bd0b06310baccc26'

# -------------------- Helpers --------------------

def list_segment_files(input_dir: Path) -> List[Path]:
    """
    Return all files in input_dir that match segment_{idx}.txt (idx is a number).
    Sorted by numeric idx.
    """
    files = []
    pat = re.compile(r"segment_(\d+)\.txt$", re.IGNORECASE)
    for p in input_dir.glob("*.txt"):
        m = pat.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    files.sort(key=lambda t: t[0])
    return [p for _, p in files]


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def safe_write_text(path: Path, content: str) -> None:
    """
    Write via temp file then atomic move to avoid partial writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    # on Windows, replace silently by removing first if exists
    if path.exists():
        path.unlink()
    shutil.move(str(tmp), str(path))


def extract_content_from_response(resp_json: dict) -> Optional[str]:
    """
    Parse standard OpenAI-compatible chat completions response.
    Expected structure:
    {
      "choices": [
        {"message": {"content": "..."}}
      ],
      ...
    }
    """
    try:
        return resp_json["choices"][0]["message"]["content"]
    except Exception:
        return None


def backoff_sleep(retry_index: int, base: float = 1.5, cap: float = 20.0) -> None:
    """
    Exponential backoff with jitter.
    retry_index starts from 1.
    """
    # e.g., 1.5^retry with +/- 20% jitter, capped
    delay = min(cap, base ** retry_index)
    jitter = random.uniform(0.8, 1.2)
    time.sleep(delay * jitter)


# -------------------- DeepSeek API --------------------

def deepseek_chat(
    api_key: str,
    endpoint: str,
    model: str,
    system_prompt: str,
    user_text: str,
    timeout: int = 60,
    extra_headers: Optional[dict] = None
) -> Tuple[bool, str]:
    """
    Send a single chat completion request to DeepSeek API.
    Returns (success, content_or_error).
    - On success: (True, translated_text)
    - On failure: (False, error_message)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        # You can adjust these as needed:
        #"temperature": 1,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {e}"

    if r.status_code != 200:
        # Try to extract message from body for diagnostics
        try:
            body = r.json()
            msg = body.get("error", {}).get("message") or body
        except Exception:
            msg = r.text
        return False, f"HTTP {r.status_code}: {msg}"

    try:
        data = r.json()
    except Exception as e:
        return False, f"Invalid JSON response: {e}"

    content = extract_content_from_response(data)
    if content is None:
        # Fallback: return whole json if structure differs
        return False, f"Unexpected response format: {json.dumps(data)[:500]}"

    return True, content


def translate_with_retries(
    api_key: str,
    endpoint: str,
    model: str,
    system_prompt: str,
    user_text: str,
    timeout: int
) -> Tuple[bool, str]:
    """
    Try up to MAX_RETRIES times with backoff.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        ok, out = deepseek_chat(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            system_prompt=system_prompt,
            user_text=user_text,
            timeout=timeout,
        )
        if ok:
            return True, out

        logging.warning(f"Translate failed (attempt {attempt}/{MAX_RETRIES}): {out}")
        if attempt < MAX_RETRIES:
            backoff_sleep(attempt)
    return False, f"Failed after {MAX_RETRIES} attempts."


# -------------------- Worker --------------------

def process_file(
    api_key: str,
    endpoint: str,
    model: str,
    system_prompt: str,
    input_file: Path,
    output_dir: Path,
    timeout: int,
    skip_if_exists: bool
) -> Tuple[str, bool, str]:
    """
    Process one file:
    - Read input
    - Call DeepSeek with retries
    - Write output file only on success
    Returns (filename, success_bool, message)
    """
    output_path = output_dir / input_file.name
    if skip_if_exists and output_path.exists():
        return (input_file.name, True, "Skipped (exists)")

    try:
        user_text = load_text(input_file)
    except Exception as e:
        return (input_file.name, False, f"Read error: {e}")

    ok, result = translate_with_retries(
        api_key=api_key,
        endpoint=endpoint,
        model=model,
        system_prompt=system_prompt,
        user_text=user_text,
        timeout=timeout
    )

    if not ok:
        # Do NOT write output if failed
        return (input_file.name, False, result)

    try:
        safe_write_text(output_path, result)
    except Exception as e:
        return (input_file.name, False, f"Write error: {e}")

    return (input_file.name, True, "OK")


# -------------------- Main --------------------

def main(
    input_dir: str,
    output_dir: str,
    system_prompt_path: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    max_workers: int = 8,
    timeout: int = 180,
    skip_if_exists: bool = True,
):
    api_key = API_KEY
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable.")

    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    if not in_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {in_dir}")

    system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")

    files = list_segment_files(in_dir)
    if not files:
        logging.warning("No segment_{idx}.txt files found.")
        return

    logging.info(f"Found {len(files)} files. Starting with {max_workers} workers.")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    # Thread pool for I/O-bound / network-bound translation
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(
                process_file,
                api_key,
                endpoint,
                model,
                system_prompt,
                f,
                out_dir,
                timeout,
                skip_if_exists
            )
            for f in files
        ]

        for fut in cf.as_completed(futs):
            fname, ok, msg = fut.result()
            results.append((fname, ok, msg))
            if ok:
                logging.info(f"[OK] {fname}: {msg}")
            else:
                logging.error(f"[FAIL] {fname}: {msg}")

    # Summary
    total = len(results)
    ok_count = sum(1 for _, ok, _ in results if ok)
    fail_count = total - ok_count
    logging.info(f"Done. Success: {ok_count}/{total}. Fail: {fail_count}/{total}.")

    # Optional: write a small report JSON next to output_dir
    report = {
        "total": total,
        "success": ok_count,
        "failed": fail_count,
        "details": [{"file": f, "ok": ok, "msg": m} for f, ok, m in results],
    }
    report_path = Path(output_dir) / "_report.json"
    try:
        safe_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
        logging.info(f"Wrote report: {report_path}")
    except Exception as e:
        logging.warning(f"Could not write report: {e}")


if __name__ == "__main__":

    # input_dir = 'F:\\Code\\AI\\Auto-Youtube\\first_chap'
    # output_dir = 'F:\\Code\\AI\\Auto-Youtube\\first_chap_out'
    while True:
        split_and_save_segments(Path("first_chap"), Path("first_chap_out"))
        system_prompt = 'F:\\Code\\AI\\Auto-Youtube\\templates\\check_quality.txt'

        scan_dir = sorted(Path("first_chap_out").iterdir())
        print(f"Found {len(scan_dir)} folders in first_chap_out")
        total_dir = 0
        for folder in scan_dir:
            if folder.is_dir():
                total_dir += 1
                input_dir = folder
                output_dir = folder / "out"
                print(f"\n=== Processing folder: {input_dir} ===")
                main(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    system_prompt_path=system_prompt)
                
                print(f"=== Finished folder: {input_dir} ===\n")

        print(f"Found {total_dir} folders in first_chap_out")
        time.sleep(5*60)
