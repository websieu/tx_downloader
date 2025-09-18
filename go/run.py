from time import sleep
from selenium import webdriver

from lib.ads_cal import compute_ad_timestamps
from lib.browser import Browser

if __name__ == "__main__":
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:8088")
    driver = Browser(f"127.0.0.1:8088")
    page = driver.current_page
    
    # menu = page.locator("//tp-yt-paper-icon-item[@id='menu-paper-icon-item-5']")
    # if(menu.count() > 0):
    #     print("click menu")
    #     menu.click()
    #     sleep(5)
    # else:
    #     print("menu not found")

    ### click start set ads ###
    # start_set_ads = page.locator("//ytcp-button[@id='place-manually-button']")
    # if(start_set_ads.count() > 0):
    #     print("click start set ads")
    #     start_set_ads.click()
    #     sleep(5)
    # else:
    #     print("start set ads not found")
    
    ### uncheck auto ads ###

    # checkbox = page.locator("//ytcp-checkbox-lit[@test-id]//div[@id='checkbox' and @tabindex='0']")
    # if(checkbox.count() > 0):
    #     print("uncheck auto ads")
    #     is_checked = checkbox.get_attribute("aria-checked")
    #     if(is_checked == 'true'):
    #         label = page.locator("//ytcp-checkbox-lit[@test-id]//div[@class='label style-scope ytcp-checkbox-lit']")
    #         if (label.count() > 0):
    #             print("click label to uncheck")
    #             label.click()
    #             sleep(2)
    #         #checkbox.click()
    #     else:
    #         print("auto ads already unchecked")
    #     sleep(5)
    # else:
    #     print("auto ads checkbox not found")
    ### end click start set ads ###

    # ads_slot = compute_ad_timestamps("09:48:00", "01:00:00") 
    # total_ads = len(ads_slot)
    # print(f"total ads slot: {total_ads}")
    # ### click insert ad break ###
    # insert_ad_break = page.locator("//ytcp-button[@test-id='insert-ad-slot']")
    # if(insert_ad_break.count() > 0):
    #     print("click insert ad break")
    #     for i in range(total_ads):
    #         insert_ad_break.click()
    #         sleep(1)
    # else:
    #     print("insert ad break not found")
    # ### end click insert ad break ###

    # ### start set time ###
    # set_time_inputs = page.locator("//ytve-framestamp-input//input")
    # if(set_time_inputs.count() > 0):
    #     for i in range(set_time_inputs.count()):
    #         if(i >= total_ads):
    #             break
    #         time_str = ads_slot[i]
    #         #time_str = time_str[::-1]
    #         print(f"set time for ad break {i+1}: {time_str}")
    #         input_box = set_time_inputs.nth(i)
    #         input_box.press("Control+A")  # Ctrl+A
    #         input_box.press("Backspace")        # Delete
    #         input_box.type(time_str)
    #         sleep(1)
    # else:
    #     print("set time inputs not found")
    # ### end set time ###

    ### click save button ###

    save_btn = page.locator("//div[@id='save-container']//ytcp-button[@id='save-button']")
    if(save_btn.count() > 0):
        print("click save button")
        save_btn.click()
        sleep(5)
    else:
        print("save button not found")

    ### end click save button ###

    #page.goto("https://studio.youtube.com/")
    sleep(500000)
    driver.close()
    driver = None
    page = None