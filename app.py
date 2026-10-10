
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="CleanSpot",
    page_icon="♻️",
    layout="wide"
)

DB = "cleanspot.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_connection():
    return sqlite3.connect(DB)


def initialize_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id TEXT PRIMARY KEY,
            location TEXT NOT NULL,
            area_type TEXT,
            description TEXT,
            image_path TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'Pending',
            latitude REAL,
            longitude REAL
        )
    """)

    columns = {
        row[1] for row in
        conn.execute("PRAGMA table_info(complaints)").fetchall()
    }

    for column in ("latitude", "longitude"):
        if column not in columns:
            conn.execute(
                f"ALTER TABLE complaints ADD COLUMN {column} REAL"
            )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cleanup_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            action TEXT NOT NULL,
            assigned_to TEXT,
            target_date TEXT,
            status TEXT DEFAULT 'Pending',
            completed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_reports():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM complaints ORDER BY created_at DESC",
        conn
    )
    conn.close()
    return df


def save_complaint(
    location, area_type, description,
    image_path, latitude, longitude
):
    complaint_id = "CS-" + uuid.uuid4().hex[:8].upper()

    conn = get_connection()
    conn.execute("""
        INSERT INTO complaints (
            id, location, area_type, description,
            image_path, created_at, status,
            latitude, longitude
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        complaint_id,
        location.strip(),
        area_type,
        description.strip(),
        image_path,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Pending",
        latitude,
        longitude
    ))

    conn.commit()
    conn.close()
    return complaint_id


def update_complaint_status(complaint_id, status):
    conn = get_connection()
    conn.execute(
        "UPDATE complaints SET status=? WHERE id=?",
        (status, complaint_id)
    )
    conn.commit()
    conn.close()


def get_hotspots(df):
    columns = ["Location", "Reports", "Area"]

    if df.empty:
        return pd.DataFrame(columns=columns)

    data = df.copy()
    data["created_at"] = pd.to_datetime(
        data["created_at"], errors="coerce"
    )

    cutoff = datetime.now() - timedelta(days=30)

    data = data[
        (data["created_at"] >= cutoff) &
        data["location"].notna()
    ].copy()

    if data.empty:
        return pd.DataFrame(columns=columns)

    data["location_key"] = (
        data["location"].astype(str).str.strip().str.casefold()
    )

    result = data.groupby("location_key").agg(
        Location=("location", "first"),
        Reports=("id", "count"),
        Area=("area_type", "first")
    ).reset_index(drop=True)

    result = result[result["Reports"] >= 3]

    return result.sort_values(
        "Reports", ascending=False
    ).reset_index(drop=True)


def prevention_advice(area):
    advice = {
        "Residential area":
            "Improve household waste collection and inform residents "
            "about proper waste disposal.",
        "Roadside":
            "Provide accessible bins, improve collection frequency, "
            "and monitor repeated dumping.",
        "Near drain or water body":
            "Keep waste away from drains and waterways and arrange "
            "regular cleaning.",
        "Vacant plot":
            "Coordinate with the property owner, arrange waste "
            "collection, and consider warning signs.",
        "Commercial area":
            "Coordinate with nearby businesses and ensure regular "
            "waste collection.",
        "Other":
            "Investigate repeated dumping and improve access to "
            "proper disposal facilities."
    }

    return advice.get(area, advice["Other"])


def save_uploaded_image(uploaded_file):
    if uploaded_file is None:
        return None

    extension = os.path.splitext(uploaded_file.name)[1].lower()

    if extension not in [".jpg", ".jpeg", ".png"]:
        return None

    filename = uuid.uuid4().hex + extension
    path = os.path.join(UPLOAD_DIR, filename)

    with open(path, "wb") as file:
        file.write(uploaded_file.getbuffer())

    return path


def get_cleanup_actions():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM cleanup_actions ORDER BY id DESC",
        conn
    )
    conn.close()
    return df


def save_cleanup_action(location, action, assigned_to, target_date):
    conn = get_connection()
    conn.execute("""
        INSERT INTO cleanup_actions (
            location, action, assigned_to,
            target_date, status, completed_at
        )
        VALUES (?, ?, ?, ?, 'Pending', NULL)
    """, (
        location, action, assigned_to, str(target_date)
    ))
    conn.commit()
    conn.close()


def update_cleanup_action(action_id, status):
    completed_at = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if status == "Completed" else None
    )

    conn = get_connection()
    conn.execute("""
        UPDATE cleanup_actions
        SET status=?, completed_at=?
        WHERE id=?
    """, (status, completed_at, int(action_id)))

    conn.commit()
    conn.close()


initialize_db()

st.title("♻️ CleanSpot")
st.caption(
    "Smart Illegal Garbage Dumping Hotspot Detection "
    "and Prevention System"
)

st.write(
    "Report garbage dumping, monitor complaints, "
    "and identify locations that need preventive action."
)

report_tab, admin_tab, hotspot_tab, map_tab, analytics_tab, prevention_tab = st.tabs([
    "📸 Report Garbage",
    "📊 Admin Dashboard",
    "📍 Hotspot Analysis",
    "🗺️ Hotspot Map",
    "📈 Environmental Analytics",
    "🧹 Prevention & Monitoring"
])


# REPORT GARBAGE
with report_tab:
    st.subheader("Report illegal garbage dumping")

    st.info(
        "CleanSpot needs your browser's location permission "
        "to capture live GPS. Allow access when prompted. "
        "Location access normally requires localhost or HTTPS."
    )

    latitude = None
    longitude = None

    try:
        from streamlit_geolocation import streamlit_geolocation

        gps = streamlit_geolocation()

        if isinstance(gps, dict):
            coords = gps.get("coords", gps)

            if isinstance(coords, dict):
                latitude = coords.get("latitude")
                longitude = coords.get("longitude")

        if latitude is not None and longitude is not None:
            latitude = float(latitude)
            longitude = float(longitude)

            if (
                -90 <= latitude <= 90 and
                -180 <= longitude <= 180
            ):
                st.success(
                    f"GPS captured: {latitude:.6f}, "
                    f"{longitude:.6f}"
                )
            else:
                latitude = longitude = None

        if latitude is None or longitude is None:
            st.warning(
                "GPS coordinates are not available yet. "
                "Allow location access in your browser and "
                "use the GPS component if it asks you to "
                "click a location button. You can still "
                "submit a report without GPS."
            )

    except ImportError:
        st.error(
            "GPS package not installed. Run this in the "
            "VS Code terminal: "
            "python -m pip install streamlit-geolocation"
        )

    except Exception as error:
        st.warning(f"Unable to retrieve GPS: {error}")

    with st.form("complaint_form"):
        location = st.text_input(
            "Location / landmark",
            placeholder="Example: Near the main gate, Jayanagar"
        )

        area_type = st.selectbox(
            "Area type",
            [
                "Residential area",
                "Roadside",
                "Near drain or water body",
                "Vacant plot",
                "Commercial area",
                "Other"
            ]
        )

        description = st.text_area(
            "Describe the garbage dumping"
        )

        uploaded_image = st.file_uploader(
            "Upload a photo (optional)",
            type=["jpg", "jpeg", "png"]
        )

        if latitude is not None and longitude is not None:
            st.caption(
                "Your captured GPS coordinates will be saved "
                "when you submit this complaint."
            )

        submitted = st.form_submit_button(
            "Submit Complaint",
            type="primary"
        )

    if submitted:
        if not location.strip():
            st.error("Please enter the location or landmark.")

        elif not description.strip():
            st.error("Please describe the garbage dumping.")

        else:
            image_path = save_uploaded_image(uploaded_image)

            complaint_id = save_complaint(
                location,
                area_type,
                description,
                image_path,
                latitude,
                longitude
            )

            st.success(
                f"Complaint submitted successfully! "
                f"Complaint ID: {complaint_id}"
            )

            if latitude is None or longitude is None:
                st.warning(
                    "The complaint was saved, but GPS coordinates "
                    "were unavailable. It will not appear as a "
                    "coordinate-based map pin."
                )

# ADMIN DASHBOARD
with admin_tab:
    st.subheader("Admin Dashboard")
    df = get_reports()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Reports", len(df))
    c2.metric(
        "Pending",
        int((df["status"] == "Pending").sum()) if not df.empty else 0
    )
    c3.metric(
        "In Progress",
        int((df["status"] == "In Progress").sum()) if not df.empty else 0
    )
    c4.metric(
        "Resolved",
        int((df["status"] == "Resolved").sum()) if not df.empty else 0
    )

    if df.empty:
        st.info("No complaints have been submitted yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        for _, row in df.iterrows():
            with st.expander(
                f"{row['id']} — {row['location']} — {row['status']}"
            ):
                st.write("**Area:**", row["area_type"])
                st.write("**Description:**", row["description"])
                st.write("**Reported at:**", row["created_at"])

                if pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
                    st.write(
                        f"**GPS:** {row['latitude']}, "
                        f"{row['longitude']}"
                    )

                image_path = row.get("image_path")
                if (
                    isinstance(image_path, str)
                    and image_path
                    and os.path.exists(image_path)
                ):
                    st.image(image_path, width=350)

                statuses = ["Pending", "In Progress", "Resolved"]
                current = (
                    row["status"]
                    if row["status"] in statuses
                    else "Pending"
                )

                new_status = st.selectbox(
                    "Complaint status",
                    statuses,
                    index=statuses.index(current),
                    key=f"status_{row['id']}"
                )

                if st.button(
                    "Save status",
                    key=f"save_{row['id']}"
                ):
                    update_complaint_status(row["id"], new_status)
                    st.success("Status updated.")
                    st.rerun()


# HOTSPOT ANALYSIS
with hotspot_tab:
    st.subheader("Repeated dumping hotspots")
    df = get_reports()
    hot = get_hotspots(df)

    st.caption(
        "A hotspot is a location with at least 3 reports "
        "within the last 30 days."
    )

    if hot.empty:
        st.info("No hotspots identified yet.")
    else:
        st.dataframe(hot, use_container_width=True, hide_index=True)
        st.bar_chart(hot.set_index("Location")["Reports"])

        st.markdown("#### Recommended prevention measures")
        for _, row in hot.iterrows():
            st.write(f"**{row['Location']}**")
            st.write(prevention_advice(row["Area"]))


# GPS MAP
with map_tab:
    st.subheader("Complaint locations on map")
    df = get_reports()

    if df.empty:
        st.info("No complaints to display yet.")
    else:
        map_data = df.dropna(
            subset=["latitude", "longitude"]
        ).copy()

        if map_data.empty:
            st.info(
                "No GPS coordinates have been saved yet. "
                "Allow location access when submitting a new report."
            )
        else:
            map_data["latitude"] = pd.to_numeric(
                map_data["latitude"], errors="coerce"
            )
            map_data["longitude"] = pd.to_numeric(
                map_data["longitude"], errors="coerce"
            )

            map_data = map_data.dropna(
                subset=["latitude", "longitude"]
            )

            map_data = map_data[
                map_data["latitude"].between(-90, 90) &
                map_data["longitude"].between(-180, 180)
            ]

            if map_data.empty:
                st.info("No valid GPS coordinates found.")
            else:
                st.map(
                    map_data.rename(
                        columns={
                            "latitude": "lat",
                            "longitude": "lon"
                        }
                    )[["lat", "lon"]]
                )

                st.dataframe(
                    map_data[
                        [
                            "id", "location", "area_type",
                            "latitude", "longitude", "status"
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True
                )


# ENVIRONMENTAL ANALYTICS
with analytics_tab:
    st.subheader("Environmental Analytics")
    df = get_reports()

    if df.empty:
        st.info("Analytics will appear after complaints are submitted.")
    else:
        df["created_at"] = pd.to_datetime(
            df["created_at"], errors="coerce"
        )
        hot = get_hotspots(df)
        resolved = int((df["status"] == "Resolved").sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Complaints", len(df))
        c2.metric("Resolved", resolved)
        c3.metric(
            "Resolution Rate",
            f"{resolved / len(df) * 100:.1f}%"
        )
        c4.metric("Hotspots", len(hot))

        st.markdown("#### Reports by location")
        st.bar_chart(
            df["location"].fillna("Unknown").value_counts().head(10)
        )

        st.markdown("#### Monthly complaint trend")
        monthly = (
            df.dropna(subset=["created_at"])
            .assign(
                Month=lambda x:
                x["created_at"].dt.to_period("M").astype(str)
            )
            .groupby("Month")
            .size()
            .rename("Reports")
        )

        if not monthly.empty:
            st.line_chart(monthly)

        st.markdown("#### Complaint status")
        st.bar_chart(df["status"].value_counts())

        st.markdown("#### Hotspot summary")
        if hot.empty:
            st.write("No current hotspots.")
        else:
            st.dataframe(hot, use_container_width=True, hide_index=True)


# PREVENTION AND MONITORING
with prevention_tab:
    st.subheader("Prevention & Monitoring")
    hot = get_hotspots(get_reports())

    if hot.empty:
        st.info("No repeated-dumping hotspots identified yet.")
    else:
        st.markdown("#### Prevention recommendations")
        for _, row in hot.iterrows():
            st.write(
                f"**{row['Location']}** — "
                f"{row['Reports']} reports in the last 30 days"
            )
            st.write(prevention_advice(row["Area"]))

    st.divider()
    st.markdown("#### Assign cleanup or prevention action")

    df = get_reports()
    known_locations = (
        sorted(df["location"].dropna().astype(str).unique().tolist())
        if not df.empty else []
    )
    options = ["Enter another location"] + known_locations

    with st.form("cleanup_action_form"):
        selected_location = st.selectbox("Location", options)

        custom_location = ""
        if selected_location == "Enter another location":
            custom_location = st.text_input("Enter location")

        action = st.text_input(
            "Action to take",
            placeholder="Arrange waste collection and install a warning sign"
        )
        assigned_to = st.text_input(
            "Assigned person / team",
            placeholder="Ward sanitation team"
        )
        target_date = st.date_input("Target completion date")

        save_action = st.form_submit_button(
            "Assign action",
            type="primary"
        )

    if save_action:
        final_location = (
            custom_location.strip()
            if selected_location == "Enter another location"
            else selected_location
        )

        if not final_location or not action.strip() or not assigned_to.strip():
            st.error("Enter the location, action, and assigned team.")
        else:
            save_cleanup_action(
                final_location,
                action.strip(),
                assigned_to.strip(),
                target_date
            )
            st.success("Cleanup action assigned.")
            st.rerun()

    st.divider()
    st.markdown("#### Cleanup action tracker")
    actions = get_cleanup_actions()

    if actions.empty:
        st.info("No cleanup actions assigned yet.")
    else:
        a, b, c = st.columns(3)
        a.metric(
            "Pending",
            int((actions["status"] == "Pending").sum())
        )
        b.metric(
            "In Progress",
            int((actions["status"] == "In Progress").sum())
        )
        c.metric(
            "Completed",
            int((actions["status"] == "Completed").sum())
        )

        st.dataframe(actions, use_container_width=True, hide_index=True)

        action_ids = actions["id"].astype(int).tolist()
        selected_id = st.selectbox(
            "Select action ID",
            action_ids,
            format_func=lambda action_id: (
                f"#{action_id} — "
                f"{actions.loc[actions['id'] == action_id, 'location'].iloc[0]}"
            )
        )

        current_status = actions.loc[
            actions["id"] == selected_id, "status"
        ].iloc[0]

        statuses = ["Pending", "In Progress", "Completed"]
        new_status = st.selectbox(
            "New action status",
            statuses,
            index=(
                statuses.index(current_status)
                if current_status in statuses else 0
            )
        )

        if st.button("Update cleanup action"):
            update_cleanup_action(selected_id, new_status)
            st.success("Cleanup action updated.")
            if new_status == "Completed":
                st.info(
                    "Completion time is recorded when an admin marks "
                    "the action Completed. The app does not independently "
                    "verify that cleanup took place."
                )
            st.rerun()


st.divider()
st.caption(
    "CleanSpot is a student project prototype. Verify reports before "
    "taking action. GPS accuracy may vary, especially indoors."
)
