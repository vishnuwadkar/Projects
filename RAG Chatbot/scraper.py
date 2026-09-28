"""
scraper.py — Vedabase.io Content Scraper
==========================================
Scrapes books from vedabase.io using Playwright (headless browser)
to capture JavaScript-rendered content.

Three-level crawl:
    Level 1: Book index    → list of chapters/cantos
    Level 2: Chapter index → list of verse URLs
    Level 3: Verse page    → extract all structured content

Respects robots.txt:
    - Crawl-delay: 10 seconds between requests
    - Avoids disallowed paths (/search/, /advanced-view/, etc.)

Usage:
    # Scrape Bhagavad-gita only (recommended first run)
    python scraper.py --books bg

    # Scrape multiple specific books
    python scraper.py --books bg sb cc

    # Scrape ALL books (takes 24-48 hours)
    python scraper.py --all

    # Resume a previously interrupted scrape
    python scraper.py --books bg --resume

Prerequisites:
    pip install playwright
    playwright install chromium
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:

    from playwright.async_api import async_playwright
except ImportError:
    print("[X] Playwright is not installed.")
    print("    Run: pip install playwright && playwright install chromium")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://vedabase.io"
LIBRARY_URL = f"{BASE_URL}/en/library/"
DATA_DIR = Path("./data/vedabase")
MANIFEST_FILE = DATA_DIR / "manifest.json"
CRAWL_DELAY = 10  # seconds between requests (per robots.txt)
PAGE_LOAD_TIMEOUT = 30_000  # ms — max wait for page load
CONTENT_WAIT_TIMEOUT = 15_000  # ms — max wait for JS content to render

# All known book codes and their names
BOOK_CATALOG = {
    "bg": "Bhagavad-gītā As It Is",
    "sb": "Śrīmad-Bhāgavatam",
    "cc": "Śrī Caitanya-caritāmṛta",
    "noi": "Nectar of Instruction",
    "kb": "Kṛṣṇa, the Supreme Personality of Godhead",
    "nod": "The Nectar of Devotion",
    "iso": "Śrī Īśopaniṣad",
    "ssr": "The Science of Self-Realization",
    "bbd": "Beyond Birth and Death",
    "bhakti": "Bhakti: The Art of Eternal Love",
    "bs": "Śrī Brahma-saṁhitā",
    "cat": "Civilization and Transcendence",
    "josd": "The Journey of Self-Discovery",
    "owk": "On the Way to Kṛṣṇa",
    "pop": "The Path of Perfection",
    "poy": "The Perfection of Yoga",
    "pqpa": "Perfect Questions, Perfect Answers",
    "rv": "Rāja-vidyā: The King of Knowledge",
    "sc": "A Second Chance",
    "tlc": "Teachings of Lord Caitanya",
    "tlk": "Teachings of Lord Kapila",
    "tqk": "Teachings of Queen Kuntī",
    "lob": "Light of the Bhāgavata",
    "cabh": "Chant and be happy",
    "spl": "Śrīla Prabhupāda-līlāmṛta",
    "rkd": "Rāmāyaṇa",
    "mbk": "Mahābhārata",
}


# ---------------------------------------------------------------------------
# Manifest (checkpoint/resume)
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    """Load the scraping progress manifest, or create a new one."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"completed_books": [], "completed_urls": [], "in_progress": None}


def save_manifest(manifest: dict):
    """Persist the manifest to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Content Extraction Helpers
# ---------------------------------------------------------------------------

async def extract_verse_content(page) -> dict:
    """
    Extract structured content from a rendered verse page.

    The page has content organized under h2 headings:
    - Devanagari
    - Verse text (transliteration)
    - Synonyms
    - Translation
    - Purport

    We parse by iterating h2 section boundaries.
    """
    content = {
        "devanagari": "",
        "transliteration": "",
        "synonyms": "",
        "translation": "",
        "purport": "",
    }

    try:
        # Wait for the main content to render (the h2 headings appear
        # only after JS execution)
        await page.wait_for_selector("h2", timeout=CONTENT_WAIT_TIMEOUT)

        # Get all h2 headings and their following content via JS
        extracted = await page.evaluate("""
        () => {
            const result = {};
            const headings = document.querySelectorAll('h2');

            headings.forEach((h2, index) => {
                const title = h2.textContent.trim().toLowerCase();

                // Collect all sibling elements until the next h2
                let text = [];
                let sibling = h2.nextElementSibling;
                const nextH2 = headings[index + 1];

                while (sibling && sibling !== nextH2) {
                    // Skip navigation elements and empty elements
                    if (sibling.tagName !== 'NAV' &&
                        sibling.textContent.trim() !== '') {
                        text.push(sibling.textContent.trim());
                    }
                    sibling = sibling.nextElementSibling;
                }

                if (title.includes('devanagari') || title === 'devanāgarī') {
                    result['devanagari'] = text.join('\\n');
                } else if (title.includes('verse text') || title.includes('text')) {
                    // "Verse text" is the transliteration section
                    if (!result['transliteration']) {
                        result['transliteration'] = text.join('\\n');
                    }
                } else if (title.includes('synonym')) {
                    result['synonyms'] = text.join('\\n');
                } else if (title.includes('translation')) {
                    result['translation'] = text.join('\\n');
                } else if (title.includes('purport')) {
                    result['purport'] = text.join('\\n\\n');
                }
            });

            return result;
        }
        """)

        content.update({k: v for k, v in extracted.items() if v})

    except Exception as e:
        print(f"    [!] Content extraction warning: {e}")

    return content


async def extract_chapter_content(page) -> str:
    """
    Extract prose content from a chapter/essay page (non-verse books).
    These pages have continuous text rather than verse structure.
    """
    try:
        # Wait for content to load
        await page.wait_for_selector("h1", timeout=CONTENT_WAIT_TIMEOUT)

        content = await page.evaluate("""
        () => {
            // Find the main content area — typically the article or main div
            // after the breadcrumbs and before the footer
            const paragraphs = document.querySelectorAll(
                '.r-text p, article p, .content p, main p'
            );
            if (paragraphs.length > 0) {
                return Array.from(paragraphs)
                    .map(p => p.textContent.trim())
                    .filter(t => t.length > 0)
                    .join('\\n\\n');
            }

            // Fallback: get all text under the main content area
            const main = document.querySelector('main') ||
                         document.querySelector('article') ||
                         document.querySelector('.content');
            if (main) {
                return main.textContent.trim();
            }
            return '';
        }
        """)

        return content or ""
    except Exception as e:
        print(f"    [!] Chapter content extraction warning: {e}")
        return ""


# ---------------------------------------------------------------------------
# URL Discovery
# ---------------------------------------------------------------------------

async def discover_sections(page, url: str) -> list[dict]:
    """
    Navigate to a book/canto/chapter index page and extract all child links.
    Returns a list of dicts with 'title' and 'url' keys.
    """
    await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
    await asyncio.sleep(2)  # Brief wait for any JS rendering

    links = await page.evaluate("""
    (baseUrl) => {
        const results = [];
        // Find all content links in the main body (not nav/footer)
        const allLinks = document.querySelectorAll('a[href*="/en/library/"]');
        const seen = new Set();

        allLinks.forEach(a => {
            const href = a.getAttribute('href');
            const text = a.textContent.trim();

            // Skip navigation, duplicates, and non-content links
            if (!href || seen.has(href)) return;
            if (href.includes('advanced-view')) return;
            if (href.includes('side-by-side')) return;
            if (text === 'Default View') return;
            if (text === 'Library') return;

            // Build absolute URL
            let fullUrl = href.startsWith('http')
                ? href
                : baseUrl.replace(/\\/+$/, '') + href;

            // Only include links that go DEEPER than the current page
            const currentPath = new URL(baseUrl.replace(/\\/+$/, '')).pathname;
            try {
                const linkPath = new URL(fullUrl).pathname;
                if (linkPath.length > currentPath.length + 1 &&
                    linkPath.startsWith(currentPath)) {
                    seen.add(href);
                    results.push({ title: text, url: fullUrl });
                }
            } catch(e) {}
        });

        return results;
    }
    """, url)

    return links


async def discover_verse_links(page, chapter_url: str) -> list[dict]:
    """
    Navigate to a chapter page and extract all verse/text links.
    Returns list of dicts with 'title' and 'url'.
    """
    await page.goto(chapter_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
    await asyncio.sleep(2)

    links = await page.evaluate("""
    (baseUrl) => {
        const results = [];
        const allLinks = document.querySelectorAll('a');
        const seen = new Set();

        allLinks.forEach(a => {
            const href = a.getAttribute('href');
            const text = a.textContent.trim();

            if (!href || seen.has(href)) return;
            if (href.includes('advanced-view')) return;
            if (href.includes('side-by-side')) return;

            // Match verse-like links: TEXT 1, TEXT 2, TEXTS 3-4, etc.
            // Also match other content pages within the chapter
            const isVerseLink = /TEXT/i.test(text);
            const isContentLink = href.includes('/en/library/') &&
                                  !text.includes('Chapter') &&
                                  !text.includes('Canto') &&
                                  text !== 'Default View' &&
                                  text !== 'Library';

            if (isVerseLink || isContentLink) {
                let fullUrl = href.startsWith('http')
                    ? href
                    : 'https://vedabase.io' + href;

                // Only links deeper than current
                const currentPath = new URL(baseUrl.replace(/\\/+$/, '')).pathname;
                try {
                    const linkPath = new URL(fullUrl).pathname;
                    if (linkPath.length > currentPath.length + 1 &&
                        linkPath.startsWith(currentPath)) {
                        seen.add(href);
                        results.push({ title: text, url: fullUrl });
                    }
                } catch(e) {}
            }
        });

        return results;
    }
    """, chapter_url)

    return links


# ---------------------------------------------------------------------------
# Book Classification
# ---------------------------------------------------------------------------

def is_verse_structured(book_code: str) -> bool:
    """
    Return True if the book uses verse-style pages (devanagari, translation,
    purport), False if it's prose/essay-style.
    """
    verse_books = {"bg", "sb", "cc", "noi", "iso", "bs", "lob"}
    return book_code in verse_books


# ---------------------------------------------------------------------------
# Main Scraping Logic
# ---------------------------------------------------------------------------

async def scrape_verse_page(page, url: str, book_code: str,
                            book_name: str) -> dict | None:
    """Scrape a single verse page and return structured data."""
    try:
        await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
        await asyncio.sleep(2)  # Wait for JS rendering

        # Get page title for the reference
        title = await page.title()

        # Extract the verse reference from the h1
        h1_text = ""
        try:
            h1 = await page.query_selector("h1")
            if h1:
                h1_text = await h1.text_content()
                h1_text = h1_text.strip()
        except Exception:
            pass

        # Extract structured content
        content = await extract_verse_content(page)

        # Parse chapter and verse from URL
        # URL pattern: /en/library/{book}/{chapter}/{verse}/
        parts = url.rstrip("/").split("/")
        verse_num = parts[-1] if parts else ""
        chapter_num = parts[-2] if len(parts) > 1 else ""

        # Get chapter title from breadcrumbs
        chapter_title = ""
        try:
            breadcrumbs = await page.query_selector_all("a")
            for bc in breadcrumbs:
                text = await bc.text_content()
                if text and ("chapter" in text.lower() or "canto" in text.lower()):
                    chapter_title = text.strip()
                    break
        except Exception:
            pass

        reference = h1_text or title.replace(" | Vedabase", "")

        return {
            "reference": reference,
            "chapter": chapter_num,
            "chapter_title": chapter_title,
            "verse_number": verse_num,
            "url": url,
            "devanagari": content.get("devanagari", ""),
            "transliteration": content.get("transliteration", ""),
            "synonyms": content.get("synonyms", ""),
            "translation": content.get("translation", ""),
            "purport": content.get("purport", ""),
        }

    except Exception as e:
        print(f"    [X] Failed to scrape {url}: {e}")
        return None


async def scrape_prose_page(page, url: str, book_code: str,
                            book_name: str) -> dict | None:
    """Scrape a prose/essay-style chapter page."""
    try:
        await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
        await asyncio.sleep(2)

        title = await page.title()

        h1_text = ""
        try:
            h1 = await page.query_selector("h1")
            if h1:
                h1_text = await h1.text_content()
                h1_text = h1_text.strip()
        except Exception:
            pass

        content = await extract_chapter_content(page)

        # Parse chapter from URL
        parts = url.rstrip("/").split("/")
        chapter_id = parts[-1] if parts else ""

        return {
            "reference": h1_text or title.replace(" | Vedabase", ""),
            "chapter": chapter_id,
            "chapter_title": h1_text,
            "url": url,
            "content": content,
        }

    except Exception as e:
        print(f"    [X] Failed to scrape {url}: {e}")
        return None


async def scrape_book(page, book_code: str, manifest: dict, resume: bool):
    """
    Scrape an entire book and save results to a JSON file.
    Supports resume from checkpoint.
    """
    book_name = BOOK_CATALOG.get(book_code, book_code)
    output_file = DATA_DIR / f"{book_code}.json"
    completed_urls = set(manifest.get("completed_urls", []))

    print(f"\n{'='*60}")
    print(f"📖 Scraping: {book_name} ({book_code})")
    print(f"{'='*60}")

    # Load existing data if resuming
    existing_data = []
    if resume and output_file.exists():
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        existing_data = existing.get("verses", existing.get("chapters", []))
        print(f"  [RESUME] Found {len(existing_data)} existing entries")

    book_url = f"{BASE_URL}/en/library/{book_code}/"

    # Step 1: Discover chapters/cantos
    print(f"\n  [1] Discovering chapters from {book_url}")
    sections = await discover_sections(page, book_url)
    print(f"      Found {len(sections)} sections")
    await asyncio.sleep(CRAWL_DELAY)

    is_verse = is_verse_structured(book_code)
    all_entries = list(existing_data)
    total_scraped = len(existing_data)
    errors = 0

    # For verse-structured books, we need to go deeper:
    # Book → Chapter/Canto → Verse
    if is_verse:
        for section in sections:
            section_url = section["url"]
            section_title = section["title"]
            print(f"\n  [Chapter] {section_title}")

            # Some books have an extra level (SB: Canto → Chapter → Verse)
            # Check if this section has sub-sections or direct verse links
            verse_links = await discover_verse_links(page, section_url)
            await asyncio.sleep(CRAWL_DELAY)

            if not verse_links:
                # This section might be a canto with chapters inside
                sub_sections = await discover_sections(page, section_url)
                await asyncio.sleep(CRAWL_DELAY)

                for sub in sub_sections:
                    sub_verses = await discover_verse_links(page, sub["url"])
                    await asyncio.sleep(CRAWL_DELAY)
                    print(f"    [Sub-chapter] {sub['title']} → "
                          f"{len(sub_verses)} verses")

                    for vl in sub_verses:
                        if resume and vl["url"] in completed_urls:
                            continue

                        print(f"      Scraping: {vl['title']} ...", end=" ",
                              flush=True)
                        result = await scrape_verse_page(
                            page, vl["url"], book_code, book_name
                        )
                        if result and (result.get("translation") or
                                       result.get("purport")):
                            all_entries.append(result)
                            completed_urls.add(vl["url"])
                            total_scraped += 1
                            print("✓")
                        else:
                            errors += 1
                            print("✗ (no content)")

                        # Save checkpoint after each verse
                        _save_book_checkpoint(
                            output_file, book_code, book_name,
                            all_entries, is_verse
                        )
                        manifest["completed_urls"] = list(completed_urls)
                        save_manifest(manifest)

                        await asyncio.sleep(CRAWL_DELAY)
            else:
                # Direct verse links found
                print(f"    → {len(verse_links)} verses")
                for vl in verse_links:
                    if resume and vl["url"] in completed_urls:
                        continue

                    print(f"      Scraping: {vl['title']} ...", end=" ",
                          flush=True)
                    result = await scrape_verse_page(
                        page, vl["url"], book_code, book_name
                    )
                    if result and (result.get("translation") or
                                   result.get("purport")):
                        all_entries.append(result)
                        completed_urls.add(vl["url"])
                        total_scraped += 1
                        print("✓")
                    else:
                        errors += 1
                        print("✗ (no content)")

                    _save_book_checkpoint(
                        output_file, book_code, book_name,
                        all_entries, is_verse
                    )
                    manifest["completed_urls"] = list(completed_urls)
                    save_manifest(manifest)

                    await asyncio.sleep(CRAWL_DELAY)
    else:
        # Prose/essay-style books — scrape chapter pages directly
        for section in sections:
            if resume and section["url"] in completed_urls:
                continue

            print(f"    Scraping: {section['title']} ...", end=" ", flush=True)
            result = await scrape_prose_page(
                page, section["url"], book_code, book_name
            )
            if result and result.get("content"):
                all_entries.append(result)
                completed_urls.add(section["url"])
                total_scraped += 1
                print("✓")
            else:
                errors += 1
                print("✗ (no content)")

            _save_book_checkpoint(
                output_file, book_code, book_name,
                all_entries, is_verse=False
            )
            manifest["completed_urls"] = list(completed_urls)
            save_manifest(manifest)

            await asyncio.sleep(CRAWL_DELAY)

    # Final save
    _save_book_checkpoint(
        output_file, book_code, book_name, all_entries, is_verse
    )
    manifest["completed_books"].append(book_code)
    manifest["completed_books"] = list(set(manifest["completed_books"]))
    save_manifest(manifest)

    print(f"\n  ✅ Done: {total_scraped} entries scraped, {errors} errors")
    print(f"  📁 Saved to: {output_file}")


def _save_book_checkpoint(output_file: Path, book_code: str,
                          book_name: str, entries: list, is_verse: bool):
    """Save the current scraping progress to a JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    key = "verses" if is_verse else "chapters"
    data = {
        "book": book_name,
        "book_code": book_code,
        "source_url": f"{BASE_URL}/en/library/{book_code}/",
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_entries": len(entries),
        key: entries,
    }

    output_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Also scrape special pages (preface, introduction, etc.)
# ---------------------------------------------------------------------------

async def scrape_special_pages(page, book_code: str, manifest: dict):
    """Scrape non-verse pages like prefaces, introductions, dedications."""
    book_url = f"{BASE_URL}/en/library/{book_code}/"
    completed_urls = set(manifest.get("completed_urls", []))

    await page.goto(book_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
    await asyncio.sleep(2)

    # Find special page links (preface, introduction, dedication, etc.)
    special_links = await page.evaluate("""
    () => {
        const results = [];
        const links = document.querySelectorAll('a[href*="/en/library/"]');

        links.forEach(a => {
            const text = a.textContent.trim().toLowerCase();
            const href = a.getAttribute('href');
            const specials = ['preface', 'introduction', 'dedication',
                            'foreword', 'setting-the-scene', 'prologue',
                            'note-2nd-edition'];

            if (specials.some(s => href.includes(s) || text.includes(s))) {
                let fullUrl = href.startsWith('http')
                    ? href
                    : 'https://vedabase.io' + href;
                results.push({ title: a.textContent.trim(), url: fullUrl });
            }
        });
        return results;
    }
    """)

    special_entries = []
    for link in special_links:
        if link["url"] in completed_urls:
            continue

        print(f"    Scraping special page: {link['title']} ...", end=" ",
              flush=True)
        result = await scrape_prose_page(
            page, link["url"], book_code,
            BOOK_CATALOG.get(book_code, book_code)
        )
        if result and result.get("content"):
            special_entries.append(result)
            completed_urls.add(link["url"])
            print("✓")
        else:
            print("✗")
        await asyncio.sleep(CRAWL_DELAY)

    # Append special pages to the book's JSON file if any
    if special_entries:
        output_file = DATA_DIR / f"{book_code}.json"
        if output_file.exists():
            existing = json.loads(output_file.read_text(encoding="utf-8"))
            if "special_pages" not in existing:
                existing["special_pages"] = []
            existing["special_pages"].extend(special_entries)
            output_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    manifest["completed_urls"] = list(completed_urls)
    save_manifest(manifest)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

async def main_async(book_codes: list[str], resume: bool = False):
    """Main async entry point for the scraper."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest() if resume else {
        "completed_books": [],
        "completed_urls": [],
        "in_progress": None,
    }

    print("=" * 60)
    print("🕉️  Vedabase.io — Content Scraper")
    print("=" * 60)
    print(f"  Books to scrape: {', '.join(book_codes)}")
    print(f"  Output directory: {DATA_DIR.resolve()}")
    print(f"  Crawl delay: {CRAWL_DELAY}s")
    print(f"  Resume mode: {'ON' if resume else 'OFF'}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
            for book_code in book_codes:
                if book_code not in BOOK_CATALOG:
                    print(f"\n[!] Unknown book code: '{book_code}'. Skipping.")
                    print(f"    Valid codes: {', '.join(BOOK_CATALOG.keys())}")
                    continue

                if resume and book_code in manifest.get("completed_books", []):
                    print(f"\n[SKIP] {book_code} already completed.")
                    continue

                manifest["in_progress"] = book_code
                save_manifest(manifest)

                await scrape_book(page, book_code, manifest, resume)

                # Also scrape special pages (preface, intro, etc.)
                await scrape_special_pages(page, book_code, manifest)

                manifest["in_progress"] = None
                save_manifest(manifest)

        except KeyboardInterrupt:
            print("\n\n[!] Scraping interrupted by user.")
            print("    Run with --resume to continue where you left off.")
            save_manifest(manifest)
        except Exception as e:
            print(f"\n[X] Unexpected error: {e}")
            save_manifest(manifest)
            raise
        finally:
            await browser.close()

    # Final summary
    print("\n" + "=" * 60)
    print("🕉️  Scraping Complete!")
    print("=" * 60)
    for bc in book_codes:
        out = DATA_DIR / f"{bc}.json"
        if out.exists():
            data = json.loads(out.read_text(encoding="utf-8"))
            key = "verses" if "verses" in data else "chapters"
            count = len(data.get(key, []))
            print(f"  📖 {BOOK_CATALOG.get(bc, bc)}: {count} entries")
    print(f"\n  Next step: python ingest_vedabase.py")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape books from vedabase.io for the RAG chatbot"
    )
    parser.add_argument(
        "--books", nargs="+", default=["bg"],
        help=f"Book codes to scrape. Choices: {', '.join(BOOK_CATALOG.keys())}",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Scrape all available books",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from a previously interrupted scrape",
    )
    parser.add_argument(
        "--list-books", action="store_true",
        help="List all available book codes and exit",
    )

    args = parser.parse_args()

    if args.list_books:
        print("\nAvailable books on vedabase.io:")
        print("-" * 50)
        for code, name in BOOK_CATALOG.items():
            print(f"  {code:8s}  {name}")
        return

    book_codes = list(BOOK_CATALOG.keys()) if args.all else args.books

    asyncio.run(main_async(book_codes, resume=args.resume))


if __name__ == "__main__":
    main()
