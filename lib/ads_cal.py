import re
from typing import List

def _parse_hhmmss_strict(s: str) -> int:
    """
    Parse chuỗi hh:mm:ss thành tổng số giây. Chỉ chấp nhận đúng 3 phần.
    """
    parts = s.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"duration phải là hh:mm:ss, nhận: {s!r}")
    h, m, sec = parts
    h, m, sec = int(h), int(m), int(sec)
    if not (0 <= m < 60 and 0 <= sec < 60):
        raise ValueError("mm và ss phải trong [0,59].")
    return h * 3600 + m * 60 + sec

def _parse_period(s: str) -> int:
    """
    Parse chu kỳ quảng cáo:
      - Dạng có ':' → hh:mm:ss | mm:ss | ss
      - Dạng ký hiệu: '1h', '30m', '45s', '1h30m15s' (có thể kết hợp)
    Trả về tổng số giây (int), phải > 0.
    """
    s = s.strip().lower()
    if not s:
        raise ValueError("ads_period rỗng.")

    # Dạng có dấu ':'
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = map(int, parts)
            if not (0 <= m < 60 and 0 <= sec < 60):
                raise ValueError("mm và ss phải trong [0,59].")
            total = h * 3600 + m * 60 + sec
        elif len(parts) == 2:
            m, sec = map(int, parts)
            if not (0 <= sec < 60):
                raise ValueError("ss phải trong [0,59].")
            total = m * 60 + sec
        elif len(parts) == 1:
            total = int(parts[0])
        else:
            raise ValueError(f"ads_period không hợp lệ: {s!r}")
        if total <= 0:
            raise ValueError("ads_period phải > 0.")
        return total

    # Dạng ký hiệu h/m/s có thể kết hợp
    matches = re.findall(r"(\d+)\s*([hms])", s)
    if not matches:
        # Nếu chỉ là số thuần → coi là giây
        if s.isdigit():
            val = int(s)
            if val <= 0:
                raise ValueError("ads_period phải > 0.")
            return val
        raise ValueError(f"ads_period không hợp lệ: {s!r}")

    total = 0
    for num, unit in matches:
        v = int(num)
        if unit == "h":
            total += v * 3600
        elif unit == "m":
            total += v * 60
        elif unit == "s":
            total += v
    if total <= 0:
        raise ValueError("ads_period phải > 0.")
    return total

def _format_timecode(total_seconds: int) -> str:
    """Định dạng thành h:mm:ss:ff (ff=00, giờ không zero-pad, mm/ss pad 2)."""
    h = total_seconds // 3600
    rem = total_seconds % 3600
    m = rem // 60
    s = rem % 60
    return f"{h}:{m:02d}:{s:02d}:00"

def compute_ad_timestamps(duration_hhmmss: str, ads_period: str) -> List[str]:
    """
    Trả về danh sách timecode chèn quảng cáo từ 0 đến hết video (≤ duration),
    cách nhau bởi ads_period.

    Ví dụ:
      compute_ad_timestamps("02:30:00", "1h")
      → ["0:00:00:00", "1:00:00:00", "2:00:00:00"]
    """
    duration_sec = _parse_hhmmss_strict(duration_hhmmss)
    period_sec = _parse_period(ads_period)

    if period_sec <= 0:
        raise ValueError("ads_period phải > 0.")
    if duration_sec < 0:
        raise ValueError("duration không hợp lệ.")

    times = []
    t = 0
    while t <= duration_sec:
        times.append(_format_timecode(t))
        t += period_sec
    return times

if __name__ == "__main__":
    # Ví dụ sử dụng
    duration = "120:30:00"
    ads_period = "00:30:00"
    timestamps = compute_ad_timestamps(duration, ads_period)
    print(timestamps)
    # → ['0:00:00:00', '1:00:00:00', '2:00:00:00']