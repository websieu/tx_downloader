import os
import time
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from gologin import GoLogin
import pychrome
from lib.browser import Browser

import re
from selenium.common.exceptions import WebDriverException
from pathlib import Path

from lib.find_username import build_rel_xpath
from lib.utils import GL_PROFILE, GO_LOGIN_TOKEN, REMOTE_PORT, get_video_id
import random

class ManageDriver:
    def __init__(self, gl_token="", port=3600):
       
        self.gl_token = gl_token
        self.driver = None
        
        self.port = port

    
    def start_gl(self, gl_profile, retry=0):
        try:
            print("start profile: "+gl_profile)
            gl = GoLogin({
                'token': self.gl_token,
                'profile_id': gl_profile,
                'port': self.port,
                
            })
            self.gl_profile = gl_profile
            self.gl = None
            self.gl = gl
            self.gl.start()
        except Exception as e:
            print("Error starting GoLogin:")
            print(e)
            traceback.print_exc()
            if self.gl:
                self.gl.stop()
            self.gl = None
            gl = None
            self.gl_profile = None

            if retry < 3:
                print(f"Retrying start... ({retry+1})")
                time.sleep(10)
                return self.start_gl(gl_profile, retry+1)
    def create_driver(self, url):
        try:
            if(self.driver):
                self.driver.close()
            
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")
            self.driver = Browser(f"127.0.0.1:{self.port}")
            self.driver.goto(url)
            time.sleep(10)
            return True
        except Exception as e:
            print("error create driver")
            traceback.print_exc()
            print(e)
            if(self.driver):
                self.driver.close()
            if(self.gl):
                self.gl.stop()
            self.driver = None
            return False

    def script_get(self, js_path: str = "fetch.js", args=None):
        js_code = Path(js_path).read_text(encoding="utf-8")
        # set timeout cho async script
        #self.driver.set_script_timeout(timeout)
        # Truyền URL qua arguments[0] (trong JS)
        data_fr = self.driver.execute_script(js_code, args)
        return data_fr

    def set_item_id(self, item_id):
        self.item_id = item_id
    
    def close(self):
        try:
            if self.driver:
                self.driver.close()
            pass
        except Exception as e:
            print("Error closing driver:")
            print(e)
            traceback.print_exc()
        self.browser = None
        self.driver = None
    
    def close_gl(self):
        if self.gl:
            self.gl.stop()

    def start_session(self, url="", version=None):
        self.create_driver(version)
        
    
    def end_session(self):
        self.close()
    def close_all(self):
        try:
            self.close()
            self.close_gl()
        except Exception as e:
            print("Error closing all:")
            print(e)

def start_fetch_book(url):
    try:
        book_id = re.search(r"/book/(\d+)/?", url).group(1)   # "49983" (string)
        if not book_id:
            print("Book ID not found in URL")
            return False
        fetch_url = 'https://www.69shuba.com/book/' + book_id + '/'
        output_file = f"projects/{book_id}/{book_id}.txt"
        if(os.path.exists(output_file)):
            print(f"File {output_file} already exists. Skipping fetch.")
            return True
        # token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NDljMTNlYWM3ZDdkNDJhNDI3ZWYyZGEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2NTJiYmQzMDRjOWNjMGUwNDliYjU0MWYifQ.kyKlIkpusfvd4BhHzjBQymYDkd40w1-PPotSKxy_IPE'
        # port = 3800
        md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=REMOTE_PORT)
        md.start_gl(gl_profile=GL_PROFILE)
        rs_driver = md.create_driver(fetch_url)
        if not rs_driver:
            print("Failed to create driver.")
            #md.close_all()
            return False
        data = md.script_get("fetch.js")
        data = "".join(data)
        if(data == "error"):
            print("error fetch data")
            md.close_all()
            return False
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data)
        
        md.close_all()
        return True
    except Exception as e:
        print("An error occurred while fetching the book:")
        print(e)
        # if md:
        #     md.close_all()
        return False

def get_download_link(url, retry=0):
    try:
        md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=REMOTE_PORT)
        md.start_gl(gl_profile=GL_PROFILE)
        driver_ts = md.create_driver("https://greenvideo.cc/")
        if not driver_ts:
            print("Failed to create driver.")
            #md.close_all()
            return False
        
        #md.driver.goto(url)
        username_input = md.driver.page.locator("//*[@id='__nuxt']/div[1]/div/div[2]/div/div[1]/div[1]/input")
        username_input.fill(url)
        
        submit_button = md.driver.page.locator("//*[@id='__nuxt']/div[1]/div/div[2]/button")
        submit_button.click()
        md.driver.page.locator("//*[@id='__nuxt']/div[1]/div/div[3]/div[1]/div/div/div").wait_for(state="attached", timeout=1000*3*60)

        js_text = Path("fetch_download.js").read_text(encoding="utf-8")
        video_id = get_video_id(url)
        if video_id.endswith("_1"):
            video_id = video_id[:-2]
        data_fr = md.driver.page.evaluate(js_text, {"args": video_id})
        data_check = data_fr.get("data", "")
        url_download = data_check.get("downloadUrl", "")
        md.close_all()
        return url_download
        
    except Exception as e:
        print("An error occurred while fetching the download link:")
        print(e)
        if md:
            md.close_all()
        if retry < 3:
            print(f"Retrying... ({retry+1})")
            time.sleep(10)
            return get_download_link(url, retry+1)
        else:
            
            return False

def upload_ytb(channel_username='@thiendao96'):
    md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=REMOTE_PORT)
    md.start_gl(gl_profile=GL_PROFILE)
    driver_ts = md.create_driver("https://studio.youtube.com/")
    if not driver_ts:
        print("Failed to create driver.")
        md.close_all()
        return False 
    try:
        avatar = md.driver.page.locator('//*[@id="avatar-btn"]').click()
        time.sleep(2)
        dropdown = md.driver.page.locator('tp-yt-iron-dropdown')
                    # chờ dropdown mở

        item = dropdown.locator('#primary-text-container').nth(2)  # 0-based → phần tử thứ 3
        #item.scroll_into_view_if_needed()
        item.click()
        time.sleep(2)
        # tìm kiếm account theo username
        rel_xpath = build_rel_xpath(channel_username)
        btn = md.driver.page.locator(f"xpath={rel_xpath}").first.click()

        ### click upload btn
        time.sleep(5)
        btn_upload = md.driver.page.locator('//*[@id="create-icon"]').click()
        time.sleep(5)
        btn_upload_video = md.driver.page.locator('//*[@id="text-item-0"]').click()
        time.sleep(5)
        file_path = str(Path(("F:\\Code\\AI\\output_video\\BV13wTkzqEw5_1.mp4")))  # example path
        locator = md.driver.page.locator('//*[@id="content"]/input')
        locator.set_input_files(file_path)  # single file
        #     # click vào account item đầu tiên khớp username
        #     page.locator(f"xpath={rel_xpath}").first.click()
        time.sleep(90)
        md.close_all()
        time.sleep(30)
        return True
    except Exception as e:
        print("An error occurred while upload ytb:")
        traceback.print_exc()
        md.close_all()
        return False
    

if __name__ == "__main__":
    list_channel = ['@thiendao96','@cuuthienlo']
    i = 0
    upload_ytb(channel_username='@cuuthienlo')
    # while i < 8:
    #     ran_channel = random.choice(list_channel)
    #     upload_ytb(channel_username=ran_channel)
    #     i += 1
