import json
import os

import streamlit as st


class PushJerkUI:
    def __init__(self):
        self.workouts = []
        self.cycles = []
        self.raw_pages = []
        self.load_data()

    def load_data(self):
        """Load data from JSON files"""
        try:
            # Load workouts
            workouts_file = os.path.join("data", "pushjerk_workouts.json")
            if os.path.exists(workouts_file):
                with open(workouts_file, "r", encoding="utf-8") as f:
                    self.workouts = json.load(f)

            # Load cycles
            cycles_file = os.path.join("data", "pushjerk_cycles.json")
            if os.path.exists(cycles_file):
                with open(cycles_file, "r", encoding="utf-8") as f:
                    self.cycles = json.load(f)

            # Load raw pages for original HTML
            html_file = os.path.join("data", "pushjerk_raw_pages.json")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    self.raw_pages = json.load(f)
        except Exception as e:
            st.error(f"Error loading data: {e}")

    def save_cycles(self):
        """Save updated cycles back to JSON"""
        cycles_file = os.path.join("data", "pushjerk_cycles.json")
        with open(cycles_file, "w", encoding="utf-8") as f:
            json.dump(self.cycles, f, indent=2, ensure_ascii=False)

    def get_workout_html(self, workout):
        """Get original HTML for a specific workout"""
        # Find the page containing this workout
        source_page = workout.get("source_page", 1)
        page_data = None
        for page in self.raw_pages:
            if page["page_number"] == source_page:
                page_data = page
                break

        if page_data:
            return page_data["html"]
        return "<p>Original HTML not found</p>"

    def run(self):
        st.set_page_config(page_title="PushJerk Workout Viewer", layout="wide")

        st.title("🏋️ PushJerk Workout Viewer")

        if not self.cycles:
            st.warning("No cycles found. Make sure you've scraped the data first.")
            return

        # Sidebar for cycle management
        with st.sidebar:
            st.header("Training Cycles")

            # Cycle selection and editing
            cycle_options = {}
            for cycle in self.cycles:
                cycle_name = cycle.get("name", f"Cycle {cycle['cycle_id']}")
                cycle_options[cycle_name] = cycle

            selected_cycle_name = st.selectbox("Select Cycle:", list(cycle_options.keys())[::-1])
            selected_cycle = cycle_options[selected_cycle_name]

            st.write(f"**Cycle ID:** {selected_cycle['cycle_id']}")
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
                    # Update cycle name
                    for i, cycle in enumerate(self.cycles):
                        if cycle["cycle_id"] == selected_cycle["cycle_id"]:
                            self.cycles[i]["name"] = new_name
                            break
                    self.save_cycles()
                    st.success("Cycle name updated!")
                    st.rerun()

            # Cycle info
            st.write(f"**Cycle ID:** {selected_cycle['cycle_id']}")
            if selected_cycle.get("total_weeks"):
                st.write(f"**Total Weeks:** {selected_cycle['total_weeks']}")
            st.write(f"**Workouts:** {len(selected_cycle['workouts'])}")

        # Get workouts for selected cycle
        cycle_workout_indices = selected_cycle["workouts"]
        cycle_workouts = []

        for i in cycle_workout_indices:
            if i < len(self.workouts):
                workout = self.workouts[i]
                cycle_workouts.append(workout)
            else:
                st.write(f"Debug - Index {i} out of range")

        # cycle_workouts = [self.workouts[i] for i in cycle_workout_indices if i < len(self.workouts)]

        if not cycle_workouts:
            st.error("No workouts found for this cycle")
            return

        # Organize workouts by weeks using the cycle's week structure
        if "weeks" in selected_cycle and selected_cycle["weeks"]:
            # Use pre-organized weeks
            weeks = {}
            for week_data in selected_cycle["weeks"]:
                week_num = week_data["week_number"]
                week_workouts = []
                for workout_idx in week_data["workouts"]:
                    if workout_idx < len(self.workouts):
                        week_workouts.append(self.workouts[workout_idx])
                weeks[week_num] = week_workouts
        else:
            # Fallback: organize by day sequence
            weeks = {}
            current_week = 1
            current_week_workouts = []

            for workout in cycle_workouts:
                if workout.get("day") == "mon" and current_week_workouts:
                    weeks[current_week] = current_week_workouts
                    current_week += 1
                    current_week_workouts = []
                current_week_workouts.append(workout)

            if current_week_workouts:
                weeks[current_week] = current_week_workouts

        # Week selection
        col1, col2 = st.columns([1, 3])

        with col1:
            st.subheader("Weeks")
            week_numbers = sorted(weeks.keys())
            selected_week = st.radio(
                "Select Week:",
                week_numbers,
                format_func=lambda x: f"Week {x} ({len(weeks[x])} workouts)",
            )

        with col2:
            st.subheader(f"Week {selected_week} Workouts")

            # Workout selection
            week_workouts = weeks[selected_week]
            workout_options = []
            for i, workout in enumerate(week_workouts):
                title = workout.get("title", f"Workout {i+1}")
                workout_options.append(f"{title}")

            selected_workout_idx = st.selectbox(
                "Select Workout:",
                range(len(workout_options)),
                format_func=lambda x: workout_options[x],
            )

            selected_workout = week_workouts[selected_workout_idx]

        # Display workout
        st.divider()

        # Workout header
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.header(selected_workout.get("title", "Untitled Workout"))
        with col2:
            st.metric("Week", selected_week)
        with col3:
            st.metric("Exercise Links", len(selected_workout.get("exercise_links", [])))

        # Display options
        display_mode = st.radio(
            "Display Mode:", ["Processed Content", "Original HTML"], horizontal=True
        )

        if display_mode == "Processed Content":
            st.subheader("Workout Content")

            # Exercise links
            exercise_links = selected_workout.get("exercise_links", [])
            if exercise_links:
                st.subheader("Exercise Links")
                for link in exercise_links:
                    st.markdown(f"- [{link['text']}]({link['url']})")

            # Content
            content = selected_workout.get("content", "")
            if content:
                st.text_area("Workout Details:", content, height=300, disabled=True)

        if display_mode == "Original HTML":
            st.subheader("Original HTML")
            workout_html = self.get_workout_html(selected_workout)

            # Render HTML
            st.components.v1.html(workout_html, height=600, scrolling=True)


def main():
    ui = PushJerkUI()
    ui.run()


if __name__ == "__main__":
    main()
