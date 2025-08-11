#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
extract_chapters.py

Extracts chapter metadata from a 69shuba catalog page.

Usage
-----
  # From a URL
  python extract_chapters.py --url "https://www.69shuba.com/book/49983.htm"

  # From a local HTML file
  python extract_chapters.py catalog.html

  # From stdin
  curl -s https://www.69shuba.com/book/49983.htm | python extract_chapters.py
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from time import sleep

import requests
from bs4 import BeautifulSoup


def parse_chapters(html: str):
    """Return a list of {'chaper_name': int, 'chaper_id': int} dicts."""
    soup = BeautifulSoup(html, "html.parser")
    out = []

    for li in soup.select("li[data-num]"):
        chaper_name = int(li["data-num"])

        a_tag = li.find("a", href=True)
        if not a_tag:
            continue
        m = re.search(r"/(\d+)(?:/)?$", a_tag["href"].strip())
        if not m:
            continue
        chaper_id = int(m.group(1))

        out.append({"chaper_name": chaper_name, "chaper_id": chaper_id})

    out.sort(key=lambda x: x["chaper_name"])
    
    return out


def fetch_url(url: str) -> str:
    """
    Download *url* using a browser-like header set (no Cookie),
    return the HTML as text.
    """
    # -- Convert "Thu, 27 Mar 2025 07:53:42 GMT" to current RFC-1123 date
    #    if you want to keep the If-Modified-Since fresh every run:
    ims = datetime.datetime(2025, 3, 27, 7, 53, 42)
    ims_hdr = ims.strftime("%a, %d %b %Y %H:%M:%S GMT")

    headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    #"Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Priority": "u=0, i",
    "Sec-CH-UA": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "Sec-CH-UA-Arch": "\"x86\"",
    "Sec-CH-UA-Bitness": "\"64\"",
    "Sec-CH-UA-Full-Version": "\"138.0.7204.101\"",
    "Sec-CH-UA-Full-Version-List": "\"Not)A;Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"138.0.7204.101\", \"Google Chrome\";v=\"138.0.7204.101\"",
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Model": "\"\"",
    "Sec-CH-UA-Platform": "\"Windows\"",
    "Sec-CH-UA-Platform-Version": "\"15.0.0\"",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",

    "Referer": "https://www.69shuba.com/book/88724.htm"
}

# ─────────────── cookies (viết dạng dict cho rõ ràng) ─────────────── #
    cookies = {
        "_ga": "GA1.1.842094013.1747818848",
        "zh_choose": "s",
        "cf_clearance": "ImoZA.9uFFtaYPPHmr_4.wZbi6R9ETMgiIgJ_DOSyfc-1753171511-1.2.1.1-4_wgTyIDCTViPzc.S83fJ29mZKDmFliPmgjn8bUakd77IXwl.Kou67h1A0jpkratrcOPpAC0Kr7Ay9Rne1ZIoMYHXuJnyXhcl0U7Nm56eKxV7PcZPbTWCut7XauEuTSa6ooaVyTkCdGkIpbqBuVbbam.rvMq_DP4D8CV.L4csr5.Pa2t3JAqidbyxQMxeMde4j5EWB9yjceHw2isvHRDs6Vb7h03mvC7AwCtZjWyqps",
        "shuba": "4987-11628-21997-4466",
        "_ym_uid": "1753171652757917886",
        "_ym_uid_cst": "zix7LPQsHA==",
        "_lr_retry_request": "true",
        "_lr_env_src_ats": "false",
        "_sharedID": "b9845997-d6a5-43f1-9f48-f3b3b22d378f",
        "_sharedID_cst": "zix7LPQsHA==",
        "jieqiHistory": "88724-39943182-%25u7B2C1%25u7AE0%2520%25u767E%25u4E16%25u4E66-1753171986",
        "_ga_04LTEL5PWY": "GS2.1.s1753171513$o3$g1$t1753171986$j57$l0$h0"
    } 
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=15)
    print(resp.content)
    resp.raise_for_status()
    #resp.encoding = resp.apparent_encoding or "utf-8"
    raw = resp.content 
    meta_match = (
        b'<meta' in raw and
        re.search(rb'charset=["\']?([\w-]+)', raw, flags=re.I)
    )
    if meta_match:
        enc = meta_match.group(1).decode().lower()
    else:
        enc = None

    # 2️⃣ Pick the best encoding
    for candidate in (enc, resp.apparent_encoding, "gb18030"):
        if not candidate:
            continue
        try:
            html = raw.decode(candidate, errors="strict")
            break
        except UnicodeDecodeError:

            continue
    else:
        # last-ditch: replace errors just so we don’t crash
        html = raw.decode("gb18030", errors="replace")

    return html


def extract_txtnav_text(html: str) -> str:
    """
    Return plain text inside <div class="txtnav"> after removing:
      • <h1 class="hide720">
      • <div class="txtinfo ...">
      • <div id="txtright">
    Keeps line-breaks where <br> tags occur.
    """
    soup = BeautifulSoup(html, "html.parser")
    nav = soup.find("div", class_="txtnav")
    if nav is None:
        return ""

    # Remove the unwanted nodes (they may occur zero or more times)
    for selector in ("h1.hide720", "div.txtinfo", "div#txtright"):
        for tag in nav.select(selector):
            tag.decompose()          # delete from tree

    # Convert <br> to newline, strip leading/trailing whitespace.
    text = nav.get_text(separator="\n", strip=True)

    # Optional: strip out the &emsp; (U+2003) indent that 69shuba uses
    text = text.replace("\u2003", "")

    return text

def main():
    parser = argparse.ArgumentParser(
        description="Extract chapter numbers and IDs from a 69shuba catalog page"
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--url", "-u", help="URL of the catalog page")
    g.add_argument(
        "html_file",
        nargs="?",
        help="Path to an HTML file (reads from stdin if omitted)",
    )
    args = parser.parse_args()

    if args.url:
        html = fetch_url(args.url)
    elif args.html_file:
        html = Path(args.html_file).read_text(encoding="utf-8")
    else:
        html = sys.stdin.read()

    data = parse_chapters(html)
    book_id = re.search(r"/book/(\d+)/?", args.url).group(1)   # "49983" (string)
    # If you want it as an int →
    book_id = int(book_id) 
    if(len(data) > 0):

        for chaper in data:
            
            print(f"chaper name: {chaper['chaper_name']} - chaper id: {chaper['chaper_id']}")
            chaper_link = f"https://www.69shuba.com/txt/{book_id}/{chaper['chaper_id']}"
            html_chaper = fetch_url(chaper_link)
          
            BAD_INDENT = "\u2003\u3000\ue5e5"
            _indent_re = re.compile(rf"^[{BAD_INDENT}]+", flags=re.MULTILINE)

            chaper_text = extract_txtnav_text(html_chaper)
            chaper_text = _indent_re.sub("", chaper_text)
            chaper_text = chaper_text.replace("(本章完)","")
            print(chaper_text)
            with open(f"{book_id}.txt", "a", encoding="utf-8") as f:
                f.write(chaper_text)
            sleep(1)
    #print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    #python .\download_story.py --url https://www.69shuba.com/book/85454/
    main()
