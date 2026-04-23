import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime
from io import BytesIO

# ---------------- SETUP ----------------
st.set_page_config(page_title="Moiz Attendance Market", page_icon="👥", layout="wide")

DB_PATH = "attendance.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location_id INTEGER NOT NULL,
        role TEXT,
        phone TEXT,
        active INTEGER DEFAULT 1,
        FOREIGN KEY(location_id) REFERENCES locations(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        notes TEXT,
        UNIQUE(staff_id, date),
        FOREIGN KEY(staff_id) REFERENCES staff(id)
    )""")
    conn.commit()
    return conn

def run_query(query, params=(), fetch=False):
    conn = get_conn()
    cursor = conn.execute(query, params)
    result = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result

# ---------------- SIDEBAR NAV ----------------
st.sidebar.title("👥 Attendance Market App")
page = st.sidebar.radio("Menu", ["Mark Attendance", "Today's Summary", "Monthly Report", "Manage Staff", "Manage Locations"])
st.sidebar.divider()
st.sidebar.caption("Baby diapers & related items")

# ---------------- MARK ATTENDANCE ----------------
if page == "Mark Attendance":
    st.title("✅ Mark Attendance")
    
    locations = run_query("SELECT id, name FROM locations ORDER BY name", fetch=True)
    if not locations:
        st.warning("Add a location first (see 'Manage Locations' in the sidebar).")
        st.stop()
    
    col1, col2 = st.columns(2)
    with col1:
        loc_map = {name: id for id, name in locations}
        selected_loc_name = st.selectbox("Location", list(loc_map.keys()))
        loc_id = loc_map[selected_loc_name]
    with col2:
        selected_date = st.date_input("Date", value=date.today())
    
    staff_list = run_query(
        "SELECT id, name, role FROM staff WHERE location_id=? AND active=1 ORDER BY name",
        (loc_id,), fetch=True
    )
    
    if not staff_list:
        st.warning(f"No active staff at {selected_loc_name}. Add some in 'Manage Staff'.")
        st.stop()
    
    st.subheader(f"Staff at {selected_loc_name} — {selected_date.strftime('%d %b %Y')}")
    
    # Load existing attendance for this date
    existing = run_query(
        "SELECT staff_id, status, notes FROM attendance WHERE date=?",
        (selected_date.isoformat(),), fetch=True
    )
    existing_map = {sid: (status, notes or "") for sid, status, notes in existing}
    
    status_options = ["Present", "Absent", "Half-day", "Leave", "Holiday"]
    
    updates = {}
    for sid, name, role in staff_list:
        current_status, current_notes = existing_map.get(sid, ("Present", ""))
        c1, c2, c3 = st.columns([3, 2, 3])
        with c1:
            st.markdown(f"**{name}**  \n*{role or '—'}*")
        with c2:
            status = st.selectbox(
                "Status", status_options,
                index=status_options.index(current_status) if current_status in status_options else 0,
                key=f"status_{sid}", label_visibility="collapsed"
            )
        with c3:
            notes = st.text_input("Notes", value=current_notes, key=f"notes_{sid}", label_visibility="collapsed", placeholder="Notes (optional)")
        updates[sid] = (status, notes)
    
    if st.button("💾 Save Attendance", type="primary", use_container_width=True):
        for sid, (status, notes) in updates.items():
            run_query("""INSERT INTO attendance (staff_id, date, status, notes) VALUES (?, ?, ?, ?)
                         ON CONFLICT(staff_id, date) DO UPDATE SET status=excluded.status, notes=excluded.notes""",
                      (sid, selected_date.isoformat(), status, notes))
        st.success(f"Saved attendance for {len(updates)} staff members.")
        st.balloons()

# ---------------- TODAY'S SUMMARY ----------------
elif page == "Today's Summary":
    st.title("📊 Today's Summary")
    today = date.today().isoformat()
    st.caption(f"As of {date.today().strftime('%A, %d %B %Y')}")
    
    data = run_query("""
        SELECT l.name AS Location, s.name AS Staff, s.role AS Role,
               COALESCE(a.status, 'Not marked') AS Status, COALESCE(a.notes, '') AS Notes
        FROM staff s
        JOIN locations l ON s.location_id = l.id
        LEFT JOIN attendance a ON a.staff_id = s.id AND a.date = ?
        WHERE s.active = 1
        ORDER BY l.name, s.name
    """, (today,), fetch=True)
    
    if not data:
        st.info("No staff added yet.")
        st.stop()
    
    df = pd.DataFrame(data, columns=["Location", "Staff", "Role", "Status", "Notes"])
    
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Staff", len(df))
    col2.metric("Present", (df["Status"] == "Present").sum())
    col3.metric("Absent", (df["Status"] == "Absent").sum())
    col4.metric("Not Marked", (df["Status"] == "Not marked").sum())
    
    st.divider()
    for loc in df["Location"].unique():
        with st.expander(f"📍 {loc} ({(df['Location'] == loc).sum()} staff)", expanded=True):
            st.dataframe(df[df["Location"] == loc].drop(columns=["Location"]), hide_index=True, use_container_width=True)

# ---------------- MONTHLY REPORT ----------------
elif page == "Monthly Report":
    st.title("📅 Monthly Report")
    
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", min_value=2024, max_value=2030, value=date.today().year)
    with col2:
        month = st.selectbox("Month", range(1, 13), index=date.today().month - 1,
                              format_func=lambda m: datetime(2000, m, 1).strftime("%B"))
    
    month_str = f"{year}-{month:02d}"
    
    data = run_query("""
        SELECT l.name AS Location, s.name AS Staff,
               SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS Present,
               SUM(CASE WHEN a.status='Half-day' THEN 1 ELSE 0 END) AS HalfDay,
               SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS Absent,
               SUM(CASE WHEN a.status='Leave' THEN 1 ELSE 0 END) AS Leave_,
               SUM(CASE WHEN a.status='Holiday' THEN 1 ELSE 0 END) AS Holiday
        FROM staff s
        JOIN locations l ON s.location_id = l.id
        LEFT JOIN attendance a ON a.staff_id = s.id AND a.date LIKE ?
        WHERE s.active = 1
        GROUP BY s.id
        ORDER BY l.name, s.name
    """, (f"{month_str}-%",), fetch=True)
    
    if not data:
        st.info("No staff to report on.")
        st.stop()
    
    df = pd.DataFrame(data, columns=["Location", "Staff", "Present", "Half-day", "Absent", "Leave", "Holiday"])
    df["Working Days"] = df["Present"] + 0.5 * df["Half-day"]
    
    st.subheader(f"Summary — {datetime(year, month, 1).strftime('%B %Y')}")
    st.dataframe(df, hide_index=True, use_container_width=True)
    
    # Excel export
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=f"{month_str}", index=False)
    st.download_button("⬇️ Download as Excel", data=output.getvalue(),
                       file_name=f"attendance_{month_str}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------- MANAGE STAFF ----------------
elif page == "Manage Staff":
    st.title("👷 Manage Staff")
    
    locations = run_query("SELECT id, name FROM locations ORDER BY name", fetch=True)
    if not locations:
        st.warning("Add a location first.")
        st.stop()
    
    loc_map = {name: id for id, name in locations}
    
    with st.expander("➕ Add New Staff", expanded=False):
        with st.form("add_staff", clear_on_submit=True):
            name = st.text_input("Full Name")
            role = st.text_input("Role (e.g. Shop assistant, Loader, Manager)")
            phone = st.text_input("Phone (optional)")
            loc = st.selectbox("Location", list(loc_map.keys()))
            if st.form_submit_button("Add Staff", type="primary"):
                if name.strip():
                    run_query("INSERT INTO staff (name, role, phone, location_id) VALUES (?, ?, ?, ?)",
                              (name.strip(), role.strip(), phone.strip(), loc_map[loc]))
                    st.success(f"Added {name}.")
                    st.rerun()
                else:
                    st.error("Name is required.")
    
    st.subheader("Current Staff")
    all_staff = run_query("""
        SELECT s.id, s.name, s.role, s.phone, l.name, s.active
        FROM staff s JOIN locations l ON s.location_id = l.id
        ORDER BY s.active DESC, l.name, s.name
    """, fetch=True)
    
    if not all_staff:
        st.info("No staff yet. Add someone above.")
    else:
        for sid, sname, srole, sphone, lname, active in all_staff:
            col1, col2, col3 = st.columns([5, 2, 2])
            status_tag = "" if active else " *(inactive)*"
            col1.markdown(f"**{sname}**{status_tag}  \n{srole or '—'} · {lname} · {sphone or 'no phone'}")
            if active:
                if col2.button("Deactivate", key=f"deact_{sid}"):
                    run_query("UPDATE staff SET active=0 WHERE id=?", (sid,))
                    st.rerun()
            else:
                if col2.button("Reactivate", key=f"react_{sid}"):
                    run_query("UPDATE staff SET active=1 WHERE id=?", (sid,))
                    st.rerun()
            if col3.button("🗑️ Delete", key=f"del_{sid}"):
                run_query("DELETE FROM attendance WHERE staff_id=?", (sid,))
                run_query("DELETE FROM staff WHERE id=?", (sid,))
                st.rerun()

# ---------------- MANAGE LOCATIONS ----------------
elif page == "Manage Locations":
    st.title("📍 Manage Locations")
    
    with st.form("add_loc", clear_on_submit=True):
        new_loc = st.text_input("Location name (e.g. Main Shop, Godown 1, Branch – Karol Bagh)")
        if st.form_submit_button("Add Location", type="primary"):
            if new_loc.strip():
                try:
                    run_query("INSERT INTO locations (name) VALUES (?)", (new_loc.strip(),))
                    st.success(f"Added {new_loc}.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That location already exists.")
    
    st.subheader("Current Locations")
    locs = run_query("""
        SELECT l.id, l.name, COUNT(s.id) FROM locations l
        LEFT JOIN staff s ON s.location_id = l.id AND s.active = 1
        GROUP BY l.id ORDER BY l.name
    """, fetch=True)
    
    if not locs:
        st.info("No locations yet. Add one above.")
    else:
        for lid, lname, count in locs:
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{lname}** — {count} active staff")
            if col2.button("🗑️", key=f"dloc_{lid}"):
                run_query("DELETE FROM attendance WHERE staff_id IN (SELECT id FROM staff WHERE location_id=?)", (lid,))
                run_query("DELETE FROM staff WHERE location_id=?", (lid,))
                run_query("DELETE FROM locations WHERE id=?", (lid,))
                st.rerun()