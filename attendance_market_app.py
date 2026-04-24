import streamlit as st
import pandas as pd
from datetime import date, datetime
from io import BytesIO
from supabase import create_client, Client

# ---------------- SETUP ----------------
st.set_page_config(page_title="Star Baby Diapers", page_icon="⭐", layout="wide")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

sb = init_supabase()

# ---------------- SIDEBAR NAV ----------------
st.sidebar.title("⭐ Star Baby Diapers")
page = st.sidebar.radio("Menu", [
    "Mark Attendance",
    "Record Sales",
    "Today's Summary",
    "Sales Dashboard",
    "Monthly Report",
    "Manage Staff",
    "Manage Locations"
])
st.sidebar.divider()
st.sidebar.caption("Baby Diapers & Varieties")
# ---------------- MARK ATTENDANCE ----------------
if page == "Mark Attendance":
    st.title("✅ Mark Attendance")
    locations = sb.table("locations").select("*").order("name").execute().data
    if not locations:
        st.warning("Add a location first (see 'Manage Locations' in the sidebar).")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        loc_map = {l["name"]: l["id"] for l in locations}
        selected_loc_name = st.selectbox("Location", list(loc_map.keys()))
        loc_id = loc_map[selected_loc_name]
    with col2:
        selected_date = st.date_input("Date", value=date.today())

    staff_list = sb.table("staff").select("*").eq("location_id", loc_id).eq("active", True).order("name").execute().data
    if not staff_list:
        st.warning(f"No active staff at {selected_loc_name}. Add some in 'Manage Staff'.")
        st.stop()

    st.subheader(f"Staff at {selected_loc_name} — {selected_date.strftime('%d %b %Y')}")

    existing_rows = sb.table("attendance").select("*").eq("date", selected_date.isoformat()).execute().data
    existing_map = {r["staff_id"]: (r["status"], r["notes"] or "") for r in existing_rows}

    status_options = ["Present", "Absent", "Half-day", "Leave", "Holiday"]
    updates = {}

    for s in staff_list:
        sid = s["id"]
        current_status, current_notes = existing_map.get(sid, ("Present", ""))
        c1, c2, c3 = st.columns([3, 2, 3])
        with c1:
            st.markdown(f"**{s['name']}**  \n*{s.get('role') or '—'}*")
        with c2:
            status = st.selectbox(
                "Status", status_options,
                index=status_options.index(current_status) if current_status in status_options else 0,
                key=f"status_{sid}", label_visibility="collapsed"
            )
        with c3:
            notes = st.text_input(
                "Notes", value=current_notes, key=f"notes_{sid}",
                label_visibility="collapsed", placeholder="Notes (optional)"
            )
        updates[sid] = (status, notes)

    if st.button("💾 Save Attendance", type="primary", use_container_width=True):
        for sid, (status, notes) in updates.items():
            sb.table("attendance").upsert({
                "staff_id": sid,
                "date": selected_date.isoformat(),
                "status": status,
                "notes": notes
            }, on_conflict="staff_id,date").execute()
        st.success(f"Saved attendance for {len(updates)} staff members.")
        st.balloons()

# ---------------- RECORD SALES ----------------
elif page == "Record Sales":
    st.title("💰 Record Daily Sales")
    locations = sb.table("locations").select("*").order("name").execute().data
    if not locations:
        st.warning("Add a location first.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        loc_map = {l["name"]: l["id"] for l in locations}
        selected_loc_name = st.selectbox("Location", list(loc_map.keys()))
        loc_id = loc_map[selected_loc_name]
    with col2:
        selected_date = st.date_input("Date", value=date.today())

    staff_list = sb.table("staff").select("*").eq("location_id", loc_id).eq("active", True).order("name").execute().data
    if not staff_list:
        st.warning(f"No active staff at {selected_loc_name}.")
        st.stop()

    st.subheader(f"Sales at {selected_loc_name} — {selected_date.strftime('%d %b %Y')}")

    existing_rows = sb.table("sales").select("*").eq("date", selected_date.isoformat()).execute().data
    existing_map = {r["staff_id"]: (float(r["amount"]), r["notes"] or "") for r in existing_rows}

    updates = {}
    total_preview = 0.0

    for s in staff_list:
        sid = s["id"]
        current_amount, current_notes = existing_map.get(sid, (0.0, ""))
        c1, c2, c3 = st.columns([3, 2, 3])
        with c1:
            st.markdown(f"**{s['name']}**  \n*{s.get('role') or '—'}*")
        with c2:
            amount = st.number_input(
                "Amount (₹)", min_value=0.0, value=float(current_amount),
                step=100.0, key=f"amt_{sid}", label_visibility="collapsed"
            )
        with c3:
            notes = st.text_input(
                "Notes", value=current_notes, key=f"snotes_{sid}",
                label_visibility="collapsed", placeholder="Notes (optional)"
            )
        updates[sid] = (amount, notes)
        total_preview += amount

    st.divider()
    st.metric("Total sales for this day", f"₹{total_preview:,.2f}")

    if st.button("💾 Save Sales", type="primary", use_container_width=True):
        for sid, (amount, notes) in updates.items():
            sb.table("sales").upsert({
                "staff_id": sid,
                "date": selected_date.isoformat(),
                "amount": amount,
                "notes": notes
            }, on_conflict="staff_id,date").execute()
        st.success(f"Saved sales for {len(updates)} staff members. Total: ₹{total_preview:,.2f}")
        st.balloons()

# ---------------- TODAY'S SUMMARY ----------------
elif page == "Today's Summary":
    st.title("📊 Today's Summary")
    today = date.today().isoformat()
    st.caption(f"As of {date.today().strftime('%A, %d %B %Y')}")

    locations = {l["id"]: l["name"] for l in sb.table("locations").select("*").execute().data}
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    att = sb.table("attendance").select("*").eq("date", today).execute().data
    att_map = {a["staff_id"]: (a["status"], a["notes"] or "") for a in att}

    if not staff:
        st.info("No staff added yet.")
        st.stop()

    rows = []
    for s in staff:
        status, notes = att_map.get(s["id"], ("Not marked", ""))
        rows.append({
            "Location": locations.get(s["location_id"], "?"),
            "Staff": s["name"],
            "Role": s.get("role") or "—",
            "Status": status,
            "Notes": notes
        })
    df = pd.DataFrame(rows).sort_values(["Location", "Staff"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Staff", len(df))
    col2.metric("Present", (df["Status"] == "Present").sum())
    col3.metric("Absent", (df["Status"] == "Absent").sum())
    col4.metric("Not Marked", (df["Status"] == "Not marked").sum())

    st.divider()
    for loc in df["Location"].unique():
        with st.expander(f"📍 {loc} ({(df['Location'] == loc).sum()} staff)", expanded=True):
            st.dataframe(df[df["Location"] == loc].drop(columns=["Location"]), hide_index=True, use_container_width=True)

# ---------------- SALES DASHBOARD ----------------
elif page == "Sales Dashboard":
    st.title("📈 Sales Dashboard")

    period = st.radio("Period", ["Today", "This Week", "This Month", "Custom range"], horizontal=True)

    today = date.today()
    if period == "Today":
        start_date = end_date = today
    elif period == "This Week":
        start_date = today.replace(day=max(1, today.day - today.weekday()))
        end_date = today
    elif period == "This Month":
        start_date = today.replace(day=1)
        end_date = today
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From", value=today.replace(day=1))
        with col2:
            end_date = st.date_input("To", value=today)

    st.caption(f"Showing {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")

    locations = {l["id"]: l["name"] for l in sb.table("locations").select("*").execute().data}
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    sales = sb.table("sales").select("*").gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute().data

    if not sales:
        st.info("No sales recorded in this period yet. Go to Record Sales to add some.")
        st.stop()

    staff_map = {s["id"]: s for s in staff}
    totals = {}
    for sale in sales:
        sid = sale["staff_id"]
        if sid not in staff_map:
            continue
        totals[sid] = totals.get(sid, 0) + float(sale["amount"])

    rows = []
    for sid, total in totals.items():
        s = staff_map[sid]
        rows.append({
            "Staff": s["name"],
            "Location": locations.get(s["location_id"], "?"),
            "Role": s.get("role") or "—",
            "Total Sales (₹)": total,
        })
    df = pd.DataFrame(rows).sort_values("Total Sales (₹)", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    df = df[["Rank", "Staff", "Location", "Role", "Total Sales (₹)"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"₹{df['Total Sales (₹)'].sum():,.0f}")
    c2.metric("Active Salespeople", len(df))
    c3.metric("Average / Person", f"₹{df['Total Sales (₹)'].mean():,.0f}")
    c4.metric("Top Earner", f"₹{df['Total Sales (₹)'].max():,.0f}")

    st.divider()

    if len(df) > 0:
        top = df.iloc[0]
        st.success(f"🏆 **Top Performer: {top['Staff']}** from *{top['Location']}* — ₹{top['Total Sales (₹)']:,.2f}")
        if len(df) > 1:
            bottom = df.iloc[-1]
            st.info(f"📉 Needs support: **{bottom['Staff']}** from *{bottom['Location']}* — ₹{bottom['Total Sales (₹)']:,.2f}")

    st.subheader("🏅 Leaderboard")
    st.dataframe(
        df, hide_index=True, use_container_width=True,
        column_config={"Total Sales (₹)": st.column_config.NumberColumn(format="₹%.2f")}
    )

    st.subheader("📍 Sales by Location")
    loc_totals = df.groupby("Location")["Total Sales (₹)"].sum().sort_values(ascending=False).reset_index()
    st.bar_chart(loc_totals.set_index("Location"))

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sales", index=False)
    st.download_button(
        "⬇️ Download as Excel",
        data=output.getvalue(),
        file_name=f"sales_{start_date}_{end_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---------------- MONTHLY REPORT ----------------
elif page == "Monthly Report":
    st.title("📅 Monthly Report")
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", min_value=2024, max_value=2030, value=date.today().year)
    with col2:
        month = st.selectbox(
            "Month", range(1, 13),
            index=date.today().month - 1,
            format_func=lambda m: datetime(2000, m, 1).strftime("%B")
        )

    start = f"{year}-{month:02d}-01"
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = f"{end_year}-{end_month:02d}-01"

    locations = {l["id"]: l["name"] for l in sb.table("locations").select("*").execute().data}
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    att = sb.table("attendance").select("*").gte("date", start).lt("date", end).execute().data
    sales_rows = sb.table("sales").select("*").gte("date", start).lt("date", end).execute().data

    sales_totals = {}
    for sr in sales_rows:
        sales_totals[sr["staff_id"]] = sales_totals.get(sr["staff_id"], 0) + float(sr["amount"])

    counts = {}
    for a in att:
        counts.setdefault(a["staff_id"], {"Present": 0, "Half-day": 0, "Absent": 0, "Leave": 0, "Holiday": 0})
        if a["status"] in counts[a["staff_id"]]:
            counts[a["staff_id"]][a["status"]] += 1

    rows = []
    for s in staff:
        c = counts.get(s["id"], {"Present": 0, "Half-day": 0, "Absent": 0, "Leave": 0, "Holiday": 0})
        rows.append({
            "Location": locations.get(s["location_id"], "?"),
            "Staff": s["name"],
            "Present": c["Present"],
            "Half-day": c["Half-day"],
            "Absent": c["Absent"],
            "Leave": c["Leave"],
            "Holiday": c["Holiday"],
            "Working Days": c["Present"] + 0.5 * c["Half-day"],
            "Sales (₹)": sales_totals.get(s["id"], 0),
        })

    df = pd.DataFrame(rows).sort_values(["Location", "Staff"]) if rows else pd.DataFrame()

    if df.empty:
        st.info("No staff to report on.")
    else:
        st.subheader(f"Summary — {datetime(year, month, 1).strftime('%B %Y')}")
        st.dataframe(df, hide_index=True, use_container_width=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=f"{year}-{month:02d}", index=False)
        st.download_button(
            "⬇️ Download as Excel",
            data=output.getvalue(),
            file_name=f"attendance_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---------------- MANAGE STAFF ----------------
elif page == "Manage Staff":
    st.title("👷 Manage Staff")
    locations = sb.table("locations").select("*").order("name").execute().data
    if not locations:
        st.warning("Add a location first.")
        st.stop()
    loc_map = {l["name"]: l["id"] for l in locations}
    loc_id_map = {l["id"]: l["name"] for l in locations}

    with st.expander("➕ Add New Staff", expanded=False):
        with st.form("add_staff", clear_on_submit=True):
            name = st.text_input("Full Name")
            role = st.text_input("Role (e.g. Shop assistant, Loader, Manager)")
            phone = st.text_input("Phone (optional)")
            loc = st.selectbox("Location", list(loc_map.keys()))
            if st.form_submit_button("Add Staff", type="primary"):
                if name.strip():
                    sb.table("staff").insert({
                        "name": name.strip(),
                        "role": role.strip() or None,
                        "phone": phone.strip() or None,
                        "location_id": loc_map[loc]
                    }).execute()
                    st.success(f"Added {name}.")
                    st.rerun()
                else:
                    st.error("Name is required.")

    st.subheader("Current Staff")
    all_staff = sb.table("staff").select("*").order("active", desc=True).order("name").execute().data
    if not all_staff:
        st.info("No staff yet.")
    else:
        for s in all_staff:
            col1, col2, col3 = st.columns([5, 2, 2])
            status_tag = "" if s["active"] else " *(inactive)*"
            col1.markdown(
                f"**{s['name']}**{status_tag}  \n"
                f"{s.get('role') or '—'} · {loc_id_map.get(s['location_id'], '?')} · {s.get('phone') or 'no phone'}"
            )
            if s["active"]:
                if col2.button("Deactivate", key=f"deact_{s['id']}"):
                    sb.table("staff").update({"active": False}).eq("id", s["id"]).execute()
                    st.rerun()
            else:
                if col2.button("Reactivate", key=f"react_{s['id']}"):
                    sb.table("staff").update({"active": True}).eq("id", s["id"]).execute()
                    st.rerun()
            if col3.button("🗑️ Delete", key=f"del_{s['id']}"):
                sb.table("staff").delete().eq("id", s["id"]).execute()
                st.rerun()

# ---------------- MANAGE LOCATIONS ----------------
elif page == "Manage Locations":
    st.title("📍 Manage Locations")
    with st.form("add_loc", clear_on_submit=True):
        new_loc = st.text_input("Location name (e.g. Main Shop, Godown 1, Branch – Chandni Chowk)")
        if st.form_submit_button("Add Location", type="primary"):
            if new_loc.strip():
                try:
                    sb.table("locations").insert({"name": new_loc.strip()}).execute()
                    st.success(f"Added {new_loc}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't add: {e}")

    st.subheader("Current Locations")
    locs = sb.table("locations").select("*").order("name").execute().data
    if not locs:
        st.info("No locations yet.")
    else:
        all_staff = sb.table("staff").select("*").eq("active", True).execute().data
        count_map = {}
        for s in all_staff:
            count_map[s["location_id"]] = count_map.get(s["location_id"], 0) + 1
        for l in locs:
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{l['name']}** — {count_map.get(l['id'], 0)} active staff")
            if col2.button("🗑️", key=f"dloc_{l['id']}"):
                sb.table("locations").delete().eq("id", l["id"]).execute()
                st.rerun()
