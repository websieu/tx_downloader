"""
Biquge Novel Downloader Package
Download novels from biquge.tw
"""

from .biquge_novel import (
    BiqugeNovel,
    start_fetch_book_biquge,
    run_fetch_and_clean_biquge,
    remove_ads_from_file,
)

__all__ = [
    'BiqugeNovel',
    'start_fetch_book_biquge',
    'run_fetch_and_clean_biquge',
    'remove_ads_from_file',
]
