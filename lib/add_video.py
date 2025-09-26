import json
import re
from time import sleep
from typing import List, Union

from lib.firebase_db import FirestoreManager

# Giả sử save_to_db(link, channel_username, video_type) đã có sẵn trong cùng module
# from your_module import save_to_db

CHANNELS = ["bao_u_review", "tram_yeu"]

def _load_ids_from_json(json_path: str) -> List[str]:
    """
    Đọc file JSON và trả về danh sách video_id (chuỗi số).
    Hỗ trợ các dạng:
      - [123, 456, "789"]
      - {"ids": [...]}, {"result": [...]}, {"list": [...]}, {"indexes": [...]}, {"index": [...]}
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates: List[Union[str, int]] = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        for key in ["ids", "result", "list", "indexes", "index"]:
            if key in data and isinstance(data[key], list):
                candidates = data[key]
                break
        if not candidates:
            # Thử dạng {"id": 123} duy nhất
            if "id" in data and (isinstance(data["id"], (str, int))):
                candidates = [data["id"]]

    if not candidates:
        raise ValueError("Không tìm thấy mảng video_id hợp lệ trong JSON.")

    ids: List[str] = []
    for x in candidates:
        s = str(x).strip()
        # Chỉ nhận toàn chữ số
        if re.fullmatch(r"\d+", s):
            ids.append(s)
        else:
            # Nếu vô tình có lẫn text, cố gắng rút trích chuỗi số đầu tiên
            m = re.search(r"\d+", s)
            if m:
                ids.append(m.group(0))
            # nếu không có số, bỏ qua
    if not ids:
        raise ValueError("JSON không chứa video_id dạng số.")
    return ids


def add_videos_from_json(json_path: str, fm: FirestoreManager) -> None:
    """
    Đọc danh sách video_id từ JSON, rồi lần lượt gọi save_to_db.
    - link = https://69shuba.com/book/{video_id}
    - video_type = "text"
    - channel_username: luân phiên giữa 'bao_u_review' và 'tram_yeu'
      và CHỈ đổi kênh sau khi thêm thành công (save_to_db trả True).
    """
    ids = _load_ids_from_json(json_path)

    chan_idx = 0  # 0 -> bao_u_review, 1 -> tram_yeu
    total = len(ids)
    inserted = 0
    failed = 0
    skipped = 0

    for vid in ids:
        # đảm bảo là dãy số
        if not re.fullmatch(r"\d+", vid):
            skipped += 1
            print(f"⚠️  Bỏ qua '{vid}' (không phải số).")
            continue

        link = f"https://69shuba.com/book/{vid}"  # KHÔNG .htm để khớp regex /book/(\d+)/?
        channel_username = CHANNELS[chan_idx]

        ok = fm.add_text_video(video_id=vid, channel_username=channel_username, video_type="text")
        if ok:
            inserted += 1
            # chỉ đổi kênh khi thêm thành công
            chan_idx = 1 - chan_idx
            print(f"✅ Thêm video_id {vid} vào kênh '{channel_username}' thành công.")
        else:
            print(f"❌ Thêm video_id {vid} vào kênh '{channel_username}' thất bại.")
            failed += 1

    print("—— Kết quả ——")
    print(f"Tổng ID đọc được : {total}")
    print(f"Đã thêm thành công: {inserted}")
    print(f"Thất bại         : {failed}")
    print(f"Bỏ qua không hợp lệ: {skipped}")
    print(f"Kênh kế tiếp (nếu chạy tiếp): {CHANNELS[chan_idx]}")


if __name__ == "__main__":
    # Ví dụ chạy: python add_videos.py /path/to/ids.json
    service_account_path = "F:\\Code\\AI\\Auto-Youtube\\auth_files\\firebase.json"

    # Create an instance of FirestoreManager.
    fm = FirestoreManager(service_account_path)
    while True:
        add_videos_from_json("result.json", fm)
        sleep(30*60)  # chờ 10 phút rồi quét lại
