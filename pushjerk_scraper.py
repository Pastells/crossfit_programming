import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


class PushJerkScraper:
    def __init__(self, base_url="https://pushjerk.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        self.workouts = []
        self.cycles = []
        self.current_cycle = None
        self.current_week = None
        self.raw_pages = []

    def get_page(self, url, delay=1):
        """Fetch a page with error handling and rate limiting"""
        try:
            time.sleep(delay)
            # print(f"Fetching: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def store_page_html(self, soup, page_num, url):
        """Store complete page HTML for later processing"""
        page_data = {
            "page_number": page_num,
            "url": url,
            "html": str(soup),
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "post_count": len(soup.select('article, .post, .entry, [class*="post"]')),
        }
        self.raw_pages.append(page_data)
        # print(f"Stored HTML for page {page_num} ({page_data['post_count']} posts found)")

    def load_existing_data(self):
        """Load existing data from JSON files"""
        try:
            # Load existing workouts
            workouts_file = os.path.join("data", "pushjerk_workouts.json")
            if os.path.exists(workouts_file):
                with open(workouts_file, "r", encoding="utf-8") as f:
                    self.workouts = json.load(f)

            # Load existing cycles
            cycles_file = os.path.join("data", "pushjerk_cycles.json")
            if os.path.exists(cycles_file):
                with open(cycles_file, "r", encoding="utf-8") as f:
                    self.cycles = json.load(f)

            # Load raw pages
            html_file = os.path.join("data", "pushjerk_raw_pages.json")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    self.raw_pages = json.load(f)

            # Restore current cycle state
            if self.cycles:
                self.current_cycle = self.cycles[-1]  # Most recent cycle
                # Find latest week number
                cycle_workouts = [
                    w for w in self.workouts if w.get("cycle_id") == self.current_cycle["cycle_id"]
                ]
                if cycle_workouts:
                    self.current_week = max(
                        w.get("week_number", 0) for w in cycle_workouts if w.get("week_number")
                    )

            print(f"Loaded existing data: {len(self.workouts)} workouts, {len(self.cycles)} cycles")
            return True
        except Exception as e:
            print(f"Error loading existing data: {e}")
            return False

    def get_latest_workout_titles(self):
        """Get titles of most recent workouts to check for duplicates"""
        if not self.workouts:
            return set()
        # Get titles from first page worth of workouts
        recent_titles = set()
        page_1_workouts = [w for w in self.workouts if w.get("source_page") == 1]
        for workout in page_1_workouts:
            if workout.get("title"):
                recent_titles.add(workout["title"].strip())
        return recent_titles

    def update_with_new_workouts(self, max_pages=3):
        """Download only new workouts from recent pages"""
        existing_titles = self.get_latest_workout_titles()
        new_workouts = []
        new_pages = []

        print(f"Checking for new workouts... (existing titles: {len(existing_titles)})")

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                url = self.base_url
            else:
                url = f"{self.base_url}/page/{page_num}/"

            soup = self.get_page(url)
            if soup:
                # Store raw HTML
                page_data = {
                    "page_number": page_num,
                    "url": url,
                    "html": str(soup),
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "post_count": len(soup.select('article, .post, .entry, [class*="post"]')),
                }

                # Extract workouts from this page
                page_workouts = self.extract_workout_posts(soup)
                new_workouts_found = 0

                for workout_data in page_workouts:
                    workout_title = workout_data.get("title", "").strip()

                    # Check if this is a new workout
                    if workout_title not in existing_titles:
                        workout_data["source_page"] = page_num
                        workout_data["source_url"] = url
                        new_workouts.append(workout_data)
                        new_workouts_found += 1
                        print(f"  Found new workout: {workout_title}")
                    else:
                        print(f"  Skipping existing workout: {workout_title}")

                # Always update page 1 data, add new pages
                if page_num == 1:
                    # Replace page 1 data
                    self.raw_pages = [p for p in self.raw_pages if p["page_number"] != 1]

                new_pages.append(page_data)

                # If we found no new workouts on this page, we can stop
                if new_workouts_found == 0 and page_num > 1:
                    print(f"No new workouts found on page {page_num}, stopping search")
                    break
            else:
                print(f"Failed to fetch page {page_num}")
                break

        return new_workouts, new_pages

    def merge_new_data(self, new_workouts, new_pages):
        """Merge new workouts and pages with existing data"""
        # Add new pages
        for page_data in new_pages:
            # Remove any existing data for this page number
            self.raw_pages = [
                p for p in self.raw_pages if p["page_number"] != page_data["page_number"]
            ]
            self.raw_pages.append(page_data)

        # Add new workouts to the beginning (most recent first)
        self.workouts = new_workouts + self.workouts

        print(f"Merged {len(new_workouts)} new workouts and {len(new_pages)} updated pages")

    def extract_workout_posts(self, soup):
        """Extract workout posts from a page"""
        workouts = []

        # Common selectors for blog posts/articles
        post_selectors = [
            "article",
            ".post",
            ".entry",
            ".workout-post",
            '[class*="post"]',
            ".hentry",
        ]

        posts = []
        for selector in post_selectors:
            found_posts = soup.select(selector)
            if found_posts:
                posts = found_posts
                # print(f"Found {len(posts)} posts using selector: {selector}")
                break

        for post in posts:
            workout_data = self.extract_workout_data(post)
            if workout_data:
                workouts.append(workout_data)

        return workouts

    def extract_workout_data(self, post_element):
        """Extract data from a single workout post"""
        workout = {
            "title": "",
            "content": "",
            "exercise_links": [],
            "all_links": [],
            "raw_html": str(post_element),
        }

        # Extract title
        title_selectors = [
            "h1",
            "h2",
            "h3",
            ".post-title",
            ".entry-title",
            "header h1",
            "header h2",
        ]
        for selector in title_selectors:
            title_elem = post_element.select_one(selector)
            if title_elem:
                title_text = title_elem.get_text().strip()
                workout["title"] = title_text
                break

        # If no title found, look in parent elements
        if not workout["title"]:
            parent = post_element.parent
            if parent:
                for selector in title_selectors:
                    title_elem = parent.select_one(selector)
                    if title_elem:
                        title_text = title_elem.get_text().strip()
                        workout["title"] = title_text
                        break

        # Extract content text
        workout["content"] = post_element.get_text().strip()

        # Extract all links
        links = post_element.find_all("a", href=True)
        for link in links:
            href = link["href"]
            full_url = urljoin(self.base_url, href)
            link_text = link.get_text().strip()

            link_data = {
                "url": full_url,
                "text": link_text,
                "is_exercise": self.is_exercise_link(link_text, href),
            }

            workout["all_links"].append(link_data)

            # If it looks like an exercise link, add to exercise_links
            if link_data["is_exercise"]:
                workout["exercise_links"].append(link_data)

        # Detect cycle information (Monday workouts)
        if "mon" in workout["title"].lower():
            self.detect_cycle_info(workout["content"], workout["title"])

        # Add cycle information to workout
        workout["cycle_id"] = self.current_cycle["cycle_id"] if self.current_cycle else None
        workout["week_number"] = self.current_week
        workout["cycle_week"] = (
            f"Cycle {workout['cycle_id']}, Week {workout['week_number']}"
            if workout["cycle_id"] and workout["week_number"]
            else None
        )

        # Add workout to current cycle
        if self.current_cycle:
            if not self.current_cycle["start_date"] and workout["title"]:
                self.current_cycle["start_date"] = workout["title"]
            self.current_cycle["workouts"].append(len(self.workouts))

        if workout["title"] or workout["exercise_links"]:
            return workout

        return None

    def detect_cycle_info(self, content_text, title):
        """Detect cycle and week information from workout content"""
        # Check for "Week x of y" pattern
        week_pattern = r"Week\s+(\d+)\s+of\s+(\d+)"
        match = re.search(week_pattern, content_text, re.IGNORECASE)

        if match:
            week_num = int(match.group(1))
            total_weeks = int(match.group(2))

            # If it's week 1 or new cycle detected
            if week_num == 1 or (
                self.current_cycle and total_weeks != self.current_cycle.get("total_weeks")
            ):
                self.start_new_cycle(total_weeks)

            self.current_week = week_num
            return True

        # Check if it's Monday and might be start of new cycle (no "Week x of y" found)
        if "mon" in title.lower() and not match:
            # Look for cycle explanation keywords
            cycle_keywords = ["cycle", "program", "phase", "block", "weeks", "training"]
            if any(keyword in content_text.lower() for keyword in cycle_keywords):
                self.start_new_cycle()
                self.current_week = 1
                return True

        return False

    def start_new_cycle(self, total_weeks=None):
        """Start a new training cycle"""
        cycle_id = len(self.cycles) + 1
        self.current_cycle = {
            "cycle_id": cycle_id,
            "total_weeks": total_weeks,
            "workouts": [],
            "start_date": None,
        }
        self.cycles.append(self.current_cycle)
        # print(f"Started new cycle {cycle_id}" + (f" ({total_weeks} weeks)" if total_weeks else ""))

    def is_exercise_link(self, link_text, href):
        """Determine if a link is likely an exercise"""
        # Exercise keywords
        exercise_keywords = [
            "squat",
            "deadlift",
            "pullup",
            "pull-up",
            "pushup",
            "push-up",
            "burpee",
            "thruster",
            "clean",
            "jerk",
            "snatch",
            "row",
            "kettlebell",
            "kb",
            "box jump",
            "wall ball",
            "double under",
            "handstand",
            "muscle up",
            "toes to bar",
            "sit-up",
            "plank",
            "lunge",
            "press",
            "curl",
            "swing",
            "turkish get up",
            "farmer",
        ]

        text_lower = link_text.lower()
        href_lower = href.lower()

        # Check if link text or URL contains exercise keywords
        for keyword in exercise_keywords:
            if keyword in text_lower or keyword in href_lower:
                return True

        # Check if it's a YouTube link (often exercise demos)
        if "youtube.com" in href_lower or "youtu.be" in href_lower:
            return True

        # Check if it's a video or demo link
        demo_keywords = ["demo", "video", "how to", "tutorial", "form"]
        for keyword in demo_keywords:
            if keyword in text_lower:
                return True

        return False

    def scrape_pages(self, start_page=1, end_page=5):
        """Scrape multiple pages"""
        print(f"Scraping pages {start_page} to {end_page}")

        for page_num in tqdm(range(start_page, end_page + 1)):
            if page_num == 1:
                url = self.base_url
            else:
                url = f"{self.base_url}/page/{page_num}/"

            soup = self.get_page(url)
            if not soup:
                print(f"Failed to load page {page_num}")
                continue

            self.store_page_html(soup, page_num, url)
            page_workouts = self.extract_workout_posts(soup)
            # print(f"Page {page_num}: Found {len(page_workouts)} workouts")

            for workout in page_workouts:
                workout["source_page"] = page_num
                workout["source_url"] = url
                self.workouts.append(workout)

            # Be respectful with delays
            time.sleep(2)

        print(f"Total workouts scraped: {len(self.workouts)}")

    def update_database(self, max_pages=3):
        """Update database with new workouts only"""
        print("Loading existing database...")
        self.load_existing_data()

        print("Checking for new workouts...")
        new_workouts, new_pages = self.update_with_new_workouts(max_pages)

        if new_workouts:
            print(f"Found {len(new_workouts)} new workouts")
            self.merge_new_data(new_workouts, new_pages)

            # Re-process cycles for new workouts
            for workout in new_workouts:
                if "mon" in workout["title"].lower():
                    self.detect_cycle_info(workout["content"], workout["title"])

            self.save_data()
            print("Database updated successfully!")
        else:
            print("No new workouts found")

        return len(new_workouts)

    def save_data(self):
        """Save scraped data"""
        if not os.path.exists("data"):
            os.makedirs("data")

        # Save raw HTML pages
        html_file = os.path.join("data", "pushjerk_raw_pages.json")
        with open(html_file, "w", encoding="utf-8") as f:
            json.dump(self.raw_pages, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.raw_pages)} raw pages to {html_file}")

        # Save processed workouts
        workouts_file = os.path.join("data", "pushjerk_workouts.json")
        with open(workouts_file, "w", encoding="utf-8") as f:
            json.dump(self.workouts, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.workouts)} workouts to {workouts_file}")

        # Save cycles
        cycles_file = os.path.join("data", "pushjerk_cycles.json")
        with open(cycles_file, "w", encoding="utf-8") as f:
            json.dump(self.cycles, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.cycles)} cycles to {cycles_file}")

        # Save database summary
        db_summary = {
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_pages": len(self.raw_pages),
            "total_workouts": len(self.workouts),
            "total_cycles": len(self.cycles),
            "page_range": f"{min(p['page_number'] for p in self.raw_pages)}-{max(p['page_number'] for p in self.raw_pages)}"
            if self.raw_pages
            else "None",
        }

        summary_file = os.path.join("data", "database_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(db_summary, f, indent=2, ensure_ascii=False)
        print(f"Saved database summary to {summary_file}")

    def print_summary(self):
        """Print scraping summary"""
        print("\n=== Scraping Summary ===")
        print(f"Pages scraped: {len(self.raw_pages)}")
        print(f"Total workouts: {len(self.workouts)}")
        print(f"Training cycles found: {len(self.cycles)}")
        print(
            f"Workouts with exercise links: {len([w for w in self.workouts if w['exercise_links']])}"
        )

        if self.cycles:
            for cycle in self.cycles:
                workouts_in_cycle = len(cycle["workouts"])
                print(
                    f"  Cycle {cycle['cycle_id']}: {workouts_in_cycle} workouts"
                    + (f" ({cycle['total_weeks']} weeks planned)" if cycle["total_weeks"] else "")
                )

        print("\nDatabase files will be saved to 'data/' folder")


if __name__ == "__main__":
    scraper = PushJerkScraper()

    print("Starting PushJerk scrape...")
    # scraper.scrape_pages(start_page=1, end_page=142)
    # scraper.save_data()
    new_count = scraper.update_database(max_pages=3)
    print(f"Update complete. {new_count} new workouts added.")

    scraper.print_summary()
    print("\nDone! Check the data folder for results.")
