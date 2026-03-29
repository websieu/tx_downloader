import os
import re
from time import sleep
import traceback


from go_login_auto import ManageDriver
from lib.utils import GL_PROFILE, GO_LOGIN_TOKEN, REMOTE_PORT


def start_fetch_book_novel543(url, retry_attempt=0, start_chapter=1, existing_text=""):
    try:
       # url = 'https://www.novel543.com/0924648104/'
        m = re.search(r"/(\d+)/?$", url)
        book_id = m.group(1) if m else None
        if not book_id:
            print("Book ID not found in URL")
            return False
        fetch_url = 'https://www.novel543.com/' + book_id + '/'
        os.makedirs(f"projects/{book_id}", exist_ok=True)
        output_file = f"projects/{book_id}/{book_id}.txt"
        if(os.path.exists(output_file) and retry_attempt == 0):
            print(f"File {output_file} already exists. Skipping fetch.")
            return True
        # token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NDljMTNlYWM3ZDdkNDJhNDI3ZWYyZGEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2NTJiYmQzMDRjOWNjMGUwNDliYjU0MWYifQ.kyKlIkpusfvd4BhHzjBQymYDkd40w1-PPotSKxy_IPE'
        # port = 3800
        md = ManageDriver(gl_token=GO_LOGIN_TOKEN, port=REMOTE_PORT)
        md.start_gl(gl_profile=GL_PROFILE)
        rs_driver = md.create_driver(fetch_url)
        if not rs_driver:
            print("Failed to create driver.")
            md.close_all()
            return False
        # Wait until Cloudflare challenge is gone
        max_wait = 10*60
        elapsed = 0
        indicators = (
            "cloudflare",
            "checking your browser",
            "just a moment",
            "verify you are human",
            "cf-browser-verification",
        )

        while True:
            try:
                
                body_text = md.driver.page.locator("body").inner_text().lower()
                print("Fetched body text for Cloudflare check.")
                print(body_text[:100])  # Print first 100 characters for debugging
            except Exception as e:
                print(f"Failed to get body text from the page: {e}")
                # If we can't get body text, wait and try again without reloading
                sleep(10)
                elapsed += 10
                if elapsed >= max_wait:
                    print("Timeout waiting for Cloudflare protection to clear.")
                    break
                continue

            if not any(token in body_text for token in indicators):
                print("Cloudflare challenge cleared.")
                break

            print("Waiting for Cloudflare to finish...")
            sleep(10)
            elapsed += 10

            # Try to reload page periodically, but handle crashes gracefully
            # if elapsed % 60 == 0:  # Changed from 30 to 60 seconds to be less aggressive
            #     try:
            #         print("Attempting to reload page...")
            #         md.driver.page.reload(wait_until="domcontentloaded") # Chờ DOM tải xong
                    
            #         # QUAN TRỌNG: Chờ thêm một chút hoặc chờ một element cụ thể
            #         # để đảm bảo context đã ổn định
            #         md.driver.page.wait_for_load_state("networkidle", timeout=10000) 
            #         sleep(5)  # Wait a bit after reload
            #     except Exception as reload_error:
            #         print(f"Failed to reload page: {reload_error}")
            #         # Don't break, just continue without reloading
            
            if elapsed >= max_wait:
                print("Timeout waiting for Cloudflare protection to clear.")
                break
        #sleep(45)  # Chờ 45 giây để trang tải xong
        
        # Prepare arguments for JavaScript
        js_args = {
            "startChapter": start_chapter,
            "existingText": existing_text
        }
        
        # Execute JavaScript with arguments
        try:
            js_code = open("js/fetch_novel.js", "r", encoding="utf-8").read()
            result = md.driver.page.evaluate(js_code, {"args": js_args})
            if result is None:
                print("JavaScript returned None result.")
                md.close_all()
                if retry_attempt < 10:
                    print(f"Retrying due to JS error... (attempt {retry_attempt + 1}/10)")
                    #sleep(60)  # Wait longer before retry
                    return start_fetch_book_novel543(url, retry_attempt + 1, start_chapter, existing_text)
                else:
                    print("Max retries exceeded due to JS execution errors.")
                    return False
            print("JavaScript result:", result)
        except Exception as js_error:
            print(f"JavaScript execution failed: {js_error}")
            md.close_all()
            
            # If this is a retry and we have existing text, save it
            if retry_attempt > 0 and existing_text:
                print("Saving existing text from previous attempts...")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(existing_text)
            
            # Retry if we haven't exceeded max retries
            if retry_attempt < 10:
                print(f"Retrying due to JS error... (attempt {retry_attempt + 1}/10)")
                sleep(60)  # Wait longer before retry
                return start_fetch_book_novel543(url, retry_attempt + 1, start_chapter, existing_text)
            else:
                print("Max retries exceeded due to JS execution errors.")
                return False
        
        if isinstance(result, dict):
            status = result.get("status", "error")
            text = result.get("text", "")
            current_chapter = result.get("currentChapter", 0)
            error_msg = result.get("error", "")
            
            # Log thông tin duplicate chapters từ catalog API
            original_max = result.get("originalMaxChapter", 0)
            actual_max = result.get("actualMaxChapter", 0)
            has_duplicates = result.get("hasDuplicates", False)
            duplicate_info = result.get("duplicateInfo", None)
            skip_chapters = result.get("skipChapters", [])
            
            print("=" * 60)
            print("CHAPTER INFO FROM CATALOG API")
            print("=" * 60)
            print(f"Original max chapter (from DOM): {original_max}")
            print(f"Actual max chapter (after dedup): {actual_max}")
            print(f"Has duplicate chapters: {has_duplicates}")
            if has_duplicates and duplicate_info:
                print(f"⚠️  DUPLICATE CHAPTERS DETECTED!")
                print(f"  - Original count: {duplicate_info.get('originalCount', 0)}")
                print(f"  - Valid count: {duplicate_info.get('validCount', 0)}")
                print(f"  - Unique count: {duplicate_info.get('uniqueCount', 0)}")
                print(f"  - Duplicate count: {duplicate_info.get('duplicateCount', 0)}")
                print(f"  - First duplicate at index: {duplicate_info.get('firstDuplicateIndex', 0)}")
                print(f"  - First duplicate name: {duplicate_info.get('firstDuplicateName', '')}")
            if skip_chapters:
                print(f"⏭️  SKIPPED UNAPPROVED CHAPTERS: {len(skip_chapters)}")
                print(f"  - Skipped indices: {skip_chapters}")
            print("=" * 60)
            
            # Ghép text mới với existing_text (nếu có) - Python xử lý việc ghép
            if existing_text and text:
                combined_text = existing_text + "\n\n" + text
            else:
                combined_text = text if text else existing_text
            
            if status == "error":
                print(f"Error occurred at chapter {current_chapter}: {error_msg}")
                md.close_all()
                
                # Retry if we haven't exceeded max retries
                if retry_attempt < 10:
                    print(f"Retrying... (attempt {retry_attempt + 1}/10)")
                    sleep(30)  # Wait before retry
                    # current_chapter là chapter cuối cùng đã hoàn thành ĐẦY ĐỦ
                    # Retry từ chapter tiếp theo
                    return start_fetch_book_novel543(url, retry_attempt + 1, current_chapter + 1, combined_text)
                else:
                    print("Max retries exceeded. Saving partial content.")
                    if combined_text:
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(combined_text)
                    return False
            elif status == "success":
                print("Successfully fetched complete novel")

                from lib.chapter_validator import validate_chapters
                skip_chapter_count = len(skip_chapters) if skip_chapters else 0
                validation = validate_chapters(
                    combined_text,
                    expected_count=actual_max,
                    source="novel543",
                    tolerance=3,
                    skip_count=skip_chapter_count
                )
                if validation["duplicate_titles"]:
                    from lib.chapter_validator import remove_duplicate_chapters
                    combined_text, removed = remove_duplicate_chapters(combined_text, source="novel543")
                    if removed:
                        from lib.telegram import send_telegram_message
                        send_telegram_message(f"[novel543] Auto-removed {len(removed)} duplicate chapter(s)")
                if not validation["is_valid"]:
                    msg = f"[novel543] Chapter validation FAILED\n{validation['missing_info']}"
                    print(f"WARNING: {msg}")
                    from lib.telegram import send_telegram_message
                    send_telegram_message(msg)

                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(combined_text)
                sleep(30)
                md.close_all()
                return True
            else:
                print("Unknown status received")
                md.close_all()
                return False
        else:
            # Handle legacy string response
            data = str(result)
            if data == "error":
                print("error fetch data")
                md.close_all()
                return False
              # Chờ thêm 30 giây để đảm bảo trang đã tải xong
            md.close_all()
            return False
    except Exception as e:
        print("An error occurred while fetching the book:")
        #print(e)
        traceback.print_exc()
        if md:
            md.close_all()
        return False

def remove_lines_with_warning(file_path: str) -> int:
    """
    Xóa mọi dòng chứa '溫馨提示:' trong file, lưu lại vào chính file đó.
    Trả về tổng số dòng đã phát hiện và xóa bỏ.
    """
    marker = "溫馨提示:"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        removed = 0
        kept_lines = []
        for line in lines:
            if marker in line:
                removed += 1
            else:
                kept_lines.append(line)

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(kept_lines)

        return removed
    except Exception:
        traceback.print_exc()
        return 0

def run_fetch_and_clean_novel543(url):
    if start_fetch_book_novel543(url):
        book_id = re.search(r"/(\d+)/?$", url).group(1)
        file_path = f"projects/{book_id}/{book_id}.txt"
        removed_count = remove_lines_with_warning(file_path)
        print(f"Removed {removed_count} lines containing warnings from {file_path}")
        return True
    else:
        print("Failed to fetch the book.")
        return False

if __name__ == "__main__":
    run_fetch_and_clean_novel543("https://www.novel543.com/1212300359/")