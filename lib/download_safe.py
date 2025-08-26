import os, re, time, random
import httpx
from typing import Optional
from tqdm import tqdm

# (Tùy chọn) bật gửi telegram nếu bạn có sẵn hàm; nếu không thì để try/except
try:
    from lib.telegram import send_telegram_message
except Exception:
    def send_telegram_message(msg: str):
        pass

# Các mã HTTP nên retry (ngoài ra ta còn retry mọi Exception phía dưới)
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

def _parse_total_size(resp: httpx.Response, resume_from: int) -> Optional[int]:
    """
    Tính total size: ưu tiên Content-Range khi resume; fallback Content-Length.
    """
    cr = resp.headers.get("Content-Range")
    if cr:
        m = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", cr)
        if m and m.group(3).isdigit():
            return int(m.group(3))
    cl = resp.headers.get("Content-Length")
    return int(cl) + resume_from if cl and cl.isdigit() else None

def _safe_finalize(tmp_path: str, output_path: str):
    if os.path.exists(output_path):
        os.remove(output_path)
    os.replace(tmp_path, output_path)

def download_with_resume(
    url: str,
    output_path: str,
    referer: Optional[str] = None,
    cookie: Optional[str] = None,
    chunk_size: int = 1 << 20,        # 1 MiB
    max_retries: int = 8,
    backoff_base: float = 1.6,        # exponential backoff
    timeout_s: int = 60,
    verify_size: bool = True,
) -> bool:
    """
    Downloader có resume + retry mọi lỗi.
    - Giữ file .part để Range resume.
    - Retry mọi Exception (HTTP/2 stream reset, timeout, network…) + các mã HTTP retryable.
    - Nếu server không hỗ trợ Range (trả 200 khi đang resume) -> tự tải lại từ đầu.
    """
    tmp_path = output_path + ".part"
    desc_name = os.path.basename(output_path) or "download"

    base_headers = {
        "User-Agent": "Wget/1.21.4",
        "Accept": "*/*",
        "Accept-Encoding": "identity",  # tránh gzip để đếm byte chính xác
    }
    if referer:
        base_headers["Referer"] = referer
    if cookie:
        base_headers["Cookie"] = cookie

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            # Tính resume_from theo .part
            resume_from = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            mode = "ab" if resume_from > 0 else "wb"

            headers = dict(base_headers)
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            # Mở client và stream
            with httpx.Client(
                headers=headers,
                follow_redirects=True,
                http2=True,
                timeout=httpx.Timeout(timeout_s)
            ) as client:

                # Một số server không thích HEAD, nhưng nếu cần có thể thử:
                # - Nếu đang resume và HEAD trả 403 thì thử bỏ Range tải lại từ đầu
                if resume_from > 0:
                    try:
                        head = client.head(url)
                        if head.status_code == 403:
                            # Có thể bị chặn Range -> tải lại từ đầu
                            resume_from = 0
                            mode = "wb"
                            headers.pop("Range", None)
                    except Exception:
                        pass

                with client.stream("GET", url, headers=headers) as resp:
                    sc = resp.status_code

                    # 416: local offset lớn hơn server size -> xoá .part và tải lại
                    if sc == 416:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        resume_from = 0
                        mode = "wb"
                        raise httpx.HTTPStatusError("416 Range Not Satisfiable", request=resp.request, response=resp)

                    # Đang resume mà server trả 200 => không hỗ trợ Range -> tải lại từ đầu
                    if resume_from > 0 and sc == 200:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        resume_from = 0
                        mode = "wb"

                    # Lỗi HTTP có thể retry
                    if sc in RETRYABLE_STATUS or (sc not in (200, 206)):
                        raise httpx.HTTPStatusError(f"HTTP {sc}", request=resp.request, response=resp)

                    total = _parse_total_size(resp, resume_from)

                    with open(tmp_path, mode) as f, tqdm(
                        total=total if total else None,
                        initial=resume_from,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=desc_name,
                        smoothing=0.1,
                        miniters=1,
                        leave=True,
                    ) as pbar:
                        for chunk in resp.iter_bytes(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            f.write(chunk)
                            pbar.update(len(chunk))

            # Xác minh kích thước nếu biết total
            if verify_size and os.path.exists(tmp_path):
                final_size = os.path.getsize(tmp_path)
                # Nếu biết total mà thiếu byte => coi như lỗi để retry
                if_total = _guess_total_size(url, headers, final_size) if total is None else total
                if if_total is not None and final_size < if_total:
                    raise IOError(f"Incomplete download: {final_size}/{if_total} bytes")

            # Thành công -> đổi tên .part -> file đích
            _safe_finalize(tmp_path, output_path)
            return True

        except Exception as e:
            # Bắt TẤT CẢ lỗi: HTTP/2 StreamReset, timeout, network, IO, v.v…
            if attempt >= max_retries:
                msg = f"Download failed after {attempt} attempts: {e}"
                print(msg)
                try: send_telegram_message(msg)
                except Exception: pass
                return False

            # exponential backoff + jitter nhẹ
            sleep_s = (backoff_base ** (attempt - 1)) + random.uniform(0, 0.5)
            print(f"[Attempt {attempt}/{max_retries}] Error: {e} -> retry in {sleep_s:.1f}s (resume at next try)")
            send_telegram_message(f"[Attempt {attempt}/{max_retries}] Error: {e} -> retry in {sleep_s:.1f}s (resume at next try)")
            time.sleep(sleep_s)

    return False

def _guess_total_size(url: str, headers: dict, current_size: int) -> Optional[int]:
    """
    Khi response tải về không có total rõ ràng, thử hỏi server bằng GET Range cuối file
    để suy ra tổng dung lượng. Không bắt buộc, chỉ để tăng độ chắc chắn verify_size.
    """
    try:
        probe_headers = dict(headers)
        start = max(0, current_size - 1)
        probe_headers["Range"] = f"bytes={start}-"
        with httpx.Client(headers=probe_headers, follow_redirects=True, http2=True, timeout=15) as c:
            r = c.get(url, headers=probe_headers)
        cr = r.headers.get("Content-Range")  # ví dụ: "bytes 123-999/1000"
        if cr:
            m = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", cr)
            if m and m.group(3).isdigit():
                return int(m.group(3))
    except Exception:
        pass
    return None

if __name__ == "__main__":
    # Ví dụ dùng: nhớ dùng raw string cho Windows path
    url = ("http://upos-sz-mirrorcos.bilivideo.com/upgcxcode/12/26/30714692612/30714692612-1-160.mp4"
           "?e=ig8euxZM2rNcNbRVhwdVhwdlhWdVhwdVhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM="
           "&uipk=5&os=estgcos&platform=html5&trid=3812f63f59e64095aed55c4ee8fa409O&deadline=1756133112&oi=2067284620"
           "&nbs=1&gen=playurlv3&og=cos&mid=0&upsig=a7a7cb50ebbe739cb951abb5b7e95ab3&uparams=e,uipk,os,platform,trid,"
           "deadline,oi,nbs,gen,og,mid&bvc=vod&nettype=1&bw=416722&agrr=0&buvid=&build=7330300&dl=0&f=O_0_0&orderid=0,3")
    output_path = r"F:\Code\AI\Auto-Youtube\lib\sample-5s.mp4"
    # Nếu server yêu cầu Referer/Cookie, truyền thêm referer=..., cookie=...
    ok = download_with_resume(url, output_path, referer=None, cookie=None)
    print("Done:", ok)
