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

def upload_ytb(channel_username='@tramyeu88'):
    md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=9009)
    md.start_gl(gl_profile="68a2cb0d24daa090cccefcae")
    driver_ts = md.create_driver("https://studio.youtube.com/")
    time.sleep(5)
    if not driver_ts:
        print("Failed to create driver.")
        md.close_all()
        return False 
    try:
        print("click avatar")
        avatar = md.driver.page.locator('//*[@id="avatar-btn"]')
        if avatar.count() == 0:
            account_btn = md.driver.page.locator('//*[@id="account-button"]')
            if account_btn.count() == 0:
                print("Không tìm thấy nút tài khoản.")
                md.close_all()
                return False
            account_btn.click()
        else:
            avatar.click()
        print("click dropdown")
        time.sleep(2)
        dropdown = md.driver.page.locator('tp-yt-iron-dropdown')
                    # chờ dropdown mở

        item = dropdown.locator('#primary-text-container').nth(2)  # 0-based → phần tử thứ 3
        #item.scroll_into_view_if_needed()

        item.click()
        print("click switch account")
        time.sleep(5)
        # tìm kiếm account theo username
        # rel_xpath = build_rel_xpath(channel_username)
        # btn = md.driver.page.locator(f"xpath={rel_xpath}").first.click()
        account_locator = md.driver.page.locator("ytd-account-item-section-renderer").get_by_text(channel_username)
        account_locator.click() # Để click vào phần tử
        print("click account")
        ### click upload btn
        time.sleep(5)
        btn_upload = md.driver.page.locator('//*[@id="create-icon"]').click()
        time.sleep(5)
        btn_upload_video = md.driver.page.locator('//*[@id="text-item-0"]').click()
        time.sleep(5)
        file_path = str(Path(("F:\\Code\\AI\\output_video\\85122_250_long.mp4")))  # example path
        # Use Selenium WebDriver to send file path to input element for large files
        #input_element = md.driver.page.locator('input[type="file"]').set_input_files(file_path)
        set_files_via_cdp(md.driver.page, 'input[type="file"]', file_path)
        #input_element.send_keys(file_path)
        #     # click vào account item đầu tiên khớp username
        #     page.locator(f"xpath={rel_xpath}").first.click()
        time.sleep(10)

        #error_text = md.driver.page.locator('//*[@id="dialog"]/div/ytcp-animatable[2]/div/div[1]/ytcp-ve/div[1]')

        # if error_text.count() > 0:
        #     print("Error upload file:")
        #     print(error_text.text_content())
        #     md.close_all()
        #     return False

        ### check upload status
        uploading = True
        while uploading:
            print("Checking upload status...")
            uploading =  check_upload_status(md.driver.page)
            if uploading:
                print("Still uploading, waiting for 10 seconds...")
                time.sleep(10)

        print("Upload complete.")

        ### set title ###

        title_element = md.driver.page.locator('//ytcp-social-suggestions-textbox[@id="title-textarea"]//div[@id="textbox"]')
        if title_element.count() == 0:
            print("Title element not found.")
            md.close_all()
            return False
        
        title_element.click()
        title_element.fill("Thiên hạ đệ nhất kiếm")

        ### set description ###
        desc_element = md.driver.page.locator('//ytcp-social-suggestions-textbox[@id="description-textarea"]//div[@id="textbox"]')
        if desc_element.count() == 0:
            print("Description element not found.")
            md.close_all()
            return False
        desc_element.click()
        desc_element.fill("Thiên hạ đệ nhất kiếm")

        ### set thumbnail ###

        upload_thumb = md.driver.page.locator("//input[@id='file-loader' and @type='file' and contains(concat(' ', normalize-space(@class), ' '), ' style-scope ') and contains(concat(' ', normalize-space(@class), ' '), ' ytcp-thumbnail-uploader ')]")
        if upload_thumb.count() == 0:
            print("Thumbnail upload element not found.")
            md.close_all()
            return False
        thumb_path = str(Path(("F:\\Code\\AI\\output_video\\31557.jpg")))  # example path
        upload_thumb.set_input_files(thumb_path)
        time.sleep(5)
        ### turn on monetization ###
        monetization_tab = md.driver.page.locator("//button[@id='step-badge-1' and @role='tab' and @test-id='MONETIZATION']")
        if monetization_tab.count() > 0:
            monetization_tab.click()
            time.sleep(5)
            select_on = md.driver.page.locator("//ytcp-video-metadata-monetization[@track-click and contains(concat(' ', normalize-space(@class), ' '), ' monetization-status-setting ') and contains(concat(' ', normalize-space(@class), ' '), ' style-scope ') and contains(concat(' ', normalize-space(@class), ' '), ' ytpp-video-monetization-basics ')]")
            if select_on.count() >0:
                select_on.click()
                time.sleep(2)
                radio_on = md.driver.page.locator('//tp-yt-paper-radio-button[@id="radio-on"]//div[@id="radioContainer"]')
                if radio_on.count() > 0:
                    radio_on.click()
                save_btn_on = md.driver.page.locator("//ytcp-button[@id='save-button']")
                if save_btn_on.count() > 0:
                    save_btn_on.click()
                    time.sleep(2)
                else:
                    print("Save button not found.")
            else:
                print("Monetization option not found.")
        else:
            print("Monetization tab not found.")
        
        ### submit form ads ###
        form_tab = md.driver.page.locator("//button[@id='step-badge-2' and @role='tab' and @test-id='CONTENT_RATINGS']")
        if form_tab.count() > 0:
            form_tab.click()
            time.sleep(5)
            check_all = md.driver.page.locator("//ytcp-checkbox-lit[contains(concat(' ', normalize-space(@class), ' '), ' all-none-checkbox ')]//div[contains(concat(' ', normalize-space(@class), ' '), ' label ')]")
            if check_all.count() > 0:
                check_all.click()
                time.sleep(2)
            else:
                print("Check all checkbox not found.")
            submit_btn = md.driver.page.locator("//ytcp-button[@id='submit-questionnaire-button']")
            if submit_btn.count() > 0:
                submit_btn.click()
        else:
            print("Form tab not found.")
        
        ### schedule publish ###
        
        lang = (md.driver.page.get_attribute("html", "lang") or "").lower()
        page_lang = (lang.split("-", 1)[0]) if lang else "unknown"
        print(page_lang)

        schedule_tab = md.driver.page.locator("//button[@id='step-badge-5' and @role='tab' and @test-id='REVIEW']")
        time.sleep(5)

        if schedule_tab.count() > 0:
            schedule_tab.click()
            time.sleep(5)
            open_schedule = md.driver.page.locator("//div[@id='visibility-container']//div[@id='second-container']")
            if open_schedule.count() > 0:
                open_schedule.click()
                time.sleep(2)
            date_picker = md.driver.page.locator("//ytcp-text-dropdown-trigger[@id='datepicker-trigger']//ytcp-dropdown-trigger[@tabindex='0']")
            if date_picker.count() > 0:
                date_picker.click()
                time.sleep(2)
            else:
                print("Date picker not found.")

            

            input_date = md.driver.page.locator("//tp-yt-iron-input[@id='input-13']//input")
            if input_date.count() > 0:
                input_date.click()
                if page_lang == "vi":
                    input_date.fill("20/09/2025")
                else:
                    input_date.fill("09/20/2025")
                input_date.press("Enter")

                time.sleep(2)
                
            else:
                print("Input date not found.")

            input_hours = md.driver.page.locator("//tp-yt-iron-input[@id='input-3']//input")
            if input_hours.count() > 0:
                input_hours.click()
                input_hours.fill("20:30")
                input_hours.press("Enter")
                time.sleep(2)
            else:
                print("Input hours not found.")


            done_btn = md.driver.page.locator("//ytcp-button[@id='done-button']")
            if done_btn.count() > 0:
                    done_btn.click()
                    time.sleep(2)
            else:
                print("Done button not found.")

        time.sleep(30)
        md.close_all()
        time.sleep(30)
        return True
    except Exception as e:
        print("An error occurred while upload ytb:")
        traceback.print_exc()
        md.close_all()
        return False
def ensure_upload_complete(page, timeout=600):
    selector = "span.progress-label.style-scope.ytcp-video-upload-progress"
    locator = page.locator(selector)
    if locator.count() > 0:
        try:
            # Lấy nội dung text của phần tử
            text_content = locator.text_content().lower()

            # Kiểm tra nội dung text
            if "uploading" in text_content or "đã tải được" in text_content:
                print(f"Phần tử '{selector}' tồn tại và đang hiển thị trạng thái upload.")
                return True
            else:
                print(f"Phần tử '{selector}' tồn tại nhưng không hiển thị trạng thái upload mong muốn.")
                return False
        except Exception as e:
            print(f"Lỗi khi lấy text content hoặc kiểm tra: {e}")
            return False
    else:
        print(f"Phần tử '{selector}' không tồn tại.")
        return False
def check_upload_status(page):
    """
    Kiểm tra xem phần tử hiển thị tiến trình upload có tồn tại hay không
    và nội dung của nó có chứa "uploading" hoặc "đang upload".

    Args:
        page: Đối tượng page của Playwright.

    Returns:
        bool: True nếu phần tử tồn tại và chứa text mong muốn, ngược lại là False.
    """
    selector = "span.progress-label.style-scope.ytcp-video-upload-progress"
    locator = page.locator(selector)

    # Kiểm tra sự tồn tại của phần tử
    if locator.count() > 0:
        try:
            # Lấy nội dung text của phần tử
            text_content = locator.text_content().lower()

            # Kiểm tra nội dung text
            if "uploading" in text_content or "đã tải được" in text_content:
                print(f"Phần tử '{selector}' tồn tại và đang hiển thị trạng thái upload.")
                return True
            else:
                print(f"Phần tử '{selector}' tồn tại nhưng không hiển thị trạng thái upload mong muốn.")
                return False
        except Exception as e:
            print(f"Lỗi khi lấy text content hoặc kiểm tra: {e}")
            return False
    else:
        print(f"Phần tử '{selector}' không tồn tại.")
        return False

def set_files_via_cdp(page, css_selector, files, frame=None):
    """
    Dùng CDP DOM.setFileInputFiles để đặt file trực tiếp từ máy chạy Chrome.
    - css_selector: selector của input[type=file]
    - files: str hoặc list[str] (đường dẫn tuyệt đối trên máy CHROME/GoLogin)
    - frame: tùy chọn, truyền page.frame(...) nếu input nằm trong iframe
    """
    try:
        if isinstance(files, str):
            files = [files]

        # Nếu input ở trong iframe, tạo CDP session trên frame đó:
        target = frame if frame else page
        session = page.context.new_cdp_session(target)  # CDPSession
        session.send("DOM.enable")
        doc = session.send("DOM.getDocument", {"depth": 1, "pierce": True})
        q = session.send("DOM.querySelector", {
            "nodeId": doc["root"]["nodeId"],
            "selector": css_selector
        })
        node_id = q.get("nodeId")
        if not node_id:
            raise RuntimeError(f"Không tìm thấy input: {css_selector}")

        # Điểm mấu chốt: truyền đường dẫn file LOCAL của máy chạy Chrome
        session.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": files
        })
    except Exception as e:
        print(f"set_files_via_cdp error: {e}")
        traceback.print_exc()
        raise





if __name__ == "__main__":
    list_channel = ['@thiendao96','@cuuthienlo']
    i = 0
    upload_ytb(channel_username='@Baoureview299')
    # while i < 8:
    #     ran_channel = random.choice(list_channel)
    #     upload_ytb(channel_username=ran_channel)
    #     i += 1
