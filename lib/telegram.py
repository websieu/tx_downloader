import requests

from lib.utils import BOT_TOKEN, CHAT_ID

# Define your constants for the bot token and chat ID
# BOT_TOKEN = '8131431318:AAH5hyyHhLhg_Io-bj28zCdTSXrReE4SmGg'
# CHAT_ID = '-1002564836359'

def send_video_telegram(video_path):
    """
    Sends a video to a Telegram chat using the Telegram Bot API.
    
    Args:
        video_path (str): The path to the video file.
        
    Returns:
        dict: The JSON response from the Telegram API if successful.
        None: If the video failed to send.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, data=data, files=files)
        
        if response.ok:
            print("Video sent successfully!")
            return response.json()
        else:
            print("Failed to send video.")
            print(response.text)
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def send_telegram_message(message: str):
    try:
        """Send a message to a Telegram chat using a bot."""
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": message}

        response = requests.get(url, params=params)
        return response.json()  # Return API response for debugging
    except Exception as e:
        print(e)

def send_image_telegram(image_path: str):
    """
    Sends a PNG image to a Telegram chat using the Telegram Bot API.

    Args:
        image_path (str): The path to the PNG image file.

    Returns:
        dict: The JSON response from the Telegram API if successful.
        None: If the image failed to send.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    try:
        with open(image_path, 'rb') as img_file:
            files = {'photo': img_file}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, data=data, files=files)

        if response.ok:
            print("Image sent successfully!")
            return response.json()
        else:
            print("Failed to send image.")
            print(response.text)
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# # Example usage:
# if __name__ == "__main__":
#     video_path_input = '/root/wan/animate_out/video-Scene-0003.mp4'
#     result = send_video(video_path_input)
#     if result:
#         print(result)
