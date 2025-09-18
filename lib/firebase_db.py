import ast
from datetime import datetime, timedelta, timezone
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
import urllib.parse
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1 import field_path as field_path_module

from lib.utils import LIST_CHANNEL, VIDEO_TYPE, get_book_id


class FirestoreManager:
    def __init__(self, service_account_path: str):
        """
        Initialize the Firebase Admin SDK and create a Firestore client.

        Args:
            service_account_path (str): Path to the Firebase service account JSON file.
        """
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    # ----------------------------
    # Channel management methods
    # ----------------------------
    def create_channel(self, channel_username: str, channel_data: dict) -> None:
        """
        Create a new channel document.
        """
        self.db.collection("channels").document(channel_username).set(channel_data)
        print(f"Channel '{channel_username}' created/updated successfully.")

    def select_channel_by_id(self, channel_id: str) -> dict:
        """
        Select one video document by its channel_id.

        Args:
            channel_id (str): The ID of the channel_id to retrieve.

        Returns:
            dict: A dictionary representing the video document, including the document ID as 'channel_id',
                or None if no match is found.
        """
        video_ref = self.db.collection("channels").document(channel_id)
        result = video_ref.get()

        if result.exists:
            video = result.to_dict()
            video["channel_username"] = result.id  # include the document ID
            return video
        else:
            print(f"No channel found with channel_id: {channel_id}")
            return None

    def update_channel(self, channel_username: str, data_update) -> None:
        """
        Update the last_upload field of a channel.
        """
        self.db.collection("channels").document(channel_username).update(data_update)
        print(f"Channel '{channel_username}' last upload updated successfully.")

    def update_last_selected(self, channel_username):
        try:
            data_update = {
                "last_selected": firestore.SERVER_TIMESTAMP
            }
            self.update_channel(channel_username, data_update)
            return True
        except Exception as e:
            print(f"Error updating last selected for channel {channel_username}: {e}")
            return False
    def upload_last_field(self, channel_username, field_name):
        try:
            data_update = {
                field_name: firestore.SERVER_TIMESTAMP
            }
            self.update_channel(channel_username, data_update)
            return True
        except Exception as e:
            print(f"Error updating last selected for channel {channel_username}: {e}")
            return False

    def select_channel_oldest_upload(self):
        """
        Select the active channel with the oldest last_upload time.
        """
        channels_ref = self.db.collection("channels")
        query = (channels_ref
                .where("status", "==", "active")
                .order_by("last_upload", direction=firestore.Query.ASCENDING)
                .limit(1))
        results = query.get()
        if results:
            channel = results[0].to_dict()
            channel["channel_username"] = results[0].id  # include the document ID
            return channel
        else:
            print("No active channels found.")
            return None
    def select_channel_for_process(self, video_type):
        """
        Select the active channel with the oldest last_selected time and matching channel_type.
        This method fetches all channels matching the where conditions, then sorts them
        in Python based on the 'last_selected' field.

        Args:
            video_type: The channel type to filter by.
            
        Returns:
            dict: A dictionary representing the channel with the oldest last_selected time,
                including the document ID as 'channel_username', or None if no match is found.
        """
        try:
            channels_ref = self.db.collection("channels")
            # Query without order_by to avoid composite index requirement.
            query = (channels_ref
                    .where(filter=FieldFilter("status", "==", "active"))
                    .where(filter=FieldFilter("channel_type", "==", video_type)))
                    
            results = query.get()
            channels = []
            
            for doc in results:
                ch = doc.to_dict()
                ch["channel_username"] = doc.id  # include the document ID
                channels.append(ch)
                
            if not channels:
                print("No active channels found for channel_type:", video_type)
                return None

            # Sort channels by 'last_selected' (assumed to be a comparable value like a timestamp)
            channels.sort(key=lambda ch: ch.get("last_selected"))
            
            # Return the channel with the oldest last_selected value.
            return channels[0]
        except Exception as e:
            print(f"not found channel to process with error: {e}")
            return None

    def select_channel_for_download(self):
        """
        Select the active channel with the oldest last_selected time and matching channel_type.
        This method fetches all channels matching the where conditions, then sorts them
        in Python based on the 'last_selected' field.

        Args:
            video_type: The channel type to filter by.
            
        Returns:
            dict: A dictionary representing the channel with the oldest last_selected time,
                including the document ID as 'channel_username', or None if no match is found.
        """
        try:
            channels_ref = self.db.collection("channels")
            # Query without order_by to avoid composite index requirement.
            query = (channels_ref
                    .where(filter=FieldFilter("status", "==", "active"))
                    )
                    
            results = query.get()
            channels = []
            
            for doc in results:
                ch = doc.to_dict()
                ch["channel_username"] = doc.id  # include the document ID
                channels.append(ch)
                
            if not channels:
                print("No active channels found ")
                return None

            # Sort channels by 'last_selected' (assumed to be a comparable value like a timestamp)
            channels.sort(key=lambda ch: ch.get("last_selected"))
            for channel in channels:
                print(f"Channel: {channel['channel_username']}")
                if channel['channel_username'] in ast.literal_eval(LIST_CHANNEL):
                    return channel  
            # Return the channel with the oldest last_selected value.
            return None
        except Exception as e:
            print(f"not found channel to process with error: {e}")
            
            return None

    def select_channel_by_field(self, field_name):
        """
        Select the active channel with the oldest last_selected time and matching channel_type.
        This method fetches all channels matching the where conditions, then sorts them
        in Python based on the 'last_selected' field.

        Args:
            video_type: The channel type to filter by.
            
        Returns:
            dict: A dictionary representing the channel with the oldest last_selected time,
                including the document ID as 'channel_username', or None if no match is found.
        """
        try:
            channels_ref = self.db.collection("channels")
            # Query without order_by to avoid composite index requirement.
            query = (channels_ref
                    .where(filter=FieldFilter("status", "==", "active"))
                    )
                    
            results = query.get()
            channels = []
            
            for doc in results:
                ch = doc.to_dict()
                ch["channel_username"] = doc.id  # include the document ID
                channels.append(ch)
                
            if not channels:
                print("No active channels found ")
                return None

            # Sort channels by 'last_selected' (assumed to be a comparable value like a timestamp)
            channels.sort(key=lambda ch: ch.get(field_name, 0))
            for channel in channels:
                print(f"Channel: {channel['channel_username']}")
                if channel['channel_username'] in ast.literal_eval(LIST_CHANNEL):
                    return channel  
            # Return the channel with the oldest last_selected value.
            return None
        except Exception as e:
            print(f"not found channel to process with error: {e}")
            
            return None


    def select_video_by_channel_for_download(self, channel_username) -> dict:

        """
        Select one video filtered by a specific process_status.
        
        Args:
            process_status_value: The process status to filter videos (e.g., "pending").
            
        Returns:
            dict: A dictionary representing the first video document matching the filter,
                including the document ID as 'video_id', or None if no match is found.
        """
        try:
            conditions = {
                
                "process_status": "pending",
                "channel_username": channel_username,
                "type": VIDEO_TYPE
                
            }
            order = {
                "time_completed": "asc"
            }
            return self.select_video_dynamic(conditions, order)
        except Exception as e:
            print(e)
            return False


    def select_channel_by_list(self, video_type, list_channel):
        try:
            
            channels_ref = self.db.collection("channels")
            doc_refs = [channels_ref.document(doc_id) for doc_id in list_channel]
            # Query without order_by to avoid composite index requirement.
            query = (channels_ref
                    .where(filter=FieldFilter("status", "==", "active"))
                    .where(filter=FieldFilter("channel_type", "==", video_type))
                    .where(field_path_module.FieldPath.document_id(), "in", doc_refs))
                    
            results = query.get()
            channels = []
            
            for doc in results:
                ch = doc.to_dict()
                ch["channel_username"] = doc.id  # include the document ID
                channels.append(ch)
                
            if not channels:
                print("No active channels found for channel_type:", video_type)
                return None

            # Sort channels by 'last_selected' (assumed to be a comparable value like a timestamp)
            channels.sort(key=lambda ch: ch.get("last_selected"))
            
            # Return the channel with the oldest last_selected value.
            return channels[0]
        except Exception as e:
            print(f"not found channel to process with error: {e}")
            return None

    def select_channels_by_video_type(self, video_type):
        """
        Select the active channel with the oldest last_selected time and matching channel_type.
        This method fetches all channels matching the where conditions, then sorts them
        in Python based on the 'last_selected' field.

        Args:
            video_type: The channel type to filter by.
            
        Returns:
            dict: A dictionary representing the channel with the oldest last_selected time,
                including the document ID as 'channel_username', or None if no match is found.
        """
        try:
            channels_ref = self.db.collection("channels")
            # Query without order_by to avoid composite index requirement.
            query = (channels_ref
                    .where(filter=FieldFilter("status", "==", "active"))
                    .where(filter=FieldFilter("channel_type", "==", video_type)))
                    
            results = query.get()
            channels = []
            
            for doc in results:
                ch = doc.to_dict()
                ch["channel_username"] = doc.id  # include the document ID
                channels.append(ch)
                
            if not channels:
                print("No active channels found for channel_type:", video_type)
                return None

            # Sort channels by 'last_selected' (assumed to be a comparable value like a timestamp)
            channels.sort(key=lambda ch: ch.get("last_selected"))
            
            # Return the channel with the oldest last_selected value.
            return channels
        except Exception as e:
            print(f"not found channel to process with error: {e}")
            return None


    def update_all_channels_to_active(self) -> None:
        """
        Update all channel documents to set their status to 'active'.
        """
        channels_ref = self.db.collection("channels")
        docs = channels_ref.get()
        
        # Create a batch instance to update documents in bulk.
        batch = self.db.batch()
        
        for doc in docs:
            channel_ref = channels_ref.document(doc.id)
            batch.update(channel_ref, {"hg_dataset": "raymondt/bao_u"})
        
        batch.commit()
        print("All channels updated to 'active'.")
    
    def update_all_videos_version(self) -> None:
        """
        Update all channel documents to set their status to 'active'.
        """
        video_ref = self.db.collection("videos")
        docs = video_ref.get()
        
        # Create a batch instance to update documents in bulk.
        batch = self.db.batch()
        one_year_ago = datetime.utcnow() - timedelta(days=365)
        for doc in docs:
            channel_ref = video_ref.document(doc.id)
            batch.update(channel_ref, {"upload_to_yt_time": 0})
        
        batch.commit()
        print("All video updated version 0")

    # ----------------------------
    # Video management methods
    # ----------------------------
    def create_video(self, video_id: str, video_data: dict) -> None:
        """
        Create a new video document.
        """
        self.db.collection("videos").document(video_id).set(video_data)
        print(f"Video '{video_id}' created/updated successfully.")

    def select_video_by_id(self, video_id: str) -> dict:
        """
        Select one video document by its video_id.

        Args:
            video_id (str): The ID of the video to retrieve.

        Returns:
            dict: A dictionary representing the video document, including the document ID as 'video_id',
                or None if no match is found.
        """
        video_ref = self.db.collection("videos").document(video_id)
        result = video_ref.get()

        if result.exists:
            video = result.to_dict()
            video["video_id"] = result.id  # include the document ID
            return video
        else:
            print(f"No video found with video_id: {video_id}")
            return None

    def select_list_video_by_process_status(self, process_status_value) -> list:
        """
        Select videos filtered by a specific process_status.
        """
        videos_ref = self.db.collection("videos")
        query = videos_ref.where("process_status", "==", process_status_value)
        results = query.get()
        videos = []
        for doc in results:
            video = doc.to_dict()
            video["video_id"] = doc.id  # include the document ID
            videos.append(video)
        return videos

    def fetch_current_processing_videos(self) -> list:
        """
        Fetch all videos that are currently being processed.
        
        Returns:
            list: A list of dictionaries representing video documents that are currently being processed,
                each including the document ID as 'video_id'.
        """
        try:
            videos = self.select_list_video_by_process_status("processing")
            if not videos:
                print("No videos are currently being processed.")
                return None
            for video in videos:
                video_id = video['video_id']
                if(os.path.exists(f"/root/wan/projects/{video_id}")):
                    return video
            return None
        except Exception as e:
            print(e)
            return None

    def select_video_for_process(self, video_type) -> dict:

        """
        Select one video filtered by a specific process_status.
        
        Args:
            process_status_value: The process status to filter videos (e.g., "pending").
            
        Returns:
            dict: A dictionary representing the first video document matching the filter,
                including the document ID as 'video_id', or None if no match is found.
        """
        try:
            conditions = {
                "type": video_type,
                "process_status": "pending",
                
            }
            return self.select_video_dynamic(conditions)
        except Exception as e:
            print(e)
            return False
    
    def select_video_by_channel(self, video_type, channel_username) -> dict:

        """
        Select one video filtered by a specific process_status.
        
        Args:
            process_status_value: The process status to filter videos (e.g., "pending").
            
        Returns:
            dict: A dictionary representing the first video document matching the filter,
                including the document ID as 'video_id', or None if no match is found.
        """
        try:
            conditions = {
                "type": video_type,
                "process_status": "pending",
                "channel_username": channel_username
                
            }
            return self.select_video_dynamic(conditions)
        except Exception as e:
            print(e)
            return False

    def select_video_by_list_channel(self, video_type, channel_username) -> dict:

        """
        Select one video filtered by a specific process_status.
        
        Args:
            process_status_value: The process status to filter videos (e.g., "pending").
            
        Returns:
            dict: A dictionary representing the first video document matching the filter,
                including the document ID as 'video_id', or None if no match is found.
        """
        try:
            #print("select video by channel: ", channel_username)
            conditions = {
                "type": video_type,
                "process_status": "downloaded",
                "channel_username": channel_username
                
            }
            order = {
                "time_completed": "asc"
            }
            return self.select_video_dynamic(conditions, order)
        except Exception as e:
            print(e)
            return False

    def select_video_for_upload(self):
        video_uploaded_part1 = self.select_video_uploaded_part1()
        if video_uploaded_part1:
            return video_uploaded_part1
        
        conditions = {
            
            "process_status": "completed",
            "upload_status": "not_uploaded",
            "channel_username": ast.literal_eval(LIST_CHANNEL),
            "type": VIDEO_TYPE
            
        }
        order = {
            "time_completed": "asc"
        }
        return self.select_video_dynamic(conditions, order)
    
    def select_video_uploaded_part1(self):
        """
        Select one video that has been processed and is ready for upload to YouTube.
        
        Returns:
            dict: A dictionary representing the first video document ready for upload,
                including the document ID as 'video_id', or None if no match is found.
        """
        conditions = {
            "process_status": "completed",
            "upload_status": "part_1_uploaded",
            "channel_username": ast.literal_eval(LIST_CHANNEL)
        }
        order = {
            "time_completed": "asc"
        }
        return self.select_video_dynamic(conditions, order)

    def select_video_dynamic(self, conditions: dict, order: dict = None) -> dict:
        """
        Select one video document based on dynamic filtering conditions.
        
        Args:
            conditions (dict): A dictionary where the key is the field name and the value is the value to filter by.
                            For example: {"process_status": "pending", "upload_status": "not_uploaded"}.
            
        Returns:
            dict: A dictionary representing the first video document matching the filters,
                including the document ID as 'video_id', or None if no match is found.
        """
        query = self.db.collection("videos")
        
        # Dynamically chain where conditions.
        for field, value in conditions.items():
            print(f"[DEBUG] field={field}, value={value}, type={type(value)}")
            if isinstance(value, list):
                print(f"Filtering by field '{field}' with value list: {value}")
                query = query.where(filter=FieldFilter(field, "in", value))

            else:
                query = query.where(filter=FieldFilter(field, "==", value))
        
        # Dynamically chain order_by conditions.
        if order:
            for field, direction in order.items():
                if isinstance(direction, str) and direction.lower() == "desc":
                    query = query.order_by(field, direction=firestore.Query.DESCENDING)
                else:
                    query = query.order_by(field, direction=firestore.Query.ASCENDING)
        else:
            # Default ordering if no order parameter provided.
            query = query.order_by("view_count", direction=firestore.Query.DESCENDING)

        # Limit the query to one result.
        query = query.limit(1)
        results = query.get()
        
        if results:
            video = results[0].to_dict()
            video["video_id"] = results[0].id  # include the document ID
            return video
        else:
            print("No video found with the provided conditions.")
            return None


    def update_video(self, video_id: str, update_data: dict) -> None:
        """
        Update a video document by its ID.
        """
        try:
            self.db.collection("videos").document(video_id).update(update_data)
            print(f"Video '{video_id}' updated successfully.")
        except Exception as e:
            print(e)

    def update_video_for_process(self, video, status='processing') -> None:
        """
        Update a video document by its ID only if its 'version' field equals 0.
        This method uses a Firestore transaction to ensure that the update
        only occurs when the condition is met.
        
        Args:
            video_id (str): The unique identifier for the video.
            update_data (dict): A dictionary of fields to update in the video document.
        """
        update_data = {"version": 1, "process_status": status}
        video_ref = self.db.collection("videos").document(video['video_id'])
        transaction = self.db.transaction()
        video_id = video['video_id']
        @firestore.transactional
        def update_if_version_zero(transaction, video_ref):
            snapshot = video_ref.get(transaction=transaction)
            if snapshot.exists:
                if snapshot.get("version") == video['version']:
                    transaction.update(video_ref, update_data)
                    print(f"Video '{video_id}' updated successfully.")
                    return True
                else:
                    print(f"Video '{video_id}' not updated because version is not 0.")
                    return False
            else:
                print(f"Video '{video_id}' does not exist.")
                return False
        
        try:
            return update_if_version_zero(transaction, video_ref)
        except Exception as e:
            print(e)
            return False


    
    def batch_create_videos_from_list(self, list_video, video_type: str) -> None:
        """
        Read a text file containing YouTube video links (one per line), extract each video's ID,
        and create a video document with default field values.

        Each video document will have:
            "title": "",
            "youtube_link": <original link>,
            "process_status": "pending",
            "upload_status": "not_uploaded",
            "hg_link": "",
            "channel_username": ""
        
        Args:
            file_path (str): Path to the text file containing video links.
        """

        one_year_ago = datetime.utcnow() - timedelta(days=365)
        for video in list_video:
            video_link = video[0]
            if not video_link:
                continue  # Skip empty lines

            # Parse the URL to extract query parameters
            parsed_url = urllib.parse.urlparse(video_link)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            video_id_list = query_params.get("v")

            if video_id_list:
                video_id = video_id_list[0]
                doc_ref = self.db.collection("videos").document(video_id)
                if doc_ref.get().exists:
                    print(f"Video '{video_id}' already exists. Skipping creation.")
                    continue
                video_data = {
                    "title": "",
                    "youtube_link": video_link,
                    "process_status": "pending",
                    "upload_status": "not_uploaded",
                    "hg_link": "",
                    "channel_username": "",
                    "type": video_type,
                    "version": 0,
                    "view_count": video[1],
                    "time_completed": firestore.SERVER_TIMESTAMP,
                    "upload_to_yt_time": 0,
                    "status_upload_tiktok": "not_uploaded"
                }
                self.create_video(video_id, video_data)
            else:
                print(f"Failed to extract video id from: {video_link}")

    def is_last_upload_older_than_3_hours(self, channel_data: dict) -> bool:
        # Retrieve the last_upload timestamp from the channel data.
        last_upload = channel_data.get("last_upload")
        if not last_upload:
            print("No last_upload timestamp found.")
            return False  # Or handle as needed

        # Calculate the time one hour ago.
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        # Return True if last_upload is earlier than one_hour_ago.
        return last_upload < one_hour_ago

    def delete_videos_by_channel(self,
                                 channel_username: str,
                                 batch_size: int = 500) -> int:
        """
        Permanently delete all video documents that belong to a channel.

        Args:
            channel_username (str): The channel_username to match.
            batch_size (int): How many docs to delete per batch commit
                              (Firestore max is 500).

        Returns:
            int: Total number of video docs deleted.
        """
        total_deleted = 0
        try:
            videos_ref = self.db.collection("videos")
            # Keep looping until the query returns no more results
            while True:
                # Fetch up to `batch_size` docs that match the channel
                query = (videos_ref
                         .where("channel_username", "==", channel_username)
                         .limit(batch_size))
                docs = query.get()
                if not docs:                      # nothing left to delete
                    break

                # Batch-delete this page of docs
                batch = self.db.batch()
                for doc in docs:
                    batch.delete(doc.reference)
                    total_deleted += 1
                batch.commit()
                print(f"Deleted {len(docs)} documents "
                      f"from channel '{channel_username}' ...")

            print(f"Finished -- {total_deleted} total documents removed.")
        except Exception as e:
            print(f"Error deleting videos for channel '{channel_username}': {e}")

        return total_deleted
if __name__ == "__main__":
    # Replace with the path to your service account JSON file.
    service_account_path = "F:\\Code\\AI\\Auto-Youtube\\auth_files\\firebase.json"

    # Create an instance of FirestoreManager.
    fm = FirestoreManager(service_account_path)
    video = fm.select_video_for_upload()
    print(video)
    #video = fm.select_video_uploaded_part1()
    # channel = fm.select_channel_by_list("ancient", ast.literal_eval(LIST_CHANNEL))
    # print(f"channel {channel} videos.")
    # print(video)
    # data = fm.select_channel_by_id('mong_tien_lo')
    # print(data)
    # check_last_upload = fm.is_last_upload_older_than_3_hours(data)
    # print(check_last_upload)
    #data_update = fm.batch_create_videos_from_file("/root/wan/list_video.txt","video")
    #print(data_update)
    # # Example: Batch create videos from a file named 'videos.txt'.
    # # Ensure that 'videos.txt' contains one YouTube link per line.
    # #fm.batch_create_videos_from_file("/root/auto-cartoon/list_video.txt","audio")
    # one_year_ago = datetime.utcnow() - timedelta(days=365)
    # channel_prefix = 'anh_d_review'
    # channel_name = 'AnhD Review'
    # channel_data = {
    #     "channel_name": channel_name,
    #     "channel_auth_file": f"{channel_prefix}.json",
    #     "channel_ending_mp3": f"ending_{channel_prefix}.mp3",
    #     "channel_logo_file": f"logo_{channel_prefix}.png",
    #     "last_upload": one_year_ago,
    #     "last_selected": one_year_ago,
    #     "channel_type": "ancient",
    #     "status": "active",
    #     "hg_dataset": f"raymondt/{channel_prefix}"
    # }
    # fm.create_channel(channel_prefix, channel_data)
    
    
