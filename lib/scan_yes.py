from pathlib import Path
import re
import time
from typing import List

def print_folders_over_yes_ratio_in_out(input_folder: str, yes_ratio: float = 0.6) -> List[str]:
    """
    Với mỗi thư mục con trong input_folder:
      - Quét folder con 'out' (input_folder/<child>/out)
      - Lọc file dạng segment_{idx}.txt (idx là số)
      - Đếm file chứa chuỗi 'YES' (phân biệt hoa/thường theo yêu cầu)
      - Nếu yes_count / total_files > yes_ratio => in ra tên <child>

    Trả về: danh sách tên thư mục đạt ngưỡng.
    """
    base = Path(input_folder)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {input_folder}")

    seg_pattern = re.compile(r"^segment_(\d+)\.txt$", re.IGNORECASE)

    passed = []
    for child in sorted(p for p in base.iterdir() if p.is_dir()):
        out_dir = child / "out"
        if not out_dir.is_dir():
            continue  # bỏ qua nếu không có thư mục out

        # Lấy các file hợp lệ: segment_{idx}.txt
        files = [f for f in out_dir.iterdir() if f.is_file() and seg_pattern.match(f.name)]
        if not files:
            continue  # không có file phù hợp thì bỏ qua

        total = 0
        yes_count = 0
        for f in files:
            total += 1
            try:
                with f.open("r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if "YES" in line:  # nếu muốn không phân biệt hoa/thường: if "yes" in line.lower():
                            yes_count += 1
                            break
            except Exception:
                # lỗi đọc file: coi như không có YES, tiếp tục file khác
                pass

        if total > 0 and (yes_count / total) > yes_ratio:
            print(child.name)
            passed.append(child.name)


    return passed

# Ví dụ dùng:
# print_folders_over_yes_ratio_in_out("/path/to/input_folder")
if __name__ == "__main__":
    while True:
        input_folder = "first_chap_out"
        yes_ratio = 0.5
        data = print_folders_over_yes_ratio_in_out(input_folder, yes_ratio)
        if len(data) == 0:
            print("No folder passed the threshold.")
        else:
            print(f"Total folders passed the threshold: {len(data)}")
        time.sleep(30)  # chờ 1 giờ rồi quét lại