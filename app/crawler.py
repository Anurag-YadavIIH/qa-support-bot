# app/crawler.py
# Crawls a website starting from a base URL,
# extracts clean text from each page, and returns
# a list of { url, text } dictionaries.

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict
import time

from app.utils import TARGET_URL, MAX_PAGES


def is_valid_url(url: str, base_domain: str) -> bool:
    """
    Check if a URL belongs to the same domain as the base site.
    
    Why: We don't want to crawl the entire internet —
    only pages on the target website. This keeps us focused.
    
    Example:
      base_domain = "docs.python.org"
      "https://docs.python.org/3/tutorial/" → True  ✅
      "https://google.com"                  → False ❌
    """
    def normalize_host(host: str) -> str:
        host = host.lower().strip()
        return host[4:] if host.startswith("www.") else host

    try:
        parsed = urlparse(url)
        # Must be http/https (not mailto:, javascript:, etc.)
        if parsed.scheme not in ("http", "https"):
            return False

        # Normalize both hosts so www.example.com and example.com are treated
        # as the same site.
        if normalize_host(parsed.netloc) != normalize_host(base_domain):
            return False

        return True
    except Exception:
        return False


def clean_text(soup: BeautifulSoup) -> str:
    """
    Extract clean, readable text from a BeautifulSoup object.
    
    Why: Raw HTML is full of noise — nav menus, ads, footers,
    script tags. We only want the meaningful body text that a
    user would actually read.
    """
    # Remove tags that never contain useful content
    for tag in soup(["script", "style", "nav", "footer",
                     "header", "aside", "form", "noscript"]):
        # decompose() removes the tag AND its contents from the tree
        tag.decompose()

    # get_text() joins all remaining text nodes
    # separator="\n" puts each block on its own line
    # strip=True removes leading/trailing whitespace per element
    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive blank lines
    # Split into lines, remove empty ones, rejoin
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def crawl(start_url: str = TARGET_URL,
          max_pages: int = MAX_PAGES) -> List[Dict[str, str]]:
    """
    Crawl a website starting from start_url.
    Returns a list of dicts: [{ "url": ..., "text": ... }, ...]
    
    How it works:
    - Uses a 'queue' (to_visit) of URLs to process
    - Uses a 'visited' set to avoid re-visiting pages
    - Stops when we've collected max_pages pages
    """

    # Parse the base domain from the starting URL
    # e.g. "https://docs.python.org/3/" → "docs.python.org"
    base_domain = urlparse(start_url).netloc

    # visited: URLs we've already crawled (set = no duplicates, fast lookup)
    visited: set = set()

    # to_visit: URLs we still need to crawl (start with the base URL)
    to_visit: List[str] = [start_url]

    # results: our collected pages
    results: List[Dict[str, str]] = []

    print(f"🕷️  Starting crawl from: {start_url}")
    print(f"📄  Max pages: {max_pages}")

    while to_visit and len(results) < max_pages:
        # Pop the first URL from the queue (FIFO = breadth-first crawl)
        url = to_visit.pop(0)

        # Skip if we've already visited this URL
        if url in visited:
            continue

        # Mark as visited immediately to avoid duplicates
        visited.add(url)

        try:
            print(f"  🔍 Crawling ({len(results)+1}/{max_pages}): {url}")

            # Send HTTP GET request with a browser-like User-Agent
            # Why User-Agent? Some servers block requests without it,
            # thinking it's a bot (which we are, but a polite one)
            response = requests.get(
                url,
                timeout=10,          # Don't wait more than 10 seconds
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; QABot/1.0; "
                        "educational-project)"
                    )
                }
            )

            # Skip non-HTML responses (PDFs, images, etc.)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                print(f"    ⏭️  Skipping non-HTML: {content_type}")
                continue

            # Skip failed responses
            # raise_for_status() throws an exception for 4xx/5xx codes
            response.raise_for_status()
            # Skip pages that are clearly not useful docs
            SKIP_PATTERNS = ["changelog", "genindex", "py-modindex", "c-api"]
            if any(p in url for p in SKIP_PATTERNS):
                print(f"    ⏭️  Skipping non-doc page: {url}")
                continue

            # Parse the HTML with BeautifulSoup
            # "html.parser" is Python's built-in parser — no extra install
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract clean text from this page
            text = clean_text(soup)

            # Only keep pages with meaningful content
            # (skip 404 pages, empty pages, etc.)
            if len(text) < 100:
                print(f"    ⚠️  Skipping thin page (< 100 chars)")
                continue

            # Save this page's data
            results.append({
                "url": url,
                "text": text
            })

            # ── Find more links to crawl ──────────────────────────
            # soup.find_all("a") finds every <a href="..."> tag
            for link_tag in soup.find_all("a", href=True):
                # href=True means only <a> tags that HAVE an href attr

                # urljoin handles relative URLs:
                # urljoin("https://docs.python.org/3/", "tutorial/")
                # → "https://docs.python.org/3/tutorial/"
                full_url = urljoin(url, link_tag["href"])

                # Strip URL fragments (#section-name) — they point to
                # the same page, just a different scroll position
                full_url = full_url.split("#")[0]

                # Add to queue if valid and not yet visited
                if (is_valid_url(full_url, base_domain)
                        and full_url not in visited
                        and full_url not in to_visit):
                    to_visit.append(full_url)

            # Be polite — wait 0.5s between requests
            # Why: Hammering a server too fast can get you blocked
            # and is bad internet citizenship
            time.sleep(0.5)

        except requests.exceptions.Timeout:
            print(f"    ❌ Timeout: {url}")
        except requests.exceptions.ConnectionError:
            print(f"    ❌ Connection error: {url}")
        except requests.exceptions.HTTPError as e:
            print(f"    ❌ HTTP error {e.response.status_code}: {url}")
        except Exception as e:
            print(f"    ❌ Unexpected error on {url}: {e}")

    print(f"\n✅ Crawl complete! Collected {len(results)} pages.")
    return results


# ── Quick test (run this file directly) ──────────────────────────────
# This block only runs when you do: python3 -m app.crawler
# It does NOT run when crawler.py is imported by another file
if __name__ == "__main__":
    pages = crawl()
    for i, page in enumerate(pages):
        print(f"\n{'='*60}")
        print(f"Page {i+1}: {page['url']}")
        print(f"Text preview (first 300 chars):")
        print(page['text'][:300])