"""
This script demonstrates how to interact with the VBEE text‑to‑speech (TTS) API.  It
performs three main tasks:

1. **Send a POST request** to the VBEE TTS endpoint to create an audio file from text.
2. **Poll the request status** using a GET request until the audio generation is
   complete.  When finished, the API returns the `audio_link` where the generated
   audio can be downloaded.
3. **Download the resulting audio** and save it into an `output` directory.

The API requires an authentication token and an application ID.  These must be
obtained from VBEE and supplied either via environment variables or by
modifying the constants defined in this script.  Without valid credentials the
requests will fail with a 401/403 error.

API details such as the endpoints and response format are documented in the
public VBEE TTS API manual.  According to the documentation, the POST request
is sent to `https://vbee.vn/api/v1/tts` and returns a `request_id`.  The
generation status and audio link can then be retrieved by calling
`GET https://vbee.vn/api/v1/tts/{request_id}`【822574005071356†screenshot】.

Note:  The example values provided in this script (e.g. `VOICE_CODE` and
`CALLBACK_URL`) are placeholders.  Replace them with the appropriate values
for your application.
"""

import os
import time
from pathlib import Path
from typing import Optional

import requests


# -----------------------------------------------------------------------------
# Configuration
#
# Replace these constants with your own VBEE credentials and settings.  For
# security, you can also define the token and app ID as environment variables
# (`VBEE_TOKEN` and `VBEE_APP_ID`) instead of editing the script directly.
#

# Bearer token provided by VBEE for authenticating API requests.
TOKEN: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTQyMDEwMjJ9.87D3UtqDvqrzkJ12s9oL3sdXu2HSoeIq15y4HWGVR24"

# Application ID issued by VBEE when you register your application.
APP_ID: str = "93b691ae-3b49-40ea-910e-3b5f8f6f0bc9"

# Optional: URL where VBEE should send a callback when the audio is ready.  If
# your environment does not have a publicly accessible endpoint, you can leave
# this as a placeholder.  The callback is only used when `response_type`
# is "indirect"; otherwise VBEE will not attempt to invoke it.
CALLBACK_URL: str = os.environ.get(
    "VBEE_CALLBACK_URL", "https://example.com/callback"
)

# Voice code specifying which voice should read the text.  See the VBEE
# documentation for the list of available voices (e.g. "hn_female_ngochuyen_full_48k-fhg").
VOICE_CODE: str = os.environ.get(
    "VBEE_VOICE_CODE", "hn_female_ngochuyen_full_48k-fhg"
)

# Desired audio format; VBEE supports "mp3" and "wav".  The file extension
# will be chosen based on this value.
AUDIO_TYPE: str = os.environ.get("VBEE_AUDIO_TYPE", "wav")


# -----------------------------------------------------------------------------
# Helper functions

def create_tts_request(
    text: str,
    voice_code: str = VOICE_CODE,
    audio_type: str = AUDIO_TYPE,
    callback_url: str = CALLBACK_URL,
    bitrate: int = 128,
    speed_rate: float = 1.0,
) -> str:
    """Submit a text‑to‑speech request to the VBEE API and return the request ID.

    Args:
        text: The text to synthesise into speech.
        voice_code: The VBEE voice code to use for synthesis.
        audio_type: Desired output format ("mp3" or "wav").
        callback_url: A public URL for VBEE to send a callback once the audio
            is ready.  This is required when using `response_type` "indirect".
        bitrate: Bitrate (kbps) for the generated audio.
        speed_rate: Reading speed.  A value of 1.0 is normal speed.

    Returns:
        The `request_id` provided by VBEE to track the synthesis job.

    Raises:
        RuntimeError: If the API call fails or returns an unexpected response.
    """
    url = "https://vbee.vn/api/v1/tts"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "app_id": APP_ID,
        # According to the documentation, the response_type must be "indirect"
        # when a callback is used.  VBEE will return immediately with a
        # request_id and process the job asynchronously.
        "response_type": "indirect",
        "callback_url": callback_url,
        "input_text": text,
        "voice_code": voice_code,
        "audio_type": audio_type,
        "bitrate": bitrate,
        "speed_rate": str(speed_rate),
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    try:
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"TTS request failed: {exc}\nResponse: {resp.text}")
    data = resp.json()
    # Check top‑level status (1 = success, 0 = error)
    if data.get("status") != 1:
        raise RuntimeError(
            f"TTS API error: {data.get('error_message')} (code={data.get('error_code')})"
        )
    result = data.get("result", {})
    request_id = result.get("request_id")
    if not request_id:
        raise RuntimeError(f"Missing request_id in response: {data}")
    return request_id


def poll_request_status(request_id: str, interval: float = 2.0) -> Optional[str]:
    """Poll VBEE's GET request endpoint until the audio is ready and return the link.

    Args:
        request_id: The identifier returned from `create_tts_request`.
        interval: Number of seconds to wait between polls.

    Returns:
        The URL of the generated audio file if the job succeeds, or None
        if the job fails or times out.
    """
    url = f"https://vbee.vn/api/v1/tts/{request_id}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    for attempt in range(60):  # Poll up to ~2 minutes
        resp = requests.get(url, headers=headers, timeout=30)
        try:
            resp.raise_for_status()
        except Exception:
            # If the request fails (e.g. 404 or 401), wait and retry.
            time.sleep(interval)
            continue
        data = resp.json()
        if data.get("status") != 1:
            # Non‑success status; you might want to handle errors differently
            return None
        result = data.get("result", {})
        status = result.get("status")
        # The API uses "IN_PROGRESS" until synthesis is complete, then "SUCCESS".
        if status == "SUCCESS":
            audio_link = result.get("audio_link")
            if audio_link:
                return audio_link
            else:
                # The API sometimes returns the audio link under "result_url"
                # depending on the version; handle both cases.
                return result.get("result_url")
        # Otherwise, wait and try again.
        time.sleep(interval)
    return None


def download_audio(url: str, output_dir: Path) -> Path:
    """Download an audio file from `url` and save it into `output_dir`.

    Args:
        url: The direct link to the audio file as returned by the VBEE API.
        output_dir: Directory where the audio file will be stored.

    Returns:
        The path to the saved audio file.

    Raises:
        RuntimeError: If the download fails or the server returns a non‑200 status.
    """
    # Determine the file extension from the URL (defaults to .mp3).
    filename = url.split("?")[0].split("/")[-1]  # strip query parameters
    if not filename:
        filename = "tts_output.wav"

    filename = filename if filename.endswith(f".{AUDIO_TYPE}") else f"{filename}.{AUDIO_TYPE}"
    output_dir.mkdir(parents=True, exist_ok=True)
    dest_path = output_dir / filename
    with requests.get(url, stream=True, timeout=60) as r:
        try:
            r.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Failed to download audio: {exc}\nResponse: {r.text}")
        with dest_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return dest_path


def main() -> None:
    """High‑level orchestration for creating, polling, and downloading TTS audio."""
    # Example text to synthesise.  Replace with your own content.
    sample_text = (
        "Ngày đó, tôi còn là một đứa trẻ, ngây thơ và trong sáng.  Tôi"
        " đã mơ về những cuộc phiêu lưu kỳ thú, những chuyến đi xa"
        
    )
    # Submit TTS request
    print("Submitting TTS request...")
    request_id = create_tts_request(sample_text)
    print(f"Request submitted. Request ID: {request_id}")
    # Poll for completion
    print("Polling request status...")
    audio_link = poll_request_status(request_id)
    if not audio_link:
        raise RuntimeError("Audio generation failed or timed out.")
    print(f"Audio ready. Download link: {audio_link}")
    # Download and save audio
    output_dir = Path("./output")
    saved_path = download_audio(audio_link, output_dir)
    print(f"Audio file saved to {saved_path}")


if __name__ == "__main__":
    # Guard against missing credentials
    if not TOKEN or TOKEN == "YOUR_TOKEN_HERE" or not APP_ID or APP_ID == "YOUR_APP_ID_HERE":
        print(
            "Warning: VBEE_TOKEN and VBEE_APP_ID must be set as environment variables "
            "or edited in the script before running.  The request will likely fail."
        )
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")