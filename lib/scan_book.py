import os
import re

from go_login_auto import ManageDriver
from lib.utils import GO_LOGIN_TOKEN
import json


def start_fetch_cat(url):
    try:
       
        
        output_file = f"list_id.json"
        # if(os.path.exists(output_file)):
        #     print(f"File {output_file} already exists. Skipping fetch.")
        #     return True
        # token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NDljMTNlYWM3ZDdkNDJhNDI3ZWYyZGEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2NTJiYmQzMDRjOWNjMGUwNDliYjU0MWYifQ.kyKlIkpusfvd4BhHzjBQymYDkd40w1-PPotSKxy_IPE'
        # port = 3800
        md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=9080)
        md.start_gl(gl_profile="68d0bee8b4d6c3eddf3d7a95")
        rs_driver = md.create_driver(url)
        if not rs_driver:
            print("Failed to create driver.")
            #md.close_all()
            return False
        data = md.script_get("js/fetch_cat.js")
        #data = "".join(data)
        if(data == "error"):
            print("error fetch data")
            md.close_all()
            return False
        if os.path.exists(output_file):
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"Error reading {output_file}: {e}")
                existing_data = []
        else:
            existing_data = []

        # Merge and remove duplicates
        if isinstance(data, list) and isinstance(existing_data, list):
            merged = existing_data + data
            # Remove duplicates based on JSON serialization
            unique = []
            seen = set()
            for item in merged:
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    unique.append(item)
            data = unique
        print(f"Fetched {len(data)} unique items.")
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error writing to {output_file}: {e}")
            md.close_all()
            return False
        
        md.close_all()
        return True
    except Exception as e:
        print("An error occurred while fetching the book:")
        print(e)
        # if md:
        #     md.close_all()
        return False

if __name__ == "__main__":
    url = "https://www.69shuba.com/novels/monthvisit_1_0_1.htm"
    start_fetch_cat(url)