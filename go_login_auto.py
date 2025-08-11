import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from gologin import GoLogin
import pychrome
from lib.browser import Browser

import re
from selenium.common.exceptions import WebDriverException
from pathlib import Path

class ManageDriver:
    def __init__(self, gl_token="", port=3600):
       
        self.gl_token = gl_token
        self.driver = None
        
        self.port = port

    
    def start_gl(self, gl_profile):
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
    def create_driver(self, url):
        try:
            if(self.driver):
                self.driver.close()
            
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")
            self.driver = Browser(f"127.0.0.1:{self.port}")
            self.driver.goto(url)
            time.sleep(10)
        except Exception as e:
            print("error create driver")
            print(e)
            if(self.driver):
                self.driver.close()
            if(self.gl):
                self.gl.stop()
            self.driver = None

    def script_get(self, js_path: str = "fetch.js"):
        js_code = Path(js_path).read_text(encoding="utf-8")
        # set timeout cho async script
        #self.driver.set_script_timeout(timeout)
        # Truyền URL qua arguments[0] (trong JS)
        data_fr = self.driver.execute_script(js_code)
        return data_fr

    def set_item_id(self, item_id):
        self.item_id = item_id
    
    def close(self):
        
        self.driver.close()
       
        self.browser = None
        self.driver = None
    
    def close_gl(self):
        
        self.gl.stop()

    def start_session(self, url="", version=None):
        self.create_driver(version)
        
    
    def end_session(self):
        self.close()
    def close_all(self):
        self.close()
        self.close_gl()

def start_fetch_book(url):
    try:
        book_id = re.search(r"/book/(\d+)/?", url).group(1)   # "49983" (string)
        if not book_id:
            print("Book ID not found in URL")
            return False
        output_file = f"projects/{book_id}/{book_id}.txt"
        if(os.path.exists(output_file)):
            print(f"File {output_file} already exists. Skipping fetch.")
            return True
        md = ManageDriver(gl_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NDljMTNlYWM3ZDdkNDJhNDI3ZWYyZGEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2NTJiYmQzMDRjOWNjMGUwNDliYjU0MWYifQ.kyKlIkpusfvd4BhHzjBQymYDkd40w1-PPotSKxy_IPE")
        md.start_gl(gl_profile="6875c69a1c72b789edb8c784")
        md.create_driver(url)
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
        if md:
            md.close_all()
        return False


if __name__ == "__main__":
    start_fetch_book("https://www.69shuba.com/book/89816/")