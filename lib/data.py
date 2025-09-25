import os
import requests
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
import unicodedata
import re

from lib.download_safe import download_with_resume
from lib.telegram import send_telegram_message
def download_zip(url, output_path):
    """
    Download a ZIP file from the given URL and save it to output_path.
    """
    # Stream download in case the file is large.
    if(os.path.exists(output_path)):
        print(f"File already exists: {output_path}")
        return True
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
            print(f"Downloaded file saved to: {output_path}")
            return True
        else:
            print(f"Failed to download file. Status code: {response.status_code}")
    except Exception as e:
        print(f"download false {e}")
        return False
    
def download_with_wget(
    url: str,
    output_path: str,
    *,
    retries: int = 3,
    connect_timeout: int = 15,
    read_timeout: int = 60,
    continue_download: bool = True,
    user_agent: str | None = "Mozilla/5.0",
    cookies_file: str | None = None,
    verify_cert: bool = True,
    show_output: bool = False,
) -> Path:
    """
    Download a URL using the system 'wget' command.

    - output_path can be a file path OR a directory path.
    - Raises CalledProcessError on failure.
    - Returns the final Path of the downloaded file.
    """
    if shutil.which("wget") is None:
        raise RuntimeError("wget is not installed or not on PATH.")

    out = Path(output_path)

    # If output_path is a directory (or ends with a path separator), save using the URL's filename.
    if output_path.endswith(("/", "\\")) or out.is_dir():
        # Try to get a sensible filename from the URL path
        url_name = os.path.basename(urlsplit(url).path) or "downloaded.file"
        out = out / url_name

    out.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "wget",
        f"--tries={retries}",
        f"--timeout={connect_timeout}",
        f"--read-timeout={read_timeout}",
        "--no-verbose",
        "-O", str(out),
    ]
    if continue_download:
        args.append("-c")
    if user_agent:
        args += ["--user-agent", user_agent]
    if cookies_file:
        args += ["--load-cookies", cookies_file]
    if not verify_cert:
        args.append("--no-check-certificate")

    # URL goes last
    args.append(url)

    # Run wget
    result = subprocess.run(
        args,
        text=True,
        capture_output=not show_output,
        check=False,
    )
    if result.returncode != 0:
        return False
    return out


def title_to_slug(title: str, max_length: int = 40) -> str:
    # 1. Normalize to NFKD and strip accents
    normalized = unicodedata.normalize('NFKD', title)
    ascii_str = normalized.encode('ASCII', 'ignore').decode('ASCII')
    # 2. Lowercase
    lower_str = ascii_str.lower()
    # 3. Replace non-alphanumeric sequences with underscores
    slug = re.sub(r'[^a-z0-9]+', '_', lower_str).strip('_')
    # 4. Truncate to max_length
    truncated = slug[:max_length]
    # 5. If original slug was longer, add ellipsis
    if len(slug) > max_length:
        truncated += ''
    return truncated

# if __name__ == '__main__':
#     title = "Thay đổi vận | mệnh tình yêu thời | cấp hai nhờ bí ẩn mật khẩu 0101!"
#     print(title_to_slug(title))
#     # → toi_yeu_em_tu_cai_nh...


def download_project_for_upload(video, project_path="project_upload"):

    video_id = video['video_id']
    upload_status = video['upload_status']
    if(upload_status == "not_uploaded"):
        part_1_link = video['part_1_link']
        if(part_1_link != ''):
            mp4_link = part_1_link
        else:
            mp4_link = video['hg_link']
    else:
        mp4_link = video['part_2_link']
    
    thumb_link = video['thumb_link']
    mp4_link = mp4_link.replace("blob/main", "resolve/main")
    if(thumb_link):
        thumb_link = thumb_link.replace("blob/main", "resolve/main")

    title = video['title']
    file_name = title_to_slug(title)
   
    extract_dir = f"{project_path}/{video_id}"
    mp4_path = f"{extract_dir}/{file_name}.mp4"

    first_part = video_id.split('_', 1)[0]

    thumb_path = f"{extract_dir}/{first_part}.jpg"

    if not os.path.exists(extract_dir):
        os.makedirs(extract_dir, exist_ok=True)
    print(f"Downloading video to {mp4_path} ...")
    print(f"Downloading thumb to {thumb_path} ...")
    send_telegram_message(f"Downloading video to {mp4_path} ...")
    if(not os.path.exists(mp4_path)):
        data_down = download_with_resume(mp4_link, mp4_path)
        #data_down = download_zip(mp4_link, mp4_path)
        if(not data_down):
            return False
        
    if(not os.path.exists(thumb_path) and thumb_link):
        data_down = download_with_resume(thumb_link, thumb_path)
        #data_down = download_zip(thumb_link, thumb_path)
        # if(not data_down):
        #     return False
    return True
