from time import sleep
import os

from go_login_auto import start_fetch_book
from lib.firebase_db import FirestoreManager
from lib.telegram import send_telegram_message
from lib.upload_hg import upload_to_hg
from lib.utils import remove_folder


def main(fm: FirestoreManager):
    
    # service_account_path = "/root/bili_download/auth_files/filebase.json"
    
    # # Create an instance of FirestoreManager.
    # fm = FirestoreManager(service_account_path)
    channel = fm.select_channel_for_download()
    if not channel:
        print("No active channel found for download.")
        return None
    print(f"Selected channel for download: {channel['channel_username']}")
    # Update the last selected time for the channel.
    update_rs = fm.update_last_selected(channel['channel_username'])
    if not update_rs:
        print(f"Failed to update last selected for channel: {channel['channel_username']}")
        return None
    video = fm.fetch_current_processing_videos()
    if(video):
        print(f"Currently processing video found: {video['video_id']}")
        
    if not video:
        video = fm.select_video_by_channel_for_download(channel['channel_username'])
    if not video:
        print(f"No video found for channel: {channel['channel_username']}")
        return None
    else:
        print(f"Selected video for download: {video['video_id']} from channel: {channel['channel_username']}")

    update_rs = fm.update_video_for_process(video, status='downloading')
    if not update_rs:
        print(f"Failed to update video for processing: {video['video_id']}")
        return None
    else:
        print(f"Video {video['video_id']} is now marked as downloading.")
    
    os.makedirs(f"projects/{video['video_id']}", exist_ok=True)

    send_telegram_message(f"Downloading video {video['video_id']}")

    download_result = start_fetch_book(video['bili_link'])
    
    if not download_result:
        print(f"Failed to download video: {video['video_id']}")
        fm.update_video(video['video_id'], {"process_status": "failed"})
        send_telegram_message(f"Failed to download video: {video['video_id']}")
        return None
    else:
        send_telegram_message(f"Video {video['video_id']} downloaded successfully.")

    channel_dataset = channel['hg_dataset']
    upload = upload_to_hg(
        file_path=f"projects/{video['video_id']}/{video['video_id']}.txt",
        name_in_hg=f"{video['video_id']}.txt",
        repo_id=channel_dataset
    )
    if not upload:
        print(f"Failed to upload video {video['video_id']} to Hugging Face.")
        fm.update_video(video['video_id'], {"process_status": "failed"})
        return None
    else:
        print(f"Video {video['video_id']} uploaded successfully to Hugging Face: {upload}")
    
    fm.update_video(video['video_id'], {
        "process_status": "downloaded",
        "bili_link": upload,
        
    })
    send_message = f"Video {video['video_id']} downloaded and uploaded successfully to Hugging Face: {upload}"
    send_telegram_message(send_message)
    remove_folder(f"projects/{video['video_id']}")

def loop_firebase():
    service_account_path = "F:\\Code\\AI\\Auto-Youtube\\auth_files\\firebase.json"

    # Create an instance of FirestoreManager.
    #video_type = 'audio'
    fm = FirestoreManager(service_account_path)
    
    while(True):
        main(fm)
        sleep(5)

if __name__ == "__main__":
    loop_firebase()