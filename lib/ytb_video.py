
import re
import time
import traceback
import datetime as dt
from zoneinfo import ZoneInfo
import json

def fetch_video_status(video):
    if video.get('status') == 'VIDEO_STATUS_PROCESSED' and video.get('visibility').get('effectiveStatus') == 'VIDEO_VISIBILITY_STATUS_USER_CONFIG' \
    and video.get('videoPrechecks').get('brandSafetyPrechecksDone') and video.get('videoPrechecks').get('copyrightPrechecksDone') and 'videoDurationMs' in video:
        return 'processed'
    return 'processing'

def switch_account(page, channel_username):
    try:
        print("click avatar")
        avatar = page.locator('//*[@id="avatar-btn"]')
        if avatar.count() == 0:
            account_btn = page.locator('//*[@id="account-button"]')
            if account_btn.count() == 0:
                print("Không tìm thấy nút tài khoản.")
                
                return False
            account_btn.click()
        else:
            avatar.click()
        print("click dropdown")
        time.sleep(2)
        dropdown = page.locator('tp-yt-iron-dropdown')
                    # chờ dropdown mở

        item = dropdown.locator('#primary-text-container').nth(2)  # 0-based → phần tử thứ 3
        #item.scroll_into_view_if_needed()

        item.click()
        print("click switch account")
        time.sleep(5)
    
        account_locator = page.locator("ytd-account-item-section-renderer").get_by_text(channel_username)
        account_locator.click() # Để click vào phần tử
        
        print("click account")
        ### click upload btn
        time.sleep(10)
        return True
    except Exception as e:
        print(f"switch_account error: {e}")
        traceback.print_exc()
        return False    

def capture_list_video(page, url_pattern):
    pattern = re.compile(url_pattern) if isinstance(url_pattern, str) else url_pattern
    results = []

    def on_response(resp):
        
        if (resp.url == url_pattern):
            req = resp.request  # the Request that produced this Response
            # Original response payload
            try:
                original_body = resp.json()
            except Exception:
                original_body = resp.text()
            results.append(original_body)
            # Replay the same request using the context-bound API client that shares cookies
            # with the page. Passing the Request object clones URL/method/headers/body.
            
            #print(f"replay body: {replay_body}")
            
    page.on("response", on_response)
    return results


def fetch_list_video(page):
    try:
        data_video = capture_list_video(page,'https://studio.youtube.com/youtubei/v1/creator/list_creator_videos?alt=json')
        menu_video = page.locator('//a[@id="menu-item-1" and @role="menuitem"]')
        if menu_video.count() == 0:
            print("Menu video not found.")
            return False
            
        menu_video.click()
        page.wait_for_timeout(30000)
        if len(data_video) > 0:
            data_video_first = data_video[0]
            if 'videos' in data_video_first:
                return data_video_first['videos']
            
        return []
    except Exception as e:
        print(f"fetch_list_video error: {e}")
        traceback.print_exc()
        return False

def fetch_lastest_schedule_video(list_video):
    if list_video and len(list_video) > 0:
        first_video = list_video[0]
        print(f"First video data: {first_video.get('videoId')}")
        if 'scheduledPublishingDetails' in first_video:
            print("Found scheduledPublishingDetails")
            schedule_time = first_video.get('scheduledPublishingDetails').get('scheduledPublishings')
            if schedule_time:
                timestamp_schedule =  int(schedule_time[0].get('scheduledTimeSeconds'))
                return dt.datetime.fromtimestamp(timestamp_schedule)
        if 'timePublishedSeconds' in first_video:
            published_time = first_video.get('timePublishedSeconds')
            if published_time:
                return dt.datetime.fromtimestamp(int(published_time))
    print("No scheduled or published time found, returning current time.")
    return dt.datetime.now()


def get_next_slot(reference_dt: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
        """Return the next upload slot (07:00, 10:00, 12:00, 19:00, 20:00, 22:00) in the given timezone."""
        ref = reference_dt.astimezone(tz) if reference_dt.tzinfo else reference_dt.replace(tzinfo=tz)
        day = ref.date()
        hours = (7, 10, 12, 19, 20, 22)

        # tìm slot hôm nay > ref, nếu không có thì trả slot đầu tiên của ngày mai
        return next(
            (dt.datetime.combine(day, dt.time(h), tzinfo=tz)
            for h in hours
            if ref < dt.datetime.combine(day, dt.time(h), tzinfo=tz)),
            dt.datetime.combine(day + dt.timedelta(days=1), dt.time(hours[0]), tzinfo=tz)
        )

def get_time_schedule(latest_video_time):
    tz = ZoneInfo("Asia/Bangkok")
    
    if latest_video_time is None:
        reference_time = dt.datetime.now(tz)
    else:
        print("Latest video effective publish time:", latest_video_time)
        reference_time = latest_video_time

    next_slot = get_next_slot(reference_time, tz)
    now = dt.datetime.now(tz)
    if next_slot <= now:
        next_slot = get_next_slot(now, tz)
    # Convert next slot to UTC RFC3339 format
    slot_utc = next_slot.astimezone(ZoneInfo("Asia/Bangkok"))
    #slot_utc = next_slot.astimezone(dt.timezone.utc)
    return slot_utc

if __name__ == "__main__":
    with open("list_video.json", "r", encoding="utf-8") as f:
        list_video = json.load(f)
    
    first_list_video = list_video['videos']
    lastest_schedule = fetch_lastest_schedule_video(first_list_video)
    print(f"lastest_schedule: {lastest_schedule}")
    publish_time = get_time_schedule(lastest_schedule)
    print(f"Next scheduled upload time (UTC): {publish_time.isoformat()}")