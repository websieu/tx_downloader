# download_and_merge_hf_videos.py
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import shutil
import requests
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm


def convert_to_direct_url(url: str) -> str:
    # /blob/ -> /resolve/ + ?download=1 để lấy file gốc
    direct = url.replace("/blob/", "/resolve/")
    if "?" not in direct:
        direct += "?download=1"
    return direct


def make_session():
    retries = Retry(
        total=5, connect=5, read=5, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "hf-downloader/1.0"})
    return s


def filename_from_template(base_url: str, idx: int) -> str:
    formatted = base_url.format(idx=idx)
    path = urlparse(formatted).path
    return os.path.basename(path)


def download_one(session: requests.Session, url_template: str, idx: int, out_dir: str, skip_existing: bool = True) -> str:
    filename = filename_from_template(url_template, idx)
    out_path = os.path.join(out_dir, filename)
    if skip_existing and os.path.exists(out_path):
        return f"[SKIP] {filename} đã tồn tại."

    web_url = url_template.format(idx=idx)
    direct_url = convert_to_direct_url(web_url)

    with session.get(direct_url, stream=True, timeout=(10, 120)) as r:
        if r.status_code == 404:
            return f"[404] Không tìm thấy: {filename}"
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        tmp_path = out_path + ".part"

        with open(tmp_path, "wb") as f, tqdm(
            total=total if total > 0 else None,
            unit="B", unit_scale=True, desc=filename, leave=False,
        ) as pbar:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    if total > 0:
                        pbar.update(len(chunk))

        os.replace(tmp_path, out_path)
        return f"[OK] {filename}"


def _quote_for_ffconcat(p: str) -> str:
    # ffmpeg concat list: dùng forward-slash cho cross-platform, và quote bằng single quote
    p2 = p.replace("\\", "/")
    return "'" + p2.replace("'", r"'\''") + "'"


def build_concat_list(file_paths, list_path: str):
    with open(list_path, "w", encoding="utf-8") as f:
        for p in file_paths:
            f.write(f"file {_quote_for_ffconcat(p)}\n")


def merge_videos_ffmpeg(file_paths, output_path: str, mode: str = "copy"):
    """
    mode='copy'    : concat demuxer + stream copy (nhanh, không re-encode)
    mode='reencode': concat demuxer + re-encode (an toàn khi codec/params khác nhau)
    """
    if not file_paths:
        raise RuntimeError("Không có file nào để merge.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    list_txt = os.path.join(os.path.dirname(os.path.abspath(output_path)), "concat_list.txt")
    build_concat_list(file_paths, list_txt)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Không tìm thấy ffmpeg trong PATH. Vui lòng cài đặt ffmpeg.")

    base_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_txt,
        "-movflags", "+faststart",
    ]

    if mode == "copy":
        cmd = base_cmd + ["-fflags", "+genpts", "-c", "copy", output_path]
    elif mode == "reencode":
        # Re-encode để đảm bảo tương thích khi copy fail
        cmd = base_cmd + [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
    else:
        raise ValueError("concat mode không hợp lệ. Dùng 'copy' hoặc 'reencode'.")

    print(">> Merging videos with FFmpeg...")
    try:
        # In stderr để xem tiến trình/ cảnh báo ffmpeg
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        print(proc.stdout[-1000:])  # in phần cuối log cho gọn
    except subprocess.CalledProcessError as e:
        tail = e.stdout[-2000:] if e.stdout else ""
        raise RuntimeError(f"FFmpeg merge thất bại (mode={mode}). Log cuối:\n{tail}") from e
    finally:
        # Không xóa concat_list để bạn xem lại; muốn auto-xóa thì mở comment dòng dưới.
        # try: os.remove(list_txt); except: pass
        pass


def main():
    ap = argparse.ArgumentParser(description="Download Hugging Face videos (idx 0..N) và merge thành 1 file.")
    ap.add_argument("--base-url", required=True,
                    help="VD: https://huggingface.co/datasets/raymondt/bao_u_review/blob/main/27955_short_{idx}.mp4")
    ap.add_argument("--out", required=True, help="Thư mục lưu video tải về.")
    ap.add_argument("--start", type=int, default=0, help="Idx bắt đầu (mặc định 0).")
    ap.add_argument("--end", type=int, default=20, help="Idx kết thúc (mặc định 20, bao gồm).")
    ap.add_argument("--workers", type=int, default=4, help="Số luồng tải song song (mặc định 4).")
    ap.add_argument("--no-skip", action="store_true", help="Không bỏ qua file đã tồn tại.")
    ap.add_argument("--merge-out", default="merged_output.mp4", help="Đường dẫn file MP4 sau khi merge.")
    ap.add_argument("--concat-mode", choices=["copy", "reencode"], default="copy",
                    help="Cách merge: 'copy' (nhanh, không re-encode) hoặc 'reencode' (an toàn).")
    ap.add_argument("--only-merge", action="store_true",
                    help="Chỉ merge các file đã có sẵn trong --out, bỏ qua bước download.")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # 1) Download (nếu không --only-merge)
    if not args.only_merge:
        session = make_session()
        futures = []
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i in range(args.start, args.end + 1):
                futures.append(
                    ex.submit(
                        download_one, session, args.base_url, i, args.out, not args.no_skip
                    )
                )
            for fut in as_completed(futures):
                try:
                    print(fut.result())
                except Exception as e:
                    print(f"[ERR] {e}")

    # 2) Thu thập file theo thứ tự idx tăng dần và merge
    file_paths = []
    for i in range(args.start, args.end + 1):
        name = filename_from_template(args.base_url, i)
        p = os.path.join(args.out, name)
        if os.path.exists(p):
            file_paths.append(p)
        else:
            print(f"[WARN] Thiếu file: {name}")

    if not file_paths:
        print("Không tìm thấy file hợp lệ để merge.")
        return

    # Bảo đảm đúng thứ tự
    file_paths.sort(key=lambda x: int(os.path.splitext(os.path.basename(x))[0].split("_")[-1]) 
                    if "_" in os.path.basename(x) else 0)

    merge_videos_ffmpeg(file_paths, args.merge_out, mode=args.concat_mode)
    print(f">> Merge xong: {args.merge_out}")


if __name__ == "__main__":
    main()

"""
python download_video.py  --base-url "https://huggingface.co/datasets/raymondt/bao_u_review/blob/main/27955_short_{idx}.mp4" --out ./output_videos  --start 0 --end 9  --merge-out merged_27955.mp4 --concat-mode copy

"""