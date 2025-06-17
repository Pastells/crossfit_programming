import json
import os
import random
import re

import streamlit as st
from bs4 import BeautifulSoup

from backup_names import backup_cycles

DAYS = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

SESSION_FILE = "app_session.json"


def load_session_state():
    """Load the last session state"""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "last_visited_type": None,
        "last_cycle_id": None,
        "last_week_number": None,
        "last_random_week_id": None,
        "last_random_2week_id": None,
    }


def save_session_state(state):
    """Save the current session state"""
    with open(SESSION_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_current_selection(selection_type, **kwargs):
    """Update and save current selection"""
    state = load_session_state()
    state["last_visited_type"] = selection_type

    if selection_type == "cycle":
        state["last_cycle_id"] = kwargs.get("cycle_id")
        state["last_week_number"] = kwargs.get("week_number")
    elif selection_type == "random_week":
        state["last_random_week_id"] = kwargs.get("week_id")
    elif selection_type == "random_2week":
        state["last_random_2week_id"] = kwargs.get("two_week_id")

    save_session_state(state)


def extract_workout_html(raw_html, target_date):
    """Extract clean HTML for a specific workout date"""
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        articles = soup.find_all("article")

        for article in articles:
            entry_title = article.find("h2", class_="entry-title")
            if entry_title:
                title_text = entry_title.get_text().strip()
                if target_date in title_text:
                    entry_content = article.find("div", class_="entry-content")
                    if entry_content:
                        return clean_workout_html(str(entry_content))
        return None
    except Exception as e:
        st.error(f"Error extracting workout HTML: {e}")
        return None


def convert_pounds_to_kg(match):
    weights = match.group(1)
    weight_parts = weights.split("/")
    converted_parts = []

    for weight in weight_parts:
        try:
            lb_value = float(weight.strip())
            kg_value = round(lb_value * 0.453592 / 0.5) * 0.5

            if kg_value.is_integer():
                converted_parts.append(str(int(kg_value)))
            else:
                converted_parts.append(str(kg_value))
        except ValueError:
            converted_parts.append(weight)

    return "/".join(converted_parts) + "kg"


def clean_workout_html(html_content):
    """Clean HTML content while preserving formatting"""
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove unwanted elements
    for tag in soup(["script", "style", "meta", "link", "head", "nav", "header", "footer"]):
        tag.decompose()

    # Clean up attributes but keep href for links
    for tag in soup.find_all():
        if tag.name == "a":
            attrs = dict(tag.attrs)
            tag.attrs.clear()
            if "href" in attrs:
                tag["href"] = attrs["href"]
                tag["target"] = "_blank"
        else:
            allowed_attrs = ["class"] if tag.name in ["strong", "em", "b", "i"] else []
            attrs = dict(tag.attrs)
            tag.attrs.clear()
            for attr in allowed_attrs:
                if attr in attrs:
                    tag[attr] = attrs[attr]

    # Remove the outer div.entry-content wrapper but keep its contents
    if soup.find("div", class_="entry-content"):
        content_div = soup.find("div", class_="entry-content")
        content_html = "".join(str(child) for child in content_div.children)
    else:
        content_html = str(soup)

    # Regex pattern to match weight formats like "53/35#", "45#", etc.
    weight_pattern = r"(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*)#"
    content_html = re.sub(weight_pattern, convert_pounds_to_kg, content_html)

    return content_html


class PushJerkUI:
    def __init__(self):
        self.workouts = []
        self.cycles = []
        self.raw_pages = []
        self.random_weeks = []
        self.random_2weeks = []
        self.load_data()

    def load_data(self):
        """Load data from JSON files"""
        try:
            # Load workouts
            workouts_file = os.path.join("data", "pushjerk_workouts.json")
            if os.path.exists(workouts_file):
                with open(workouts_file, "r", encoding="utf-8") as f:
                    self.workouts = json.load(f)

            # Load cycles (now only contains cycles with 3+ weeks)
            cycles_file = os.path.join("data", "pushjerk_cycles.json")
            if os.path.exists(cycles_file):
                with open(cycles_file, "r", encoding="utf-8") as f:
                    self.cycles = json.load(f)

            # Load raw pages for original HTML
            html_file = os.path.join("data", "pushjerk_raw_pages.json")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    self.raw_pages = json.load(f)

            # Load random weeks data
            random_weeks_file = os.path.join("data", "random_weeks.json")
            if os.path.exists(random_weeks_file):
                with open(random_weeks_file, "r", encoding="utf-8") as f:
                    self.random_weeks = json.load(f)

            # Load random 2weeks data
            random_2weeks_file = os.path.join("data", "random_2weeks.json")
            if os.path.exists(random_2weeks_file):
                with open(random_2weeks_file, "r", encoding="utf-8") as f:
                    self.random_2weeks = json.load(f)

        except Exception as e:
            st.error(f"Error loading data: {e}")

    def save_cycles(self):
        """Save updated cycles back to JSON"""
        cycles_file = os.path.join("data", "pushjerk_cycles.json")
        with open(cycles_file, "w", encoding="utf-8") as f:
            json.dump(self.cycles, f, indent=2, ensure_ascii=False)

    def get_workout_html(self, workout):
        """Get original HTML for a specific workout"""
        source_page = workout.get("source_page", 1)
        page_data = None
        for page in self.raw_pages:
            if page["page_number"] == source_page:
                page_data = page
                break

        if not page_data:
            return None

        workout_title = workout.get("title", "")
        extracted_html = extract_workout_html(page_data["html"], workout_title)
        return extracted_html

    def display_week_workouts(self, week_data):
        """Display workouts in a week with previews"""
        workouts = week_data.get("workouts", [])

        workouts_by_day = {}

        for workout in workouts:
            day = workout.get("day", "unknown")
            if day not in workouts_by_day:
                workouts_by_day[day] = []
            workouts_by_day[day].append(workout)

        # Display workouts in day order
        for day in DAYS.keys():
            if day in workouts_by_day:
                day_workouts = workouts_by_day[day]
                for workout in day_workouts:
                    preview = workout.get("preview", "")
                    st.write(f"**{DAYS[day]}**: {preview}")

    def display_workout_content(self, workout, cycle_info=None, week_info=None):
        """Display workout content with header"""
        # Workout header
        # col1, col2, col3 = st.columns([3, 1, 1])
        # with col1:
        #     st.header(workout.get("title", "Untitled Workout"))
        # with col2:
        #     if cycle_info:
        #         st.metric("Cycle", cycle_info)
        # with col3:
        #     if week_info:
        #         st.metric("Week", week_info)

        workout_html = self.get_workout_html(workout)

        if workout_html:
            st.markdown(
                f"""
            <div style="
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 20px;
                margin: 10px 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
            ">
                {workout_html}
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            st.info("Original formatted content not available for this workout.")

    def show_cycle_selection(self):
        """Display cycle selection interface"""
        if not self.cycles:
            st.warning("No cycles with 3+ weeks found.")
            return

        # Load saved state
        saved_state = load_session_state()

        # Sidebar for cycle management
        with st.sidebar:
            st.header("Training Cycles")

            # Cycle selection and editing
            cycle_options = {}
            for cycle in self.cycles:
                cycle_name = cycle.get("name", f"Cycle {cycle['cycle_id']}")
                week_count = len(cycle["weeks"])
                cycle_name = f"{cycle_name} ({week_count} weeks)"
                cycle_options[cycle_name] = cycle

            # Try to restore last selected cycle
            cycle_names = list(cycle_options.keys())[::-1]  # Reverse order
            default_cycle_index = 0
            if saved_state.get("last_cycle_id") is not None:
                try:
                    for i, cycle_name in enumerate(cycle_names):
                        if cycle_options[cycle_name]["cycle_id"] == saved_state["last_cycle_id"]:
                            default_cycle_index = i
                            break
                except:
                    pass

            selected_cycle_name = st.selectbox(
                "Select Cycle:", cycle_names, index=default_cycle_index
            )
            selected_cycle = cycle_options[selected_cycle_name]

            if selected_cycle.get("total_weeks"):
                st.write(f"**Total Weeks:** {selected_cycle['total_weeks']}")
            st.write(f"**Workouts:** {len(selected_cycle['workouts'])}")

            # Edit cycle name
            with st.expander("Edit Cycle Name"):
                new_name = st.text_input(
                    "Cycle Name:",
                    value=selected_cycle.get("name", f"Cycle {selected_cycle['cycle_id']}"),
                    key=f"cycle_name_{selected_cycle['cycle_id']}",
                )
                if st.button("Save Name", key=f"save_name_{selected_cycle['cycle_id']}"):
                    for i, cycle in enumerate(self.cycles):
                        if cycle["cycle_id"] == selected_cycle["cycle_id"]:
                            self.cycles[i]["name"] = new_name
                            break
                    self.save_cycles()
                    backup_cycles()
                    st.success("Cycle name updated!")
                    st.rerun()

        # Organize workouts by weeks using the cycle's week structure
        weeks = {}
        if "weeks" in selected_cycle and selected_cycle["weeks"]:
            for week_data in selected_cycle["weeks"]:
                week_num = week_data["week_number"]
                week_workouts = []
                for workout_idx in week_data["workouts"]:
                    if workout_idx < len(self.workouts):
                        week_workouts.append(self.workouts[workout_idx])
                weeks[week_num] = week_workouts

        if not weeks:
            st.error("No weeks found for this cycle")
            return

        col1, _, col2 = st.columns([1, 0.2, 2])

        with col1:
            # Week selection
            week_numbers = sorted(weeks.keys())

            # Try to restore last selected week
            default_week_index = 0
            if saved_state.get("last_week_number") in week_numbers:
                try:
                    default_week_index = week_numbers.index(saved_state["last_week_number"])
                except:
                    pass

            selected_week = st.selectbox(
                "Select Week:",
                week_numbers,
                format_func=lambda x: f"Week {x}",
                index=default_week_index,
            )

        with col2:
            # Workout selection
            week_workouts = weeks[selected_week]
            workout_options = []
            for i, workout in enumerate(week_workouts):
                day = workout.get("day", f"Workout {i+1}")
                preview = workout.get("preview", "")
                workout_options.append(f"{DAYS[day]}: {preview}")
                # workout_options.append(f"{DAYS[day]}")

            selected_workout_idx = st.selectbox(
                "Select Workout:",
                range(len(workout_options)),
                format_func=lambda x: workout_options[x],
            )

            selected_workout = week_workouts[selected_workout_idx]

            # week_display_data = {
            #     "week_number": selected_week,
            #     "workouts": week_workouts,
            # }
            # self.display_week_workouts(week_display_data)

        # Save current selection
        update_current_selection(
            "cycle", cycle_id=selected_cycle["cycle_id"], week_number=selected_week
        )

        self.display_workout_content(
            selected_workout, cycle_info=selected_cycle["cycle_id"], week_info=selected_week
        )

    def show_random_week(self):
        """Display random week interface"""
        if not self.random_weeks:
            st.warning("No random weeks available.")
            return

        # Initialize or get current random week
        if "current_random_week" not in st.session_state:
            saved_state = load_session_state()
            if saved_state.get("last_random_week_id") is not None:
                try:
                    week_id = saved_state["last_random_week_id"]
                    if 0 <= week_id < len(self.random_weeks):
                        st.session_state.current_random_week = self.random_weeks[week_id]
                        st.session_state.current_random_week_id = week_id
                    else:
                        raise IndexError()
                except:
                    # Fallback to random selection
                    week = random.choice(self.random_weeks)
                    st.session_state.current_random_week = week
                    st.session_state.current_random_week_id = self.random_weeks.index(week)
            else:
                week = random.choice(self.random_weeks)
                st.session_state.current_random_week = week
                st.session_state.current_random_week_id = self.random_weeks.index(week)

        week = st.session_state.current_random_week

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Random Week: {week['cycle_name']}")
        with col2:
            if st.button("🎲 Get Another Random Week", use_container_width=True):
                new_week = random.choice(self.random_weeks)
                st.session_state.current_random_week = new_week
                st.session_state.current_random_week_id = self.random_weeks.index(new_week)
                update_current_selection(
                    "random_week", week_id=st.session_state.current_random_week_id
                )
                st.rerun()

        # Display workouts in this week
        week_workouts = []
        for workout_idx in week["workouts"]:
            if workout_idx < len(self.workouts):
                week_workouts.append(self.workouts[workout_idx])

        if week_workouts:
            workout_options = [
                workout.get("title", f"Workout {i+1}") for i, workout in enumerate(week_workouts)
            ]

            selected_workout_idx = st.selectbox(
                "Select Workout:",
                range(len(workout_options)),
                format_func=lambda x: workout_options[x],
            )

            selected_workout = week_workouts[selected_workout_idx]

            # Save selection
            update_current_selection("random_week", week_id=st.session_state.current_random_week_id)

            st.divider()
            self.display_workout_content(
                selected_workout,
                cycle_info=week["cycle_name"],
                week_info=f"Week {week['week_number']}",
            )
        else:
            st.error("No workouts found for this week")

    def show_random_2weeks(self):
        """Display random 2 weeks interface"""
        if not self.random_2weeks:
            st.warning("No random 2-week sequences available.")
            return

        # Initialize or get current random 2 weeks
        if "current_random_2week" not in st.session_state:
            saved_state = load_session_state()
            if saved_state.get("last_random_2week_id") is not None:
                try:
                    two_week_id = saved_state["last_random_2week_id"]
                    if 0 <= two_week_id < len(self.random_2weeks):
                        st.session_state.current_random_2week = self.random_2weeks[two_week_id]
                        st.session_state.current_random_2week_id = two_week_id
                    else:
                        raise IndexError()
                except:
                    two_week = random.choice(self.random_2weeks)
                    st.session_state.current_random_2week = two_week
                    st.session_state.current_random_2week_id = self.random_2weeks.index(two_week)
            else:
                two_week = random.choice(self.random_2weeks)
                st.session_state.current_random_2week = two_week
                st.session_state.current_random_2week_id = self.random_2weeks.index(two_week)

        two_week = st.session_state.current_random_2week

        col1, col2 = st.columns([3, 1])
        with col1:
            week_nums = two_week["week_numbers"]
            st.subheader(f"Random 2 Weeks: {two_week['cycle_name']}")
        with col2:
            if st.button("🎲 Get Another Random 2 Weeks", use_container_width=True):
                new_two_week = random.choice(self.random_2weeks)
                st.session_state.current_random_2week = new_two_week
                st.session_state.current_random_2week_id = self.random_2weeks.index(new_two_week)
                update_current_selection(
                    "random_2week", two_week_id=st.session_state.current_random_2week_id
                )
                st.rerun()

        # Display both weeks
        for i, week_data in enumerate(two_week["weeks"]):
            week_num = week_data["week_number"]
            st.subheader(f"Week {week_num}")

            # Get workouts for this week
            week_workouts = []
            for workout_idx in week_data["workouts"]:
                if workout_idx < len(self.workouts):
                    week_workouts.append(self.workouts[workout_idx])

            if week_workouts:
                workout_options = [
                    workout.get("title", f"Workout {j+1}")
                    for j, workout in enumerate(week_workouts)
                ]

                selected_workout_idx = st.selectbox(
                    "Select Workout:",
                    range(len(workout_options)),
                    format_func=lambda x: workout_options[x],
                    key=f"workout_selector_week_{week_num}",
                )

                selected_workout = week_workouts[selected_workout_idx]

                # Display workout content
                self.display_workout_content(
                    selected_workout,
                    cycle_info=two_week["cycle_name"],
                    week_info=f"Week {week_num}",
                )

                if i < len(two_week["weeks"]) - 1:  # Add separator between weeks
                    st.divider()

        # Save selection
        update_current_selection(
            "random_2week", two_week_id=st.session_state.current_random_2week_id
        )

    def run(self):
        st.set_page_config(page_title="PushJerk Workout Viewer", layout="wide")

        st.title("🏋️ PushJerk Workout Viewer")

        # Initialize selection type from saved state
        if "selection_type" not in st.session_state:
            saved_state = load_session_state()
            st.session_state.selection_type = saved_state.get("last_visited_type", "cycle")

        # Selection buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📚 Training Cycles", use_container_width=True):
                st.session_state.selection_type = "cycle"
                st.rerun()

        with col2:
            if st.button("🎲 Random Week", use_container_width=True):
                st.session_state.selection_type = "random_week"
                # Clear current selection to force new random selection
                if "current_random_week" in st.session_state:
                    del st.session_state.current_random_week
                st.rerun()

        with col3:
            if st.button("🎯 Random 2 Weeks", use_container_width=True):
                st.session_state.selection_type = "random_2week"
                # Clear current selection to force new random selection
                if "current_random_2week" in st.session_state:
                    del st.session_state.current_random_2week
                st.rerun()

        st.divider()

        # Display based on selection type
        if st.session_state.selection_type == "cycle":
            self.show_cycle_selection()
        elif st.session_state.selection_type == "random_week":
            self.show_random_week()
        elif st.session_state.selection_type == "random_2week":
            self.show_random_2weeks()


def main():
    ui = PushJerkUI()
    ui.run()


if __name__ == "__main__":
    main()
