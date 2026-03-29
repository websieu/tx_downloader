"""
BiqugeNovel - Download novels from biquge.tw
Similar structure to go_login_auto.py and novel543.py
"""

import os
import re
from time import sleep
import traceback
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from go_login_auto import ManageDriver
from lib.utils import GL_PROFILE, GO_LOGIN_TOKEN, REMOTE_PORT


class BiqugeNovel:
    """
    Class to download novels from biquge.tw website
    """
    
    BASE_URL = "https://www.biquge.tw"
    
    def __init__(self, gl_token=None, port=None, gl_profile=None):
        """
        Initialize BiqugeNovel downloader
        
        Args:
            gl_token: GoLogin token (uses config if not provided)
            port: Remote port (uses config if not provided)
            gl_profile: GoLogin profile ID (uses config if not provided)
        """
        self.gl_token = gl_token or GO_LOGIN_TOKEN
        self.port = port or REMOTE_PORT
        self.gl_profile = gl_profile or GL_PROFILE
        self.md = None
    
    def _extract_book_id(self, url: str) -> str:
        """
        Extract book ID from URL
        
        Args:
            url: Book URL (e.g., https://www.biquge.tw/book/1138317/)
            
        Returns:
            Book ID as string, or None if not found
        """
        m = re.search(r"/book/(\d+)/?", url)
        return m.group(1) if m else None
    
    def _extract_chapter_id(self, href: str) -> str:
        """
        Extract chapter ID from href
        
        Args:
            href: Chapter href (e.g., /book/1138317/80502506.html)
            
        Returns:
            Chapter ID as string, or None if not found
        """
        m = re.search(r"/(\d+)\.html$", href)
        return m.group(1) if m else None
    
    def _init_driver(self, url: str) -> bool:
        """
        Initialize GoLogin and browser driver
        
        Args:
            url: URL to navigate to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.md = ManageDriver(gl_token=self.gl_token, port=self.port)
            self.md.start_gl(gl_profile=self.gl_profile)
            return self.md.create_driver(url)
        except Exception as e:
            print(f"Error initializing driver: {e}")
            traceback.print_exc()
            return False
    
    def _close_driver(self):
        """Close the browser and GoLogin"""
        if self.md:
            try:
                self.md.close_all()
            except Exception as e:
                print(f"Error closing driver: {e}")
            self.md = None
    
    def _try_click_cloudflare_checkbox(self):
        """
        Try to click the Cloudflare checkbox if present
        """
        try:
            # Try multiple selectors for Cloudflare checkbox
            checkbox_selectors = [
                # Turnstile checkbox iframe
                "iframe[src*='challenges.cloudflare.com']",
                "iframe[title*='Cloudflare']",
                "iframe[title*='challenge']",
                # Direct checkbox selectors
                "#cf-turnstile-response",
                ".cf-turnstile",
                "input[type='checkbox']",
            ]
            
            for selector in checkbox_selectors:
                try:
                    element = self.md.driver.page.locator(selector).first
                    if element.count() > 0:
                        print(f"Found Cloudflare element: {selector}")
                        
                        # If it's an iframe, we need to interact with it
                        if "iframe" in selector:
                            frame = element.content_frame()
                            if frame:
                                # Try to find and click checkbox inside iframe
                                checkbox = frame.locator("input[type='checkbox'], .ctp-checkbox-label, #challenge-stage")
                                if checkbox.count() > 0:
                                    checkbox.first.click()
                                    print("Clicked checkbox inside iframe")
                                    sleep(3)
                                    return True
                                # Try clicking the iframe itself
                                element.click()
                                print("Clicked iframe")
                                sleep(3)
                                return True
                        else:
                            element.click()
                            print(f"Clicked element: {selector}")
                            sleep(3)
                            return True
                except Exception as e:
                    continue
            
            # Try clicking in the center of the page where checkbox usually appears
            try:
                # Cloudflare checkbox is often in a specific position
                self.md.driver.page.mouse.click(200, 300)
                print("Clicked at position (200, 300)")
                sleep(2)
            except:
                pass
                
            return False
        except Exception as e:
            print(f"Error trying to click Cloudflare checkbox: {e}")
            return False

    def _wait_for_page_load(self, max_wait: int = 600) -> bool:
        """
        Wait for page to load and bypass any protection
        
        Args:
            max_wait: Maximum wait time in seconds
            
        Returns:
            True if page loaded successfully
        """
        elapsed = 0
        indicators = (
            "cloudflare",
            "checking your browser",
            "just a moment",
            "verify you are human",
            "cf-browser-verification",
            "turnstile",
        )
        
        last_checkbox_attempt = 0
        
        while elapsed < max_wait:
            try:
                body_text = self.md.driver.page.locator("body").inner_text().lower()
                print(f"Page text (first 200 chars): {body_text[:200]}")
                
                if not any(token in body_text for token in indicators):
                    print("Page loaded successfully.")
                    return True
                
                # Try to click checkbox every 10 seconds
                if elapsed - last_checkbox_attempt >= 10:
                    print("Detected Cloudflare protection, trying to click checkbox...")
                    self._try_click_cloudflare_checkbox()
                    last_checkbox_attempt = elapsed
                    
            except Exception as e:
                print(f"Error checking page: {e}")
            
            print(f"Waiting for page to load... ({elapsed}s / {max_wait}s)")
            sleep(5)
            elapsed += 5
        
        print("Timeout waiting for page to load.")
        return False
    
    def start_fetch_book(self, url: str, retry_attempt: int = 0, 
                         start_chapter: int = 1, existing_text: str = "") -> bool:
        """
        Main method to fetch and download a book from biquge.tw
        
        Args:
            url: Book URL (e.g., https://www.biquge.tw/book/1138317/)
            retry_attempt: Current retry attempt number
            start_chapter: Chapter to start from (for resume)
            existing_text: Already downloaded text (for resume)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract book ID from URL
            book_id = self._extract_book_id(url)
            if not book_id:
                print("Book ID not found in URL")
                return False
            
            # Prepare paths
            fetch_url = f"{self.BASE_URL}/book/{book_id}/"
            os.makedirs(f"projects/{book_id}", exist_ok=True)
            output_file = f"projects/{book_id}/{book_id}.txt"
            
            # Check if already downloaded
            if os.path.exists(output_file) and retry_attempt == 0:
                print(f"File {output_file} already exists. Skipping fetch.")
                return True
            
            # Initialize driver
            if not self._init_driver(fetch_url):
                print("Failed to create driver.")
                self._close_driver()
                return False
            
            # Wait for page to load
            if not self._wait_for_page_load():
                print("Page did not load properly.")
                self._close_driver()
                return False
            
            # Prepare JS arguments
            js_args = {
                "startChapter": start_chapter,
                "existingText": existing_text,
                "bookId": book_id
            }
            
            # Execute JavaScript to fetch chapters
            try:
                js_path = os.path.join(os.path.dirname(__file__), "fetch_biquge.js")
                js_code = open(js_path, "r", encoding="utf-8").read()
                result = self.md.driver.page.evaluate(js_code, {"args": js_args})
                
                if result is None:
                    print("JavaScript returned None result.")
                    self._close_driver()
                    if retry_attempt < 10:
                        print(f"Retrying due to JS error... (attempt {retry_attempt + 1}/10)")
                        return self.start_fetch_book(url, retry_attempt + 1, start_chapter, existing_text)
                    return False
                    
            except Exception as js_error:
                print(f"JavaScript execution failed: {js_error}")
                traceback.print_exc()
                self._close_driver()
                
                # Save existing text if available
                if retry_attempt > 0 and existing_text:
                    print("Saving existing text from previous attempts...")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(existing_text)
                
                # Retry
                if retry_attempt < 10:
                    print(f"Retrying... (attempt {retry_attempt + 1}/10)")
                    sleep(30)
                    return self.start_fetch_book(url, retry_attempt + 1, start_chapter, existing_text)
                
                print("Max retries exceeded.")
                return False
            
            # Process result
            if isinstance(result, dict):
                status = result.get("status", "error")
                text = result.get("text", "")
                current_chapter = result.get("currentChapter", 0)
                error_msg = result.get("error", "")
                
                # Ghép text mới với existing_text (nếu có) - Python xử lý việc ghép
                if existing_text and text:
                    combined_text = existing_text + "\n\n" + text
                else:
                    combined_text = text if text else existing_text
                
                if status == "error":
                    print(f"Error at chapter {current_chapter}: {error_msg}")
                    self._close_driver()
                    
                    if retry_attempt < 10:
                        print(f"Retrying... (attempt {retry_attempt + 1}/10)")
                        sleep(30)
                        # current_chapter là chapter cuối cùng đã hoàn thành ĐẦY ĐỦ
                        # Retry từ chapter tiếp theo
                        return self.start_fetch_book(url, retry_attempt + 1, current_chapter + 1, combined_text)
                    
                    # Save partial content
                    if combined_text:
                        print("Saving partial content...")
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(combined_text)
                    return False
                    
                elif status == "success":
                    print("Successfully fetched complete novel!")

                    from lib.chapter_validator import validate_chapters
                    total_chapters = result.get("totalChapters", 0)
                    validation = validate_chapters(
                        combined_text,
                        expected_count=total_chapters,
                        source="biquge",
                        tolerance=3
                    )
                    if validation["duplicate_titles"]:
                        from lib.chapter_validator import remove_duplicate_chapters
                        combined_text, removed = remove_duplicate_chapters(combined_text, source="biquge")
                        if removed:
                            from lib.telegram import send_telegram_message
                            send_telegram_message(f"[biquge] Auto-removed {len(removed)} duplicate chapter(s)")
                    if not validation["is_valid"]:
                        msg = f"[biquge] Chapter validation FAILED\n{validation['missing_info']}"
                        print(f"WARNING: {msg}")
                        from lib.telegram import send_telegram_message
                        send_telegram_message(msg)

                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(combined_text)
                    self._close_driver()
                    return True
                    
                else:
                    print(f"Unknown status: {status}")
                    self._close_driver()
                    return False
            else:
                print("Unexpected result format")
                self._close_driver()
                return False
                
        except Exception as e:
            print(f"Error fetching book: {e}")
            traceback.print_exc()
            self._close_driver()
            return False


def start_fetch_book_biquge(url: str, retry_attempt: int = 0, 
                            start_chapter: int = 1, existing_text: str = "") -> bool:
    """
    Convenience function to fetch a book from biquge.tw
    Similar to start_fetch_book in go_login_auto.py
    
    Args:
        url: Book URL
        retry_attempt: Current retry attempt
        start_chapter: Starting chapter (for resume)
        existing_text: Existing text (for resume)
        
    Returns:
        True if successful, False otherwise
    """
    downloader = BiqugeNovel()
    return downloader.start_fetch_book(url, retry_attempt, start_chapter, existing_text)


def run_fetch_and_clean_biquge(url: str) -> bool:
    """
    Fetch book and clean up the result
    Similar to run_fetch_and_clean_novel543 in novel543.py
    
    Args:
        url: Book URL
        
    Returns:
        True if successful, False otherwise
    """
    result = start_fetch_book_biquge(url)
    
    if result:
        # Extract book ID for file path
        m = re.search(r"/book/(\d+)/?", url)
        if m:
            book_id = m.group(1)
            output_file = f"projects/{book_id}/{book_id}.txt"
            if os.path.exists(output_file):
                removed = remove_ads_from_file(output_file)
                print(f"Removed {removed} ad lines from file.")
    
    return result


def remove_ads_from_file(file_path: str) -> int:
    """
    Remove advertisement lines from the downloaded file
    
    Args:
        file_path: Path to the file
        
    Returns:
        Number of lines removed
    """
    ad_markers = [
        "請記住本書首發域名",
        "筆趣閣",
        "biquge",
        "手機版閱讀網址",
        "最新章節",
        "www.",
        ".com",
        ".tw",
    ]
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        removed = 0
        kept_lines = []
        
        for line in lines:
            line_lower = line.lower()
            if any(marker.lower() in line_lower for marker in ad_markers):
                removed += 1
            else:
                kept_lines.append(line)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(kept_lines)
        
        return removed
        
    except Exception as e:
        print(f"Error removing ads: {e}")
        return 0


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        book_url = sys.argv[1]
    else:
        book_url = "https://www.biquge.tw/book/1138317/"
    
    print(f"Fetching book from: {book_url}")
    success = run_fetch_and_clean_biquge(book_url)
    print(f"Result: {'Success' if success else 'Failed'}")
