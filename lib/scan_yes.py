#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
from pathlib import Path
from time import sleep

def scan_segments(folder: str, output_json: str = "result.json"):
    """
    Quét toàn bộ file segment_{idx}.txt trong folder,
    nếu file có chứa 'Yes<a>' thì lưu idx vào mảng kết quả.
    """
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise NotADirectoryError(f"{folder} không phải là folder hợp lệ")

    pattern = re.compile(r"segment_(\d+)\.txt$")
    result = []

    for file in folder_path.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                idx = int(match.group(1))
                try:
                    with file.open("r", encoding="utf-8") as f:
                        content = f.read()
                        if "Yes<a>" in content:
                            result.append(idx)
                except Exception as e:
                    print(f"⚠️ Lỗi khi đọc {file}: {e}")

    result.sort()
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã lưu {len(result)} idx vào {output_json}")

def make_urls_from_result(result_file: str = "result.json", output_file: str = "url.json"):
    """
    Đọc idx từ result.json, tạo URL dạng:
    https://69shuba.com/book/{idx}/
    rồi lưu vào url.json
    """
    if not Path(result_file).exists():
        raise FileNotFoundError(f"{result_file} không tồn tại")

    with open(result_file, "r", encoding="utf-8") as f:
        idx_list = json.load(f)

    urls = [f"https://69shuba.com/book/{idx}/" for idx in idx_list]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã tạo {len(urls)} URL và lưu vào {output_file}")
if __name__ == "__main__":
    # Thay '.' bằng đường dẫn folder chứa các file txt
    while True:
        scan_segments(folder="first_chap_out")
        sleep(10*60)  # chờ 10 phút rồi quét lại
    #make_urls_from_result(result_file="result.json", output_file="url.json")
