#!/usr/bin/env python3
"""
YouTube Upload Scheduler

This script determines the next available upload slot for a YouTube channel by querying
the YouTube API for the latest video (including scheduled uploads). Upload slots are fixed
daily at 12:00 and 20:00 in UTC+7. The script computes the next available slot based on the 
effective publish time of the latest video and schedules a new upload accordingly.
"""

import os
import datetime
import shutil
import traceback
from zoneinfo import ZoneInfo

import dateutil.parser
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from firebase_admin import credentials, firestore

from go_login_auto import upload_ytb_browser
from lib.data import download_project_for_upload, title_to_slug
from lib.firebase_db import FirestoreManager
from lib.telegram import send_telegram_message
from lib.write_text_img import write_text_on_image




CLIENT_SECRETS_FILE = "auth_files/client_sec.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube"
]


class UploadSchedulerFirebase:
    def __init__(self, fm: FirestoreManager):
        # Define the daily upload slots in local time (UTC+7)
        self.slot_times = [(12, 0), (20, 0)]
        self.local_tz = ZoneInfo("Asia/Bangkok")
        self.fm = fm
        self.project_path = "project_upload"
        # self.project_name = project_name
       
        # self.channel_id = channel_id
        # self.channel_config = channel_config
    def fetch_video(self):
            video = self.fm.select_video_for_upload()
            if(not video):
                print("not found video for upload")
                return None
            return video
    def fetch_channel(self, video):
        channel_username = video['channel_username']
        video_id = video['video_id']
        channel = self.fm.select_channel_by_id(channel_username)
        if(not channel):
            print(f"not found channel {channel_username}")
            return None
        if(channel["status"] != "active"):
            print(f"channel is not activate {channel_username}")
            #self.fm.update_video(video_id, update_data={"time_completed": firestore.SERVER_TIMESTAMP})
            return None
        # if( 'money' in channel and channel['money']):
        #     return channel
        
        if(not self.fm.is_last_upload_older_than_3_hours(channel)):
            print("channel need to wait to upload...")
            #self.fm.update_video(video_id, update_data={"time_completed": firestore.SERVER_TIMESTAMP})
            return None
        return channel
    
    def get_data_to_upload(self):
        video = self.fetch_video()
        if(not video):
            return None
        channel = self.fetch_channel(video)
        if(not channel):
            print("not found channel to process...")
            return None
        data_download = download_project_for_upload(video, self.project_path)
        if(not data_download):
            print("cannot download video data")
            return None
        send_telegram_message(f"download data upload for project {video['video_id']}")
        self.channel_id = channel['channel_username']
        self.project_name = video['video_id']
        self.channel_config = channel
        
        self.video = video
        return True
        
    
    def get_authenticated_service(self, token_file):
        try:
            if os.path.exists(token_file):
                creds = google.oauth2.credentials.Credentials.from_authorized_user_file(token_file, SCOPES)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
            else:
                raise FileNotFoundError(f"Token file {token_file} not found. Please generate it using get_token.py")
            return build("youtube", "v3", credentials=creds)
        except Exception as e:
            print(f"Cannot get auth service: {e}")
            return None

    def get_latest_video_time(self):
        """
        Fetch the most recent video (public or scheduled) from your channel by:
          - Retrieving the channel's uploads playlist.
          - Fetching a batch of videos and sorting by effective publish time.
        
        Effective publish time is:
          - status.publishAt for scheduled videos (if available)
          - snippet.publishedAt for public videos
        
        Returns a tuple (video_data, effective_publish_time) where effective_publish_time is a datetime in UTC+7.
        """
        token_file = f"auth_files/{self.channel_id}.json"
        youtube = self.get_authenticated_service(token_file)
        if not youtube:
            return None, None

        # Retrieve the channel's uploads playlist ID.
        channels_response = youtube.channels().list(
            part="contentDetails",
            mine=True
        ).execute()
        items = channels_response.get("items", [])
        if not items:
            raise Exception("No channel found for the authenticated user.")
        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Retrieve a batch of videos from the uploads playlist.
        playlist_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50
        ).execute()
        playlist_items = playlist_response.get("items", [])
        if not playlist_items:
            return None, None

        # Extract video IDs.
        video_ids = [
            item["snippet"]["resourceId"]["videoId"]
            for item in playlist_items if "resourceId" in item["snippet"]
        ]
        if not video_ids:
            return None, None

        # Retrieve full video details including status.
        videos_response = youtube.videos().list(
            part="snippet,status",
            id=",".join(video_ids)
        ).execute()
        videos = videos_response.get("items", [])
        if not videos:
            return None, None

        def effective_publish_time(video):
            status = video.get("status", {})
            snippet = video.get("snippet", {})
            publish_time_str = status.get("publishAt") or snippet.get("publishedAt")
            dt = dateutil.parser.isoparse(publish_time_str)
            return dt.astimezone(self.local_tz)

        # Sort videos by effective publish time (newest first)
        videos_sorted = sorted(videos, key=effective_publish_time, reverse=True)
        most_recent_video = videos_sorted[0]
        return most_recent_video, effective_publish_time(most_recent_video)

    import datetime as dt

    def get_next_slot(self, reference_dt: datetime.datetime, tz: dt.tzinfo) -> dt.datetime:
        """Return the next upload slot (07:00, 10:00, 12:00, 19:00, 20:00, 22:00) in the given timezone."""
        ref = reference_dt.astimezone(tz) if reference_dt.tzinfo else reference_dt.replace(tzinfo=tz)
        day = ref.date()
        hours = (7, 10, 12, 19, 20, 22)

        # tìm slot hôm nay > ref, nếu không có thì trả slot đầu tiên của ngày mai
        return next(
            (datetime.datetime.combine(day, datetime.time(h), tzinfo=tz)
            for h in hours
            if ref < datetime.datetime.combine(day, datetime.time(h), tzinfo=tz)),
            datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(hours[0]), tzinfo=tz)
        )

    def schedule_video(self):
        """
        Schedule a video upload by determining the next available slot based on the latest video effective publish time.
        """
        data_upload = self.get_data_to_upload()
        if(not data_upload):
            #send_telegram_message("Cannot get data upload for process")
            print("Cannot get data upload for process")
            
            return False
        
        

        
        tz = self.local_tz
        latest_video_time = datetime.datetime.now(tz) + datetime.timedelta(days=3)
        if latest_video_time is None:
            reference_time = datetime.datetime.now(tz)
        else:
            print("Latest video effective publish time:", latest_video_time)
            reference_time = latest_video_time

        next_slot = self.get_next_slot(reference_time, tz)
        now = datetime.datetime.now(tz)
        if next_slot <= now:
            next_slot = self.get_next_slot(now, tz)
        # Convert next slot to UTC RFC3339 format
        slot_utc = next_slot.astimezone(datetime.timezone.utc)
        slot_utc_rfc3339 = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        print("Next upload slot:", slot_utc_rfc3339)

        result_upload = self.process_upload(slot_utc_rfc3339)
        print("result upload: ", result_upload)
        if(not result_upload):
            send_telegram_message(f"Upload video failed {self.project_name}")
            print("upload fail")
            self.fm.update_video(self.project_name, {"upload_status": "error", "error_message": "upload fail"})
            self.fm.update_channel(self.channel_id, {"last_upload": firestore.SERVER_TIMESTAMP})
            return False
        video_id_uploaded = result_upload["video_id"]

        # current_video = self.video
        # current_upload_status = current_video['upload_status']
        # if(current_upload_status == "not_uploaded"):
        #     part_1_link = current_video['part_1_link']
        #     if(part_1_link != ''):
        #         new_upload_status = "part_1_uploaded"
        #     else:
        #         new_upload_status = "uploaded"
        # else:
        #     new_upload_status = "uploaded"
        last_part_name = result_upload["part_name"] 
        self.fm.update_video(self.project_name, {"upload_status": "uploaded",
                                                  "upload_to_yt_time":firestore.SERVER_TIMESTAMP,
                                                  "last_part_name": last_part_name,
                                                    "new_youtube_link":  f"https://www.youtube.com/watch?v={video_id_uploaded}"})
        self.fm.update_channel(self.channel_id, {"last_upload": firestore.SERVER_TIMESTAMP})
        
        shutil.rmtree(f"{self.project_path}/{self.project_name}")
        return True

        #return self.process_upload(slot_utc_rfc3339)

    def upload_video(self, video_file, thumbnail_file,  title, description, time_schedule):
        try:
            print("Uploading video...")
            channel_data = self.channel_config
            channel_ytb_username = channel_data["channel_ytb_username"]
            channel_go_profile = channel_data["channel_go_profile"]
            result = upload_ytb_browser(channel_ytb_username, video_file, thumbnail_file, title, description, channel_go_profile)
            return result
        except Exception as e:
            print(f"Error during upload: {e}")
            return None

    def set_thumbnail(self, youtube, video_id, thumbnail_file):
        try:
            print("Setting thumbnail...")
            request = youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_file)
            )
            response = request.execute()
            print("Thumbnail set!")
            return response
        except Exception as e:
            traceback.print_exc()
            send_telegram_message(f"cannot set thumb for project {video_id}")

    def process_upload(self, time_schedule):
        try:
            #{first_part}_part_{part_name}.jpg
            video = self.video
            title = video['title']
            
            #title_data = get_title(video['video_id'], self.fm)
            
            if "part_name" in video and video["part_name"]:
                part_name = video["part_name"]
            else:
                part_name = ""
            
            
            title_with_part =  f"{part_name}|" + title
            project_name = video['video_id']
            first_part = project_name.split("_")[0] 
            img_path = f"{self.project_path}/{video['video_id']}/{first_part}.jpg"
            out_path = f"{self.project_path}/{video['video_id']}/{first_part}_thumb.jpg"

            write_text_on_image(part_name, img_path, out_path)
            

            file_name = title_to_slug(title)
            channel_config = self.channel_config
            channel_name = channel_config["channel_name"]
            working_dir = f"{self.project_path}/{self.project_name}"
            token_file = f"auth_files/{self.channel_id}.json"
           
            video_file = f"{working_dir}/{file_name}.mp4"

            video_id = video['video_id']
            first_part = video_id.split('_', 1)[0]
            thumbnail_file = f"{working_dir}/{first_part}_thumb.jpg"
            print("thumbnail_file: ", thumbnail_file)
            
            #title = title_with_part
            if len(title_with_part) > 100:
                title_with_part = title_with_part[:98] + '..'
            print("title: ", title)
            description = title+ f" | Phần {part_name} #reviewtruyen #truyentutien #truyenaudio"
            tags = ["reviewtruyen", "truyentutien", "truyenaudio"]
            
            data_upload = self.upload_video(video_file, thumbnail_file, title_with_part, description, time_schedule)
            if(not data_upload):
                print("cannot upload video")
                return False
           
            entry = {
                "title": title,
                "scheduled_time": time_schedule,
                "project_name": self.project_name,
                "part_name": part_name,
                "video_id": data_upload
            }
            return entry
        except Exception as e:
            print(e)
            traceback.print_exc()
            send_telegram_message(f"Error during video upload: {e}")
            return False

    
  
if __name__ == "__main__":
    # Initialize FirestoreManager with the service account path
    # This is used to manage Firestore operations.
    service_account_path = "F:\\Code\\AI\\Auto-Youtube\\auth_files\\firebase.json"
    fm = FirestoreManager(service_account_path)

    scheduler = UploadSchedulerFirebase(fm)
    scheduler.schedule_video()
   