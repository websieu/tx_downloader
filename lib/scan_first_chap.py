import json
import os
import re
from time import sleep

from go_login_auto import ManageDriver
from lib.utils import GO_LOGIN_TOKEN


def start_fetch_book(book_id, md):
    try:
       
        fetch_url = 'https://www.69shuba.com/book/' + book_id + '/'
        
        output_file = f"first_chap/segment_{book_id}.txt"
        if(os.path.exists(output_file)):
            print(f"File {output_file} already exists. Skipping fetch.")
            return True
        # token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NDljMTNlYWM3ZDdkNDJhNDI3ZWYyZGEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2NTJiYmQzMDRjOWNjMGUwNDliYjU0MWYifQ.kyKlIkpusfvd4BhHzjBQymYDkd40w1-PPotSKxy_IPE'
        # port = 3800
        # md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=REMOTE_PORT)
        # md.start_gl(gl_profile=GL_PROFILE)
        # rs_driver = md.create_driver(fetch_url)
        # if not rs_driver:
        #     print("Failed to create driver.")
        #     #md.close_all()
        #     return False
        md.driver.goto(fetch_url)
        sleep(5)  # Chờ trang tải xong, có thể điều chỉnh thời gian chờ nếu cần
        data = md.script_get("js/fetch_first_chap.js")
        data = "".join(data)
        if(data == "error"):
            print("error fetch data")
            #md.close_all()
            return False
        print(f"Fetched data length: {data}")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data)
        
        #md.close_all()
        return True
    except Exception as e:
        print("An error occurred while fetching the book:")
        print(e)
        # if md:
        #     md.close_all()
        return False

def loop_fetch_book():
    try:
        md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=4310)
        md.start_gl(gl_profile="68d0bee8b4d6c3eddf3d7a95")
        md.create_driver("https://69shuba.com/")
        with open("list_id.json", "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        if len(existing_data) == 0:
            print("No book IDs found in list_id.json.")
            md.close_all()
            return False
        output_folder = f"first_chap"
        os.makedirs(output_folder, exist_ok=True)
        for i, book_id in enumerate(existing_data):
            print(f"Fetching book {book_id} {i + 1}/{len(existing_data)}...")
            if os.path.exists(f"{output_folder}/segment_{book_id}.txt"):
                print(f"File for book {book_id} already exists. Skipping.")
                continue
            result = start_fetch_book(book_id, md)
            if not result:
                print(f"Failed to fetch book {book_id}.")
                continue
            sleep(5)  # Chờ 5 giây trước khi fetch sách tiếp theo

        md.close_all()
        return result
    except Exception as e:
        print("An error occurred in loop_fetch_book:")
        print(e)
        return False

if __name__ == "__main__":
    loop_fetch_book()