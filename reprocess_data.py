import json
import os
import re

from bs4 import BeautifulSoup
from tqdm import tqdm

from backup_names import restore_cycles


def load_cycle_names():
    """Load custom cycle names from storage"""
    try:
        with open("data/cycle_names.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_cycle_names(cycle_names):
    """Save custom cycle names to storage"""
    os.makedirs("data", exist_ok=True)
    with open("data/cycle_names.json", "w") as f:
        json.dump(cycle_names, f, indent=2)


class DataReprocessor:
    def __init__(self):
        self.workouts = []
        self.cycles = []
        self.current_cycle = None
        self.current_week = None
        self.raw_pages = []

    def load_raw_pages(self):
        """Load the raw HTML pages"""
        html_file = os.path.join("data", "pushjerk_raw_pages.json")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                self.raw_pages = json.load(f)
            print(f"Loaded {len(self.raw_pages)} raw pages")
        else:
            print("No raw pages found!")

    def is_valid_workout_title(self, title):
        """Check if title is a valid workout date"""
        if not title or title.strip() in ["No title", "Warm-up", ""]:
            print(title)
            return False

        # Check for date pattern (Mon, Feb 24, 2025)
        date_pattern = r"\b(mon|tue|wed|thu|fri|sat|sun),?\s+\w+\s+\d+,\s+\d{4}\b"
        res = bool(re.search(date_pattern, title.lower()))
        if not res:
            print(title, "is not a valid workout title")
        return res

    def get_day_from_title(self, title):
        """Extract day of week from title"""
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        title_lower = title.lower()
        for day in days:
            if title_lower.startswith(day):
                return day
        return None

    def parse_workout_from_html(self, workout_html, source_page):
        """Parse individual workout from HTML"""
        soup = BeautifulSoup(workout_html, "html.parser")

        # Extract title
        title_elem = soup.find("h2") or soup.find("h3") or soup.find("strong")
        title = title_elem.get_text().strip() if title_elem else "No title"

        # Skip if not a valid workout title
        if not self.is_valid_workout_title(title):
            return None

        # Extract content
        content = soup.get_text().strip()

        workout = {
            "title": title,
            "content": content,
            "html": workout_html,
            "source_page": source_page,
            "day": self.get_day_from_title(title),
        }

        return workout

    def detect_cycle_info(self, content, title):
        """Detect cycle information from Monday workouts"""
        content_lower = content.lower()

        week_patterns = [
            r"week\s+(\d+)\s+of\s+(\d+)",  # Week X of Y
            r"week\s+(\d+)\/(\d+)",  # Week X/Y
            r"(\d+)\.1\)",  # (program W.D) D=1 on Mondays
            r"week\s+(\d+)(?!\s+(?:of|/))",  # Week N (not followed by "of" or "/")
        ]

        no_pattern = True
        for pattern in week_patterns:
            match = re.search(pattern, content_lower)
            if match:
                current_week = int(match.group(1))

                # Check if pattern has total weeks (group 2 exists)
                total_weeks = None
                if len(match.groups()) >= 2:
                    total_weeks = int(match.group(2))

                # If it's week 1, start a new cycle
                if current_week == 1:
                    self.current_cycle = {
                        "cycle_id": len(self.cycles) + 1,
                        "total_weeks": total_weeks,
                        "workouts": [],
                        "start_date": title,
                        "name": f"Cycle {len(self.cycles) + 1}",
                    }
                    self.cycles.append(self.current_cycle)

                self.current_week = current_week
                no_pattern = False
                break  # Stop at first match

        if no_pattern:
            self.current_cycle = {
                "cycle_id": len(self.cycles) + 1,
                "total_weeks": None,
                "workouts": [],
                "start_date": title,
                "name": f"Cycle {len(self.cycles) + 1}",
            }
            self.cycles.append(self.current_cycle)
            self.current_week = 1

    def organize_workouts_by_weeks(self):
        """Organize workouts into weeks based on day sequence, handling gaps and avoiding repeated days"""
        day_order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        for cycle in self.cycles:
            if not cycle["workouts"]:
                continue

            weeks = []
            current_week_workouts = []
            last_day_index = -1
            seen_dates_in_cycle = set()  # Track dates across entire cycle to avoid duplicates

            for workout_index in cycle["workouts"]:
                if workout_index >= len(self.workouts):
                    continue

                workout = self.workouts[workout_index]
                day = workout.get("day")
                date = workout.get("title")

                if day not in day_order:
                    continue

                # Skip if we've already seen this exact date in this cycle
                if date and date in seen_dates_in_cycle:
                    print(f"Skipping duplicate date: {date}")  # Debug info
                    continue

                # Add the date to our seen set
                if date:
                    seen_dates_in_cycle.add(date)

                current_day_index = day_order.index(day)

                # Start a new week if current day comes before the last processed day
                # BUT only if we actually have workouts in the current week
                should_start_new_week = (
                    current_week_workouts and current_day_index <= last_day_index
                )

                if should_start_new_week:
                    weeks.append(
                        {"week_number": len(weeks) + 1, "workouts": current_week_workouts.copy()}
                    )
                    current_week_workouts = []
                    last_day_index = -1

                current_week_workouts.append(workout_index)
                last_day_index = current_day_index

            # Add the final week
            if current_week_workouts:
                weeks.append(
                    {"week_number": len(weeks) + 1, "workouts": current_week_workouts.copy()}
                )

            cycle["weeks"] = weeks

    def reprocess_all_data(self):
        """Reprocess all workouts from raw HTML pages"""
        print("Starting reprocessing...")

        for page_data in tqdm(self.raw_pages[::-1]):
            page_num = page_data["page_number"]
            html_content = page_data["html"]

            # Parse the page HTML
            soup = BeautifulSoup(html_content, "html.parser")

            # Find all text elements and look for workout patterns
            all_text = soup.get_text()

            all_workouts = []

            # Look for date patterns to split content
            date_pattern = r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\w+\s+\d+,\s+\d{4}.*?)(?=(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\w+\s+\d+,\s+\d{4}|$)"
            matches = re.findall(date_pattern, all_text, re.DOTALL | re.IGNORECASE)

            for match in matches:
                # Create a simple HTML structure for each workout
                ssplit = match.split(" - ")[0] if " - " in match else match.split("\n")[0]
                workout_html = "<div><h2>" + ssplit + f"</h2><p>{match}</p></div>"
                workout = self.parse_workout_from_html(workout_html, page_num)

                if workout:  # Only add valid workouts
                    all_workouts.append(workout)

            # REVERSE the order to get chronological (oldest first)
            all_workouts.reverse()

            # Process each valid workout
            for workout in all_workouts:
                try:
                    # Calculate workout index before appending
                    workout_index = len(self.workouts)

                    # Detect cycle info for Monday workouts
                    if workout["day"] == "mon":
                        self.detect_cycle_info(workout["content"], workout["title"])

                    # Add workout index to current cycle
                    if self.current_cycle:
                        self.current_cycle["workouts"].append(workout_index)
                        workout["cycle_id"] = self.current_cycle["cycle_id"]
                        workout["week_number"] = self.current_week

                    # Append workout
                    self.workouts.append(workout)

                except Exception as e:
                    print(f"Error processing workout: {e}")
                    continue

        # Organize workouts by weeks
        self.organize_workouts_by_weeks()

        print(
            f"Reprocessing complete! Found {len(self.workouts)} valid workouts and {len(self.cycles)} cycles"
        )

    def save_reprocessed_data(self):
        """Save the reprocessed data"""
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)

        # Save workouts
        workouts_file = os.path.join("data", "pushjerk_workouts.json")
        with open(workouts_file, "w", encoding="utf-8") as f:
            json.dump(self.workouts, f, indent=2, ensure_ascii=False)

        # Save cycles
        cycles_file = os.path.join("data", "pushjerk_cycles.json")
        with open(cycles_file, "w", encoding="utf-8") as f:
            json.dump(self.cycles, f, indent=2, ensure_ascii=False)

        print(f"Saved {len(self.workouts)} workouts and {len(self.cycles)} cycles")

    def print_summary(self):
        """Print summary of reprocessed data"""
        print("\n=== REPROCESSING SUMMARY ===")
        print(f"Total workouts: {len(self.workouts)}")
        print(f"Total cycles: {len(self.cycles)}")

    def filter_cycles_by_weeks(self):
        """Filter cycles to only include those with more than 2 weeks, and create random selection data"""

        # First, let's see what we have before filtering
        print(f"Total cycles before filtering: {len(self.cycles)}")

        # Save ALL cycles (including short ones) for random selection BEFORE filtering
        all_cycles = self.cycles.copy()  # Keep original cycles for random selection

        # Create separate lists for random selection from ALL cycles
        all_weeks = []
        all_2week_sequences = []

        for cycle in all_cycles:
            weeks = cycle.get("weeks", [])
            cycle_name = cycle.get("name", f"Cycle {cycle.get('cycle_id', 'Unknown')}")

            for week in weeks:
                # Add individual weeks for random selection
                week_data = {
                    "cycle_name": cycle_name,
                    "week_number": week["week_number"],
                    "workouts": week["workouts"],
                    "total_weeks_in_cycle": len(weeks),
                }
                all_weeks.append(week_data)

                # Create 2-week sequences
                week_index = week["week_number"] - 1
                if week_index < len(weeks) - 1:  # If there's a next week
                    next_week = weeks[week_index + 1]
                    two_week_data = {
                        "cycle_name": cycle_name,
                        "week_numbers": [week["week_number"], next_week["week_number"]],
                        "weeks": [week, next_week],
                        "total_weeks_in_cycle": len(weeks),
                    }
                    all_2week_sequences.append(two_week_data)

        # Now filter self.cycles to only contain cycles with more than 2 weeks
        self.cycles = [cycle for cycle in self.cycles if len(cycle.get("weeks", [])) > 2]
        print(f"Cycles with 3+ weeks after filtering: {len(self.cycles)}")

        # Save random selections data
        with open("data/random_weeks.json", "w") as f:
            json.dump(all_weeks, f, indent=2)

        with open("data/random_2weeks.json", "w") as f:
            json.dump(all_2week_sequences, f, indent=2)

        print(
            f"Saved {len(all_weeks)} random weeks and {len(all_2week_sequences)} random 2-week sequences"
        )


def main():
    reprocessor = DataReprocessor()
    reprocessor.load_raw_pages()
    reprocessor.reprocess_all_data()
    reprocessor.filter_cycles_by_weeks()
    reprocessor.save_reprocessed_data()
    reprocessor.print_summary()
    restore_cycles()


if __name__ == "__main__":
    main()
