from lxml import html as lxml_html

def build_rel_xpath(username: str) -> str:
    """
    Tạo XPath tương đối chọn mọi <ytd-account-item-renderer> 
    có chứa text username (ví dụ '@mongtienlo') ở bất kỳ phần tử con nào.
    """
    # normalize-space() để tránh lỗi do khoảng trắng
    # contains() để match một phần (YouTube hiển thị @handle trong <yt-formatted-string>)
    return f"//ytd-account-item-renderer[.//*[contains(normalize-space(), '{username}')]]"

def find_account_items_in_html(html_text: str, username: str):
    """
    Trả về:
      - list_xpath_abs: các XPath tuyệt đối trong cây HTML đã parse (hữu ích để debug/offline)
      - rel_xpath: XPath tương đối dùng trực tiếp cho Playwright/Selenium để click
    """
    tree = lxml_html.fromstring(html_text)
    rel_xpath = build_rel_xpath(username)
    nodes = tree.xpath(rel_xpath)
    list_xpath_abs = [tree.getpath(n) for n in nodes]  # tuyệt đối trong cây parse
    return list_xpath_abs, rel_xpath