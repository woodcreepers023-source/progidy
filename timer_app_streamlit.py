import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import requests
import json
from pathlib import Path

# ------------------- Config -------------------
MANILA = ZoneInfo("Asia/Manila")
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_HERE"  # <-- put your Discord webhook URL here
DATA_FILE = Path("boss_timers.json")
HISTORY_FILE = Path("boss_history.json")
ADMIN_PASSWORD = "bestgame"


def send_discord_message(message: str):
    """Send a message to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_HERE":
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception as e:
        print(f"Discord webhook error: {e}")


# ------------------- Default Boss Data -------------------
# Only Waterlord as the field/world boss
# 20 minutes 10 seconds = 20 + 10/60 = 20.1666667 minutes
default_boss_data = [
    ("Waterlord", 20.1666667, "2025-09-20 08:00 AM"),
]


# ------------------- JSON Persistence -------------------
def _safe_load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # If file is corrupted or empty, just fall back
        return default


def load_boss_data():
    """
    Stored format in JSON: [ [name, interval_minutes, last_time_str], ... ]
    """
    data = _safe_load_json(DATA_FILE, None)

    if data is None:
        # First run: use default data
        data = default_boss_data.copy()
    else:
        # If JSON was saved as list of dicts accidentally, normalize it
        if data and isinstance(data[0], dict):
            normalized = []
            for d in data:
                normalized.append(
                    (d["name"], d["interval_minutes"], d["last_time_str"])
                )
            data = normalized

        # Ensure elements are tuple/list-like of length 3 and cast interval to float
        cleaned = []
        for entry in data:
            if isinstance(entry, (list, tuple)) and len(entry) == 3:
                name, interval_minutes, last_time_str = entry
                try:
                    interval_minutes = float(interval_minutes)
                except (TypeError, ValueError):
                    interval_minutes = 20.1666667
                cleaned.append((name, interval_minutes, last_time_str))
        data = cleaned

    # Always keep ONLY Waterlord
    FIXED_INTERVAL_MINUTES = 20.1666667  # 20m 10s
    waterlords = [entry for entry in data if entry[0] == "Waterlord"]

    if waterlords:
        # Keep last_time_str from file, override interval to fixed value
        name, _old_interval, last_time_str = waterlords[0]
        data = [(name, FIXED_INTERVAL_MINUTES, last_time_str)]
    else:
        # Fallback to default, but still enforce fixed interval
        name, _old_interval, last_time_str = default_boss_data[0]
        data = [(name, FIXED_INTERVAL_MINUTES, last_time_str)]

    # Save cleaned data back to JSON
    save_boss_data(data)

    return data


def save_boss_data(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def log_edit(boss_name, old_time, new_time):
    history = _safe_load_json(HISTORY_FILE, [])
    edited_by = st.session_state.get("username", "Unknown")

    entry = {
        "boss": boss_name,
        "old_time": old_time,
        "new_time": new_time,
        "edited_at": datetime.now(tz=MANILA).strftime("%Y-%m-%d %I:%M %p"),
        "edited_by": edited_by,
    }

    history.append(entry)

    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

    # Generic edit log to Discord
    send_discord_message(
        f"🛠 **{boss_name}** time updated by **{edited_by}**\n"
        f"Old: `{old_time}` → New: `{new_time}` (Manila time)"
    )


# ------------------- Timer Class -------------------
class TimerEntry:
    def __init__(self, name, interval_minutes, last_time_str):
        self.name = name
        # Allow decimals in minutes (e.g. 20.1666667)
        self.interval_minutes = float(interval_minutes)
        # Convert minutes (possibly decimal) to seconds
        self.interval = int(self.interval_minutes * 60)

        parsed_time = datetime.strptime(last_time_str, "%Y-%m-%d %I:%M %p").replace(
            tzinfo=MANILA
        )
        self.last_time = parsed_time
        self.next_time = self.last_time + timedelta(seconds=self.interval)

    def update_next(self):
        now = datetime.now(tz=MANILA)
        while self.next_time < now:
            self.last_time = self.next_time
            self.next_time = self.last_time + timedelta(seconds=self.interval)

    def countdown(self):
        return self.next_time - datetime.now(tz=MANILA)

    def format_countdown(self):
        td = self.countdown()
        total_seconds = int(td.total_seconds())
        if total_seconds < 0:
            return "00:00:00"
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
        return f"{hours:02}:{minutes:02}:{seconds:02}"


# Helper for weekly countdown formatting
def format_timedelta(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "00:00:00"
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    return f"{hours:02}:{minutes:02}:{seconds:02}"


# ------------------- Build Timers -------------------
def build_timers():
    return [TimerEntry(*data) for data in load_boss_data()]


# ------------------- Streamlit Setup -------------------
st.set_page_config(page_title="Lord9 Santiago 7 Boss Timer", layout="wide")
st.title("🛡️ Lord9 Santiago 7 Boss Timer")
st_autorefresh(interval=1000, key="timer_refresh")

if "timers" not in st.session_state:
    st.session_state.timers = build_timers()
timers = st.session_state.timers

# ------------------- Password Gate -------------------
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    username = st.text_input("Enter your name:")
    password = st.text_input("🔑 Enter password to edit timers:", type="password")
    if password == ADMIN_PASSWORD and username.strip():
        st.session_state.auth = True
        st.session_state.username = username.strip()
        st.success(f"✅ Access granted for {st.session_state.username}")

# ------------------- Weekly Boss Data (Capricorn only) -------------------
weekly_boss_data = [
    ("Capricorn", ["Sunday 20:00"]),  # Change day/time here if needed
]


def get_next_weekly_spawn(day_time: str):
    """Convert 'Monday 11:30' to next datetime in Manila timezone."""
    now = datetime.now(tz=MANILA)
    day, time_str = day_time.split()
    target_time = datetime.strptime(time_str, "%H:%M").time()

    weekday_map = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }
    target_weekday = weekday_map[day]

    days_ahead = (target_weekday - now.weekday()) % 7
    spawn_date = (now + timedelta(days=days_ahead)).date()
    spawn_dt = datetime.combine(spawn_date, target_time).replace(tzinfo=MANILA)

    if spawn_dt <= now:
        spawn_dt += timedelta(days=7)

    return spawn_dt


# ------------------- Next Boss Banner -------------------
def next_boss_banner(timers_list):
    # Update field timers
    for t in timers_list:
        t.update_next()

    # Soonest field boss (only Waterlord now)
    field_next = min(timers_list, key=lambda x: x.countdown())
    field_cd = field_next.countdown()

    # Soonest weekly boss
    now = datetime.now(tz=MANILA)
    weekly_best_name = None
    weekly_best_time = None
    weekly_best_cd = None

    for boss, times in weekly_boss_data:
        for sched in times:
            spawn_dt = get_next_weekly_spawn(sched)
            cd = spawn_dt - now
            if weekly_best_cd is None or cd < weekly_best_cd:
                weekly_best_cd = cd
                weekly_best_name = boss
                weekly_best_time = spawn_dt

    # Decide which spawns next (field vs weekly)
    chosen_name = field_next.name
    chosen_time = field_next.next_time
    chosen_cd = field_cd
    from_weekly = False

    if weekly_best_cd is not None and weekly_best_cd < field_cd:
        from_weekly = True
        chosen_name = weekly_best_name
        chosen_time = weekly_best_time
        chosen_cd = weekly_best_cd

    remaining = chosen_cd.total_seconds()

    # Color logic for countdown
    if remaining <= 60:
        cd_color = "red"
    elif remaining <= 300:
        cd_color = "orange"
    else:
        cd_color = "limegreen"

    time_only = chosen_time.strftime("%I:%M %p")
    cd_str = format_timedelta(chosen_cd) if from_weekly else field_next.format_countdown()

    st.markdown(
        f"""
        <style>
        .banner-container {{
            display: flex;
            justify-content: center;
            margin: 20px 0 5px 0;
        }}
        .boss-banner {{
            background: linear-gradient(90deg, #0f172a, #1d4ed8, #16a34a);
            padding: 14px 28px;
            border-radius: 999px;
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.75);
            color: #f9fafb;
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }}
        .boss-banner-title {{
            font-size: 28px;
            font-weight: 800;
            margin: 0;
            letter-spacing: 0.03em;
        }}
        .boss-banner-row {{
            display: flex;
            align-items: center;
            gap: 14px;
            font-size: 18px;
        }}
        .banner-chip {{
            padding: 4px 12px;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(148, 163, 184, 0.7);
        }}
        </style>

        <div class="banner-container">
            <div class="boss-banner">
                <h2 class="boss-banner-title">
                    Next Boss: <strong>{chosen_name}</strong>
                </h2>
                <div class="boss-banner-row">
                    <span class="banner-chip">
                        🕒 <strong>{time_only}</strong>
                    </span>
                    <span class="banner-chip" style="color:{cd_color}; border-color:{cd_color};">
                        ⏳ <strong>{cd_str}</strong>
                    </span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------- Auto-Sorted Field Boss Table -------------------
def display_boss_table_sorted(timers_list):
    for t in timers_list:
        t.update_next()

    timers_sorted = sorted(timers_list, key=lambda t: t.next_time)

    # Build colored countdown values
    countdown_cells = []
    for t in timers_sorted:
        secs_left = t.countdown().total_seconds()
        if secs_left <= 60:
            color = "red"
        elif secs_left <= 300:
            color = "orange"
        else:
            color = "green"
        countdown_cells.append(
            f"<span style='color:{color}'>{t.format_countdown()}</span>"
        )

    # Human-readable interval like "20m 10s"
    interval_labels = []
    for t in timers_sorted:
        total_secs = t.interval
        mins = total_secs // 60
        secs = total_secs % 60
        if secs > 0:
            interval_labels.append(f"{mins}m {secs:02}s")
        else:
            interval_labels.append(f"{mins}m")

    data = {
        "Boss Name": [t.name for t in timers_sorted],
        "Interval": interval_labels,

        # numeric date + 24-hour time
        "Last Spawn": [
            t.last_time.strftime("%Y/%m/%d - %H:%M") for t in timers_sorted
        ],

        "Next Spawn Time": [t.next_time.strftime("%I:%M %p") for t in timers_sorted],
        "Countdown": countdown_cells,
    }

    df = pd.DataFrame(data)
    st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)


# ------------------- Weekly Table: Boss | Day | Time | Countdown -------------------
def display_weekly_boss_table():
    """Display sorted weekly bosses by nearest spawn time with columns:
       Boss, Day, Time (12h), Countdown."""
    upcoming = []
    now = datetime.now(tz=MANILA)

    for boss, times in weekly_boss_data:
        for sched in times:
            spawn_dt = get_next_weekly_spawn(sched)
            countdown = spawn_dt - now
            upcoming.append((boss, spawn_dt, countdown))

    upcoming_sorted = sorted(upcoming, key=lambda x: x[1])

    data = {
        "Boss Name": [row[0] for row in upcoming_sorted],
        "Day": [row[1].strftime("%A") for row in upcoming_sorted],
        "Time": [row[1].strftime("%I:%M %p") for row in upcoming_sorted],
        "Countdown": [
            f"<span style='color:{'red' if row[2].total_seconds() <= 60 else 'orange' if row[2].total_seconds() <= 300 else 'green'}'>{format_timedelta(row[2])}</span>"
            for row in upcoming_sorted
        ],
    }

    df = pd.DataFrame(data)
    st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)


# ---- Show the combined (field + weekly) next boss banner ----
next_boss_banner(timers)

# ------------------- Tabs -------------------
tabs = ["World Boss Spawn"]
if st.session_state.auth:
    tabs.append("Manage & Edit Timers")
    tabs.append("Edit History")
tab_selection = st.tabs(tabs)

# Tab 1: World Boss Spawn
with tab_selection[0]:
    st.subheader("🗡️ Field Boss Spawn Table")

    # Side-by-side layout (field + weekly)
    col1, col2 = st.columns([2, 1])  # left = bigger
    with col1:
        display_boss_table_sorted(timers)
    with col2:
        st.subheader("📅 Fixed Time Field Boss Spawn Table")
        display_weekly_boss_table()

# Tab 2: Manage & Edit Timers
if st.session_state.auth:
    with tab_selection[1]:
        st.subheader("Edit Boss Timers (Edit Last Time, Next auto-updates)")
        for i, timer in enumerate(timers):
            with st.expander(f"Edit {timer.name}", expanded=False):

                # Date should always default to TODAY
                today = datetime.now(tz=MANILA).date()

                # Time should remain the STORED LAST SPAWN TIME
                stored_time = timer.last_time.time()

                new_date = st.date_input(
                    f"{timer.name} Last Date",
                    value=today,
                    key=f"{timer.name}_last_date_{i}",
                )
                new_time = st.time_input(
                    f"{timer.name} Last Time",
                    value=stored_time,
                    key=f"{timer.name}_last_time_{i}",
                    step=60,
                )

                # Extra: Killer name for Waterlord Discord drop message
                killer_name = ""
                if timer.name == "Waterlord":
                    killer_name = st.text_input(
                        "Killer name (for Discord message)",
                        key=f"{timer.name}_killer_{i}",
                        placeholder="Type killer's name here...",
                    )

                if st.button(f"Save {timer.name}", key=f"save_{timer.name}_{i}"):
                    old_time_str = timer.last_time.strftime("%Y-%m-%d %I:%M %p")

                    updated_last_time = datetime.combine(new_date, new_time).replace(
                        tzinfo=MANILA
                    )
                    updated_next_time = updated_last_time + timedelta(
                        seconds=timer.interval
                    )

                    st.session_state.timers[i].last_time = updated_last_time
                    st.session_state.timers[i].next_time = updated_next_time

                    # Save to JSON
                    save_boss_data(
                        [
                            (
                                t.name,
                                t.interval_minutes,
                                t.last_time.strftime("%Y-%m-%d %I:%M %p"),
                            )
                            for t in st.session_state.timers
                        ]
                    )

                    # Log edit (generic log)
                    log_edit(
                        timer.name,
                        old_time_str,
                        updated_last_time.strftime("%Y-%m-%d %I:%M %p"),
                    )

                    # Special Discord message for Waterlord drop
                    if timer.name == "Waterlord":
                        name_part = killer_name.strip() or "Unknown Hero"
                        drop_msg = (
                            f"[ProdigyCO] CONGRATS A rare CleanWater has dropped "
                            f"from the WaterDevil killed by {name_part}"
                        )
                        send_discord_message(drop_msg)

                    st.success(
                        f"✅ {timer.name} updated! Next: {updated_next_time.strftime('%Y-%m-%d %I:%M %p')}"
                    )


# Tab 3: Edit History
if st.session_state.auth:
    with tab_selection[2]:
        st.subheader("Edit History")

        history = _safe_load_json(HISTORY_FILE, [])
        if history:
            df_history = pd.DataFrame(history)

            # Convert edited_at string -> real datetime for correct sorting
            df_history["edited_at_dt"] = pd.to_datetime(
                df_history["edited_at"],
                format="%Y-%m-%d %I:%M %p",
                errors="coerce",
            )

            # Sort newest → oldest
            df_history = (
                df_history.sort_values("edited_at_dt", ascending=False)
                .drop(columns=["edited_at_dt"])
                .reset_index(drop=True)
            )

            st.dataframe(df_history, use_container_width=True)
        else:
            st.info("No edits yet.")
