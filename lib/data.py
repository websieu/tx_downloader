import os
import requests
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

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
