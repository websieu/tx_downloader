from time import sleep
import time

import firebase_admin

from lib.firebase_db import FirestoreManager
from upload_ytb import UploadSchedulerFirebase





    
    # Create an instance of FirestoreManager.
    #video_type = 'audio'

def loop_firebase():
    service_account_path = "F:\\Code\\AI\\Auto-Youtube\\auth_files\\firebase.json"

    # Create an instance of FirestoreManager.
    #video_type = 'audio'
    fm = FirestoreManager(service_account_path)
    start = time.time()
    print(f"Start time: {start}")
    while(True):
        now = time.time()
        if now - start > 3600:  # 1 hour
            print("Restarting the loop after 1 hour.")
            start = now
            fm = None
            del fm
            try:
                app = firebase_admin.get_app()
                firebase_admin.delete_app(app)
            except ValueError:
                pass  # chưa có app nào
            fm = FirestoreManager(service_account_path)
        scheduler = UploadSchedulerFirebase(fm)
        scheduler.schedule_video()
        sleep(5*60)

if __name__ == "__main__":
    loop_firebase()