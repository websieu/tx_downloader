import subprocess
from decimal import Decimal, ROUND_HALF_UP

def _run(cmd: list) -> str:
    return subprocess.run(
        cmd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout.strip()

def get_duration_hhmmss(path: str) -> str:
    """
    Trả về thời lượng video dạng 'hh:mm:ss'.
    Yêu cầu: đã cài ffmpeg/ffprobe và có trong PATH.
    """
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])
    # Làm tròn đến giây gần nhất (half-up). Nếu muốn luôn làm tròn xuống, thay bằng int(float(out)).
    try:
        total_seconds = int(Decimal(out).quantize(0, rounding=ROUND_HALF_UP))
    except Exception as e:
        return False

    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# Ví dụ chạy trực tiếp: python script.py /path/to/video.mp4
if __name__ == "__main__":
    video_path = "F:\\Code\\AI\\Auto-Youtube\\output_videos\\27955_short_0.mp4"
    print(get_duration_hhmmss(video_path))
