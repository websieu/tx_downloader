from playwright.sync_api import sync_playwright
class Browser:
    def __init__(self, debug="http://127.0.0.1:3500"):
        self.playwright = sync_playwright().start()
        # Connect to the running Chrome instance
        if(not debug.startswith("http")):
            debug = f"http://{debug}"
        browser = self.playwright.chromium.connect_over_cdp(debug)
        
        # Get the existing browser context
        context = browser.contexts[0]
        
        # Open a new tab (page)
        new_page = context.new_page()
        
        # Bring the new tab to the front
        new_page.bring_to_front()
        
        # Navigate to a website
        self.page = new_page
       
    

        # Optionally, close the tab or browser
        # new_page.close()
        # browser.close()  # This will close the entire browser

    def get_cookie(self, cookie_name):
        cookies = self.page.context.cookies()
        cookie = next((c for c in cookies if c['name'] == cookie_name), None)
        return cookie
            
    def close(self):
       self.page.close()
       self.playwright.stop()
            
    
    def goto(self, url):
        self.page.goto(url)
    
    def execute_script(self, script):
        return self.page.evaluate(script)
    
        