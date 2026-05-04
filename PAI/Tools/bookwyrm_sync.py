#!/usr/bin/env python3
"""
Bookwyrm RSS → BOOKS.md sync

Pulls recently read books, reading queue, and 5-star recommendations from a
BookWyrm user's RSS feeds and updates PAI/USER/TELOS/BOOKS.md.

Configuration is read from the PAI .env file.  Required variables:

    BOOKWYRM_SERVER=https://bookrastinating.com
    BOOKWYRM_USER=ktneely
    BOOKWYRM_READ_LIMIT=8
    BOOKWYRM_QUEUE_LIMIT=5
    BOOKWYRM_REC_LIMIT=8

Usage:
    python bookwyrm_sync.py [--dry-run]
"""

import argparse
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


def load_env():
    """Load .env from PAI_DIR, falling back to script-relative paths."""
    env = {}
    # Try PAI_DIR/.env first
    pai_dir = os.environ.get("PAI_DIR", "")
    if pai_dir:
        env_path = Path(pai_dir) / ".env"
    else:
        # Fallback: walk up from script location looking for .env
        script_dir = Path(__file__).resolve().parent
        for parent in [script_dir] + list(script_dir.parents):
            candidate = parent / ".env"
            if candidate.exists():
                env_path = candidate
                break
        else:
            print("WARNING: No .env file found", file=sys.stderr)
            return env

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()

    return env


def load_config(env):
    """Build config dict from environment variables."""
    server = env.get("BOOKWYRM_SERVER", "")
    user = env.get("BOOKWYRM_USER", "")

    if not server or not user:
        print(
            "ERROR: BOOKWYRM_SERVER and BOOKWYRM_USER must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "server": server.rstrip("/"),
        "user": user,
        "read_limit": int(env.get("BOOKWYRM_READ_LIMIT", "8")),
        "queue_limit": int(env.get("BOOKWYRM_QUEUE_LIMIT", "5")),
        "rec_limit": int(env.get("BOOKWYRM_REC_LIMIT", "8")),
    }


def find_books_file():
    """Locate BOOKS.md at $PAI_DIR/PAI/USER/TELOS/BOOKS.md."""
    pai_dir = os.environ.get("PAI_DIR", "")
    if pai_dir:
        candidate = Path(pai_dir) / "PAI" / "USER" / "TELOS" / "BOOKS.md"
        if candidate.exists():
            return candidate

    # Fallback: script-relative path
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir.parent / "PAI" / "USER" / "TELOS" / "BOOKS.md"
    if candidate.exists():
        return candidate

    print("ERROR: BOOKS.md not found at $PAI_DIR/PAI/USER/TELOS/BOOKS.md", file=sys.stderr)
    sys.exit(1)


def fetch_rss(url, retries=2):
    """Fetch and parse an RSS feed, returning list of item dicts."""
    req = Request(url, headers={"User-Agent": "PAI-BookwyrmSync/1.0"})
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            break
        except URLError as e:
            if attempt < retries:
                print(f"WARNING: Fetch failed (attempt {attempt+1}), retrying: {e}", file=sys.stderr)
                continue
            print(f"ERROR: Failed to fetch {url}: {e}", file=sys.stderr)
            return []

    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item"):
        title = (item.find("title").text or "").strip()
        link = (item.find("link").text or "").strip()
        pub_date = (item.find("pubDate").text or "").strip()
        description = (item.find("description").text or "").strip()

        # Parse "Author: Title" format (for shelf feeds)
        author = ""
        book_title = title
        if ": " in title:
            parts = title.split(": ", 1)
            author = parts[0].strip()
            book_title = parts[1].strip()

        book_title = book_title.strip("''\"")

        date_str = ""
        try:
            dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = pub_date

        items.append({
            "author": author,
            "title": book_title,
            "date": date_str,
            "link": link,
            "description": description,
        })

    return items


def fetch_reviews(server, user, retries=2):
    """Fetch reviews RSS feed and extract 5-star rated books."""
    url = f"{server}/user/{user}/rss-reviews"
    req = Request(url, headers={"User-Agent": "PAI-BookwyrmSync/1.0"})
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            break
        except URLError as e:
            if attempt < retries:
                print(f"WARNING: Fetch failed (attempt {attempt+1}), retrying: {e}", file=sys.stderr)
                continue
            print(f"ERROR: Failed to fetch {url}: {e}", file=sys.stderr)
            return []

    root = ET.fromstring(raw)
    five_star = []
    review_pattern = re.compile(
        r'Review of\s+"(.+?)"\s+\((\d+)\s+stars?\)(?::\s*(.*))?', re.IGNORECASE
    )

    for item in root.findall(".//item"):
        raw_title = (item.find("title").text or "").strip()
        link = (item.find("link").text or "").strip()
        pub_date = (item.find("pubDate").text or "").strip()
        description = (item.find("description").text or "").strip()

        match = review_pattern.match(raw_title)
        if match:
            book_title = match.group(1).strip()
            stars = int(match.group(2))
            subtitle = match.group(3).strip() if match.group(3) else ""

            if stars == 5:
                review_text = re.sub(r"<[^>]+>", "", description).strip()
                review_text = html.unescape(review_text)
                # Collapse whitespace for table-cell compatibility
                review_text = re.sub(r"\s+", " ", review_text).strip()

                date_str = ""
                try:
                    dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    date_str = pub_date

                five_star.append({
                    "title": book_title,
                    "subtitle": subtitle,
                    "review": review_text,
                    "date": date_str,
                    "link": link,
                })

    return five_star


def _fetch_author_from_book_page(server, book_title, review_link):
    """Try to extract author from the book's page on BookWyrm."""
    review_url = review_link if review_link.startswith("http") else f"{server}{review_link}"
    req = Request(review_url, headers={"User-Agent": "PAI-BookwyrmSync/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except URLError:
        return ""

    book_path_match = re.search(r'href="(/book/\d+/s/[^"]+)"', raw)
    if not book_path_match:
        return ""

    book_url = f"{server}{book_path_match.group(1)}"
    req = Request(book_url, headers={"User-Agent": "PAI-BookwyrmSync/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except URLError:
        return ""

    author_matches = re.findall(r'href="/author/[^"]+"[^>]*>([^<]+)</a>', raw)
    if author_matches:
        return ", ".join(a.strip() for a in author_matches if a.strip())

    title_area = raw.find(book_title.split()[0]) if book_title else -1
    if title_area >= 0:
        chunk = raw[title_area : title_area + 2000]
        text = re.sub(r"<[^>]+>", " ", chunk)
        text = re.sub(r"\s+", " ", text).strip()
        by_match = re.search(r"\bby\s+([A-Z][a-zA-Z\s\.&\-]{2,40})\b", text)
        if by_match:
            return by_match.group(1).strip()

    return ""


def enrich_with_authors(recommendations, read_shelf_books, server=""):
    """Cross-reference recommendations with read shelf for author names.
    Falls back to fetching book pages for older books not in the read shelf."""
    author_map = {}
    for book in read_shelf_books:
        if book["title"] and book["author"]:
            key = book["title"].lower().strip("''\"")
            author_map[key] = book["author"]

    for rec in recommendations:
        key = rec["title"].lower().strip("''\"")
        author = author_map.get(key, "")
        if not author and server:
            author = _fetch_author_from_book_page(server, rec["title"], rec["link"])
        rec["author"] = author

    return recommendations


def update_books_md(filepath, recently_read, reading_queue, recommendations, dry_run=False):
    """Update the Reading Queue, Recently Read, and Recommendations sections."""
    p = Path(filepath)
    if not p.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    content = p.read_text(encoding="utf-8")

    # Build Reading Queue table
    queue_lines = ["| Book | Author | Added |", "|------|--------|-------|"]
    for book in reading_queue:
        queue_lines.append(f"| {book['title']} | {book['author']} | {book['date']} |")

    # Build Recently Read table
    read_lines = ["| Book | Author | Finished |", "|------|--------|----------|"]
    for book in recently_read:
        read_lines.append(f"| {book['title']} | {book['author']} | {book['date']} |")

    # Build Recommendations table
    rec_lines = ["| Book | Author | Why | Review |", "|------|--------|-----|--------|"]
    for rec in recommendations:
        why = rec["subtitle"] if rec["subtitle"] else rec["review"][:80]
        why = why.replace("|", "\\|")
        review = rec["review"].replace("|", "\\|").replace("\n", " ")
        rec_lines.append(f"| {rec['title']} | {rec['author']} | {why} | {review} |")

    # Replace sections (idempotent — any existing table rows are consumed)
    queue_pattern = r"## Reading Queue\n\nBooks you want to read(?: \(synced from BookWyrm\))?:\n\n\|.*(?:\n\|.*)*"
    queue_replacement = (
        "## Reading Queue\n\n"
        "Books you want to read (synced from BookWyrm):\n\n"
        + "\n".join(queue_lines)
    )
    content = re.sub(queue_pattern, queue_replacement, content)

    read_pattern = r"## Recently Read\n\nBooks recently finished(?: \(synced from BookWyrm\))?:\n\n\|.*(?:\n\|.*)*"
    read_replacement = (
        "## Recently Read\n\n"
        "Books recently finished (synced from BookWyrm):\n\n"
        + "\n".join(read_lines)
    )
    content = re.sub(read_pattern, read_replacement, content)

    rec_pattern = r"## Book Recommendations I Give\n\nBooks (?:I've rated 5 stars \(synced from BookWyrm\)|you often recommend to others):\n\n\|.*(?:\n\|.*)*"
    rec_replacement = (
        "## Book Recommendations I Give\n\n"
        "Books I've rated 5 stars (synced from BookWyrm):\n\n"
        + "\n".join(rec_lines)
    )
    content = re.sub(rec_pattern, rec_replacement, content)

    if dry_run:
        print(content)
        return

    p.write_text(content, encoding="utf-8")
    print(f"Updated {filepath}")
    print(f"  Reading Queue: {len(reading_queue)} books")
    print(f"  Recently Read: {len(recently_read)} books")
    print(f"  5-Star Recommendations: {len(recommendations)} books")


def main():
    parser = argparse.ArgumentParser(description="Sync Bookwyrm RSS to BOOKS.md")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing")
    args = parser.parse_args()

    env = load_env()
    cfg = load_config(env)

    server = cfg["server"]
    user = cfg["user"]
    read_limit = cfg["read_limit"]
    queue_limit = cfg["queue_limit"]
    rec_limit = cfg["rec_limit"]

    read_url = f"{server}/user/{user}/books/read/rss"
    to_read_url = f"{server}/user/{user}/books/to-read/rss"

    print(f"Fetching read shelf: {read_url}")
    recently_read = fetch_rss(read_url)[:read_limit]

    print(f"Fetching full read shelf for author lookup...")
    all_read = fetch_rss(read_url)

    print(f"Fetching to-read shelf: {to_read_url}")
    reading_queue = fetch_rss(to_read_url)[:queue_limit]

    print(f"Fetching reviews for 5-star ratings: {server}/user/{user}/rss-reviews")
    recommendations = fetch_reviews(server, user)[:rec_limit]

    recommendations = enrich_with_authors(recommendations, all_read, server)

    books_file = find_books_file()
    update_books_md(
        str(books_file), recently_read, reading_queue, recommendations, dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
