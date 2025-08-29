import os
import json
import re
import shutil
import urllib.parse as up

def get_config_value(config_name: str, config_path: str = 'config.json') -> str:
    """
    Get config value from environment. If not set or empty, load from config file and export all to env.
    Raise an error if value still not found after loading.
    
    Args:
        config_name (str): The key to get from the environment.
        config_path (str): Path to the JSON config file.
    
    Returns:
        str: The value of the config variable.
    
    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If the config value is not found even after loading.
    """
    value = os.environ.get(config_name)
    if value:
        return value

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    print("need to read file")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        for key, val in config.items():
            os.environ[key] = str(val)

    # Try to read again
    value = os.environ.get(config_name)
    if not value:
        raise KeyError(f"Config key '{config_name}' not found in environment or in config file.")
    
    return value

BOT_TOKEN = get_config_value("telegram_bot_token")
CHAT_ID = get_config_value("telegram_chat_id")
GEMINI_API = get_config_value("gemini_api")
CHATGPT_API = get_config_value("chat_gpt_api")
MAX_SCENE_DURATION = int(get_config_value("max_scene_duration"))
PROXY = get_config_value("proxy")
DEEPSEEK_API = get_config_value("deepseek_api")
MODEL_SCOPE_TOKEN = get_config_value("model_scope_token")
LIST_CHANNEL = get_config_value("list_channel")
TRANS_MODEL = get_config_value("trans_model")
VIDEO_TYPE = get_config_value("video_type")
SYNC_DURATION = int(get_config_value("sync_duration"))
LEONARDO_API = get_config_value("leonardo_api")
GO_LOGIN_TOKEN = get_config_value("go_login_token")
REMOTE_PORT = int(get_config_value("remote_port"))
GL_PROFILE = get_config_value("gl_profile")
def get_video_id(url: str) -> str:
    """
    Lấy ID video BiliBili kèm số phần (p).
    
    Ví dụ
    -------
    >>> get_video_id("https://www.bilibili.com/video/BV1EK4y1b7B1?p=3")
    'BV1EK4y1b7B1_3'
    >>> get_video_id("https://www.bilibili.com/video/BV1EK4y1b7B1")
    'BV1EK4y1b7B1_1'
    """
    # ‣ Phân tách URL một lần để dùng cho cả ID & query
    parsed = up.urlparse(url)
    
    # ‣ Lấy video ID (BV… hoặc av…)
    m = re.search(r'(BV\w+|av\d+)', parsed.path)
    if m:
        vid = m.group(1)
    else:
        # fallback: lấy segment cuối của path (bỏ / và query)
        vid = parsed.path.rstrip('/').split('/')[-1] or 'unknown'
    
    # ‣ Lấy tham số p (page index), mặc định 1
    qs = up.parse_qs(parsed.query)
    p = qs.get('p', ['1'])[0] or '1'
    
    return f'{vid}_{p}'


def get_book_id(url: str) -> str:
    """
    Extract book ID from the given URL.
    
    Args:
        url (str): The URL to extract the book ID from.
    
    Returns:
        str: The extracted book ID, or an empty string if not found.
    """
    m = re.search(r'/book/(\d+)', url)
    return m.group(1) if m else ""

def remove_folder(path: str):
    """
    Remove a folder and all its contents.
    """
    if not os.path.exists(path):
        print(f"Error: '{path}' does not exist.")
        return
    if not os.path.isdir(path):
        print(f"Error: '{path}' is not a directory.")
        return

    try:
        shutil.rmtree(path)
        print(f"Removed folder and all contents: {path}")
    except Exception as e:
        print(f"Failed to remove '{path}': {e}")


if __name__ == "__main__":

    data = get_book_id("https://www.69shuba.com/book/85454/")
    print(data)  # Should print "85454"
