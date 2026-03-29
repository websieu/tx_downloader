"""
chapter_validator.py
Shared chapter count validation and duplicate detection for all novel fetching pipelines.
"""
import re
import sys
from difflib import SequenceMatcher


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))


CHAPTER_MARKER_RE = re.compile(
    r'^(?:\d+\.)?[第弟]\s*[\d一二三四五六七八九十百千万零〇]+\s*[章节回集卷](?![\d一二三四五六七八九十百千万零〇])',
    re.MULTILINE
)

CHAPTER_TITLE_RE = re.compile(
    r'^((?:\d+\.)?[第弟]\s*[\d一二三四五六七八九十百千万零〇]+\s*[章节回集卷].*)$',
    re.MULTILINE
)


def count_chapters_in_text(text: str) -> int:
    return len(CHAPTER_MARKER_RE.findall(text))


def extract_chapter_titles(text: str) -> list:
    return CHAPTER_TITLE_RE.findall(text)


def find_duplicate_titles(text: str) -> list:
    titles = extract_chapter_titles(text)
    title_counts = {}
    for title in titles:
        normalized = title.strip()
        title_counts[normalized] = title_counts.get(normalized, 0) + 1
    return [(title, count) for title, count in title_counts.items() if count > 1]


CHAPTER_SPLIT_RE = re.compile(
    r'(?=^(?:\d+\.)?[第弟]\s*[\d一二三四五六七八九十百千万零〇]+\s*[章节回集卷](?![\d一二三四五六七八九十百千万零〇]))',
    re.MULTILINE
)


def remove_duplicate_chapters(text: str, similarity_threshold: float = 0.9,
                              source: str = "unknown"):
    """
    Remove duplicate chapters (same chapter title, >90% similar content).
    Returns (cleaned_text, removed_list).
    """
    chunks = CHAPTER_SPLIT_RE.split(text)

    # First chunk may be preamble (before first chapter marker)
    preamble = ""
    chapter_chunks = []
    for chunk in chunks:
        if CHAPTER_MARKER_RE.match(chunk.strip()):
            chapter_chunks.append(chunk)
        else:
            preamble += chunk

    # Group by chapter title (first line)
    from collections import defaultdict
    groups = defaultdict(list)
    for i, chunk in enumerate(chapter_chunks):
        title_match = CHAPTER_TITLE_RE.match(chunk.strip())
        title = title_match.group(1).strip() if title_match else f"__unknown_{i}"
        groups[title].append((i, chunk))

    kept = set(range(len(chapter_chunks)))  # indices to keep
    removed = []

    for title, occurrences in groups.items():
        if len(occurrences) < 2:
            continue
        # Keep first, compare rest against it
        first_idx, first_chunk = occurrences[0]
        for dup_idx, dup_chunk in occurrences[1:]:
            ratio = SequenceMatcher(None, first_chunk, dup_chunk).ratio()
            if ratio >= similarity_threshold:
                kept.discard(dup_idx)
                removed.append((title, dup_idx, ratio))
                _safe_print(f"[{source}] Removing duplicate: \"{title}\" "
                           f"(index {dup_idx}, similarity {ratio:.1%})")

    if not removed:
        return text, []

    # Rebuild text
    cleaned_chunks = [preamble] + [chapter_chunks[i] for i in sorted(kept)]
    cleaned_text = "".join(cleaned_chunks).strip()

    _safe_print(f"[{source}] Removed {len(removed)} duplicate chapter(s)")
    return cleaned_text, removed


def validate_chapters(text: str, expected_count: int, source: str = "unknown",
                      tolerance: int = 0, skip_count: int = 0):
    found_count = count_chapters_in_text(text)
    duplicates = find_duplicate_titles(text)

    adjusted_expected = expected_count - skip_count

    count_diff = abs(found_count - adjusted_expected)
    count_ok = count_diff <= tolerance
    no_duplicates = len(duplicates) == 0
    is_valid = count_ok and no_duplicates

    issues = []
    if not count_ok:
        issues.append(
            f"Chapter count mismatch: found {found_count} in text, "
            f"expected {adjusted_expected} "
            f"(original: {expected_count}, skipped: {skip_count})"
        )
    if not no_duplicates:
        dup_strs = [f'"{t}" x{c}' for t, c in duplicates[:5]]
        issues.append(f"Duplicate chapters: {', '.join(dup_strs)}")

    missing_info = "; ".join(issues) if issues else "OK"

    _safe_print(f"[{source}] Chapter validation: "
               f"found={found_count}, expected={adjusted_expected}, "
               f"duplicates={len(duplicates)}, valid={is_valid}")
    if not is_valid:
        _safe_print(f"[{source}] Issues: {missing_info}")

    return {
        "is_valid": is_valid,
        "chapter_count_in_text": found_count,
        "expected_chapter_count": adjusted_expected,
        "duplicate_titles": duplicates,
        "missing_info": missing_info
    }
