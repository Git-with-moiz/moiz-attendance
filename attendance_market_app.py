import streamlit as st
import pandas as pd
import hashlib
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

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ---------------- LOGIN ----------------
def login_screen():
    st.title("⭐ Star Baby Diapers")
    st.caption("Please sign in to continue")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            if not username or not password:
                st.error("Enter both username and password.")
                return
            user = sb.table("users").select("*").eq("username", username.strip()).eq("active", True).execute().data
            if not user:
                st.error("Invalid username or password.")
                return
            user = user[0]
            if user["password_hash"] != hash_password(password):
                st.error("Invalid username or password.")
                return
            st.session_state["user"] = user
            st.rerun()

if "user" not in st.session_state:
    login_screen()
    st.stop()

user = st.session_state["user"]
is_admin = user["role"] == "super_admin"

# ---------------- SIDEBAR ----------------
st.sidebar.title("⭐ Star Baby Diapers")
st.sidebar.markdown(f"**{user['full_name']}**  \n*{user['role'].replace('_', ' ').title()}*")
st.sidebar.divider()

if is_admin:
    menu = ["Dashboard", "Mark Attendance", "Record Sales", "Today's Summary",
            "Sales Dashboard", "Monthly Report", "Manage Staff",
            "Manage Locations", "Manage Users"]
else:
    menu = ["My Dashboard", "My Attendance", "My Sales", "Leaderboard"]

page = st.sidebar.radio("Menu", menu)
st.sidebar.divider()
if st.sidebar.button("🚪 Log out", use_container_width=True):
    del st.session_state["user"]
    st.rerun()
st.sidebar.caption("Baby Diapers & Varieties")

# ---------------- SHARED HELPERS ----------------
def get_staff_sales_totals(staff_id, start_date, end_date):
    rows = sb.table("sales").select("amount").eq("staff_id", staff_id)\
        .gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute().data
    return sum(float(r["amount"]) for r in rows)

def get_month_leaderboard(year, month):
    start = f"{year}-{month:02d}-01"
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = f"{end_year}-{end_month:02d}-01"
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    sales = sb.table("sales").select("*").gte("date", start).lt("date", end).execute().data
    totals = {}
    for s in sales:
        totals[s["staff_id"]] = totals.get(s["staff_id"], 0) + float(s["amount"])
    rows = []
    for s in staff:
        rows.append({"staff_id": s["id"], "name": s["name"], "total": totals.get(s["id"], 0)})
    rows.sort(key=lambda r: r["total"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows

# ============================================================
# ADMIN PAGES
# ============================================================

if is_admin and page == "Dashboard":
    st.title("📊 Admin Dashboard")
    today = date.today()
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    locations = sb.table("locations").select("*").execute().data
    today_sales = sb.table("sales").select("amount").eq("date", today.isoformat()).execute().data
    today_att = sb.table("attendance").select("status").eq("date", today.isoformat()).execute().data
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Staff", len(staff))
    c2.metric("Locations", len(locations))
    c3.metric("Today's Sales", f"₹{sum(float(s['amount']) for s in today_sales):,.0f}")
    c4.metric("Present Today", sum(1 for a in today_att if a["status"] == "Present"))
    st.divider()
    st.subheader("🏆 This Month's Top 3")
    lb = get_month_leaderboard(today.year, today.month)[:3]
    for i, row in enumerate(lb):
        medal = ["🥇", "🥈", "🥉"][i]
        st.markdown(f"### {medal} {row['name']} — ₹{row['total']:,.0f}")

elif is_admin and page == "Mark Attendance":
    st.title("✅ Mark Attendance")
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
    st.subheader(f"{selected_loc_name} — {selected_date.strftime('%d %b %Y')}")
    existing_rows = sb.table("attendance").select("*").eq("date", selected_date.isoformat()).execute().data
    existing_map = {r["staff_id"]: (r["status"], r["notes"] or "") for r in existing_rows}
    status_options = ["Present", "Absent", "Half-day", "Leave", "Holiday"]
    updates = {}
    for s in staff_list:
        sid = s["id"]
        cur_s, cur_n = existing_map.get(sid, ("Present", ""))
        c1, c2, c3 = st.columns([3, 2, 3])
        c1.markdown(f"**{s['name']}**  \n*{s.get('role') or '—'}*")
        status = c2.selectbox("Status", status_options,
            index=status_options.index(cur_s) if cur_s in status_options else 0,
            key=f"st_{sid}", label_visibility="collapsed")
        notes = c3.text_input("Notes", value=cur_n, key=f"n_{sid}",
            label_visibility="collapsed", placeholder="Notes (optional)")
        updates[sid] = (status, notes)
    if st.button("💾 Save Attendance", type="primary", use_container_width=True):
        for sid, (s_, n_) in updates.items():
            sb.table("attendance").upsert({
                "staff_id": sid, "date": selected_date.isoformat(),
                "status": s_, "notes": n_
            }, on_conflict="staff_id,date").execute()
        st.success(f"Saved for {len(updates)} staff.")
        st.balloons()

elif is_admin and page == "Record Sales":
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
    existing = sb.table("sales").select("*").eq("date", selected_date.isoformat()).execute().data
    existing_map = {r["staff_id"]: (float(r["amount"]), r["notes"] or "") for r in existing}
    updates = {}
    total_preview = 0.0
    for s in staff_list:
        sid = s["id"]
        cur_a, cur_n = existing_map.get(sid, (0.0, ""))
        c1, c2, c3 = st.columns([3, 2, 3])
        c1.markdown(f"**{s['name']}**  \n*{s.get('role') or '—'}*")
        amount = c2.number_input("Amount (₹)", min_value=0.0, value=float(cur_a),
            step=100.0, key=f"amt_{sid}", label_visibility="collapsed")
        notes = c3.text_input("Notes", value=cur_n, key=f"sn_{sid}",
            label_visibility="collapsed", placeholder="Notes (optional)")
        updates[sid] = (amount, notes)
        total_preview += amount
    st.divider()
    st.metric("Total today", f"₹{total_preview:,.2f}")
    if st.button("💾 Save Sales", type="primary", use_container_width=True):
        for sid, (a, n) in updates.items():
            sb.table("sales").upsert({
                "staff_id": sid, "date": selected_date.isoformat(),
                "amount": a, "notes": n
            }, on_conflict="staff_id,date").execute()
        st.success(f"Saved. Total: ₹{total_preview:,.2f}")
        st.balloons()

elif is_admin and page == "Today's Summary":
    st.title("📊 Today's Summary")
    today = date.today().isoformat()
    st.caption(f"As of {date.today().strftime('%A, %d %B %Y')}")
    locations = {l["id"]: l["name"] for l in sb.table("locations").select("*").execute().data}
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    att = sb.table("attendance").select("*").eq("date", today).execute().data
    att_map = {a["staff_id"]: (a["status"], a["notes"] or "") for a in att}
    rows = []
    for s in staff:
        status, notes = att_map.get(s["id"], ("Not marked", ""))
        rows.append({
            "Location": locations.get(s["location_id"], "?"),
            "Staff": s["name"], "Role": s.get("role") or "—",
            "Status": status, "Notes": notes
        })
    if not rows:
        st.info("No staff yet.")
        st.stop()
    df = pd.DataFrame(rows).sort_values(["Location", "Staff"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(df))
    c2.metric("Present", (df["Status"] == "Present").sum())
    c3.metric("Absent", (df["Status"] == "Absent").sum())
    c4.metric("Not Marked", (df["Status"] == "Not marked").sum())
    st.divider()
    for loc in df["Location"].unique():
        with st.expander(f"📍 {loc}", expanded=True):
            st.dataframe(df[df["Location"] == loc].drop(columns=["Location"]), hide_index=True, use_container_width=True)

elif is_admin and page == "Sales Dashboard":
    st.title("📈 Sales Dashboard")
    period = st.radio("Period", ["Today", "This Week", "This Month", "Custom"], horizontal=True)
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
        start_date = col1.date_input("From", value=today.replace(day=1))
        end_date = col2.date_input("To", value=today)
    st.caption(f"{start_date.strftime('%d %b')} → {end_date.strftime('%d %b %Y')}")
    locations = {l["id"]: l["name"] for l in sb.table("locations").select("*").execute().data}
    staff = sb.table("staff").select("*").eq("active", True).execute().data
    sales = sb.table("sales").select("*").gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute().data
    if not sales:
        st.info("No sales in this period.")
        st.stop()
    staff_map = {s["id"]: s for s in staff}
    totals = {}
    for sale in sales:
        sid = sale["staff_id"]
        if sid in staff_map:
            totals[sid] = totals.get(sid, 0) + float(sale["amount"])
    rows = []
    for sid, total in totals.items():
        s = staff_map[sid]
        rows.append({"Staff": s["name"], "Location": locations.get(s["location_id"], "?"),
                     "Role": s.get("role") or "—", "Total Sales (₹)": total})
    df = pd.DataFrame(rows).sort_values("Total Sales (₹)", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    df = df[["Rank", "Staff", "Location", "Role", "Total Sales (₹)"]]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", f"₹{df['Total Sales (₹)'].sum():,.0f}")
    c2.metric("People", len(df))
    c3.metric("Average", f"₹{df['Total Sales (₹)'].mean():,.0f}")
    c4.metric("Top", f"₹{df['Total Sales (₹)'].max():,.0f}")
    st.divider()
    top = df.iloc[0]
    st.success(f"🏆 **Top Performer: {top['Staff']}** ({top['Location']}) — ₹{top['Total Sales (₹)']:,.2f}")
    if len(df) > 1:
        st.info(f"📉 Needs support: **{df.iloc[-1]['Staff']}** — ₹{df.iloc[-1]['Total Sales (₹)']:,.2f}")
    st.subheader("🏅 Leaderboard")
    st.dataframe(df, hide_index=True, use_container_width=True,
        column_config={"Total Sales (₹)": st.column_config.NumberColumn(format="₹%.2f")})
    st.subheader("📍 By Location")
    loc_totals = df.groupby("Location")["Total Sales (₹)"].sum().sort_values(ascending=False).reset_index()
    st.bar_chart(loc_totals.set_index("Location"))
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sales", index=False)
    st.download_button("⬇️ Download Excel", data=output.getvalue(),
        file_name=f"sales_{start_date}_{end_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif is_admin and page == "Monthly Report":
    st.title("📅 Monthly Report")
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", 2024, 2030, value=date.today().year)
    month = col2.selectbox("Month", range(1, 13), index=date.today().month - 1,
        format_func=lambda m: datetime(2000, m, 1).strftime("%B"))
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
            "Location": locations.get(s["location_id"], "?"), "Staff": s["name"],
            "Present": c["Present"], "Half-day": c["Half-day"], "Absent": c["Absent"],
            "Leave": c["Leave"], "Holiday": c["Holiday"],
            "Working Days": c["Present"] + 0.5 * c["Half-day"],
            "Sales (₹)": sales_totals.get(s["id"], 0),
        })
    df = pd.DataFrame(rows).sort_values(["Location", "Staff"]) if rows else pd.DataFrame()
    if df.empty:
        st.info("No data.")
    else:
        st.subheader(f"Summary — {datetime(year, month, 1).strftime('%B %Y')}")
        st.dataframe(df, hide_index=True, use_container_width=True)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=f"{year}-{month:02d}", index=False)
        st.download_button("⬇️ Download Excel", data=output.getvalue(),
            file_name=f"report_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif is_admin and page == "Manage Staff":
    st.title("👷 Manage Staff")
    locations = sb.table("locations").select("*").order("name").execute().data
    if not locations:
        st.warning("Add a location first.")
        st.stop()
    loc_map = {l["name"]: l["id"] for l in locations}
    loc_id_map = {l["id"]: l["name"] for l in locations}
    with st.expander("➕ Add New Staff"):
        with st.form("add_staff", clear_on_submit=True):
            name = st.text_input("Full Name")
            role = st.text_input("Role")
            phone = st.text_input("Phone")
            loc = st.selectbox("Location", list(loc_map.keys()))
            if st.form_submit_button("Add Staff", type="primary"):
                if name.strip():
                    sb.table("staff").insert({"name": name.strip(), "role": role.strip() or None,
                        "phone": phone.strip() or None, "location_id": loc_map[loc]}).execute()
                    st.success(f"Added {name}.")
                    st.rerun()
    st.subheader("Current Staff")
    all_staff = sb.table("staff").select("*").order("active", desc=True).order("name").execute().data
    for s in all_staff:
        col1, col2, col3 = st.columns([5, 2, 2])
        tag = "" if s["active"] else " *(inactive)*"
        col1.markdown(f"**{s['name']}**{tag}  \n{s.get('role') or '—'} · {loc_id_map.get(s['location_id'], '?')} · {s.get('phone') or 'no phone'}")
        if s["active"]:
            if col2.button("Deactivate", key=f"deact_{s['id']}"):
                sb.table("staff").update({"active": False}).eq("id", s["id"]).execute()
                st.rerun()
        else:
            if col2.button("Reactivate", key=f"react_{s['id']}"):
                sb.table("staff").update({"active": True}).eq("id", s["id"]).execute()
                st.rerun()
        if col3.button("🗑️", key=f"del_{s['id']}"):
            sb.table("staff").delete().eq("id", s["id"]).execute()
            st.rerun()

elif is_admin and page == "Manage Locations":
    st.title("📍 Manage Locations")
    with st.form("add_loc", clear_on_submit=True):
        new_loc = st.text_input("Location name")
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
    all_staff = sb.table("staff").select("*").eq("active", True).execute().data
    count_map = {}
    for s in all_staff:
        count_map[s["location_id"]] = count_map.get(s["location_id"], 0) + 1
    for l in locs:
        col1, col2 = st.columns([5, 1])
        col1.markdown(f"**{l['name']}** — {count_map.get(l['id'], 0)} staff")
        if col2.button("🗑️", key=f"dloc_{l['id']}"):
            sb.table("locations").delete().eq("id", l["id"]).execute()
            st.rerun()

elif is_admin and page == "Manage Users":
    st.title("🔑 Manage Users")
    st.caption("Super admins can see everything. Staff users see only their own stats.")
    staff_list = sb.table("staff").select("*").eq("active", True).order("name").execute().data
    staff_map = {s["name"]: s["id"] for s in staff_list}

    with st.expander("➕ Add New User"):
        with st.form("add_user", clear_on_submit=True):
            uname = st.text_input("Username (for login)")
            fname = st.text_input("Full Name")
            pw = st.text_input("Password", type="password")
            role_choice = st.selectbox("Role", ["staff", "super_admin"])
            link_staff = st.selectbox("Link to staff member (for staff role)",
                ["(none)"] + list(staff_map.keys()))
            if st.form_submit_button("Create User", type="primary"):
                if not uname or not pw:
                    st.error("Username and password are required.")
                else:
                    try:
                        sb.table("users").insert({
                            "username": uname.strip(),
                            "password_hash": hash_password(pw),
                            "full_name": fname.strip() or uname.strip(),
                            "role": role_choice,
                            "staff_id": staff_map.get(link_staff) if link_staff != "(none)" else None
                        }).execute()
                        st.success(f"Created user '{uname}'.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Couldn't create: {e}")

    st.subheader("Current Users")
    users = sb.table("users").select("*").order("role").order("username").execute().data
    for u in users:
        col1, col2, col3 = st.columns([5, 2, 2])
        tag = "" if u["active"] else " *(inactive)*"
        col1.markdown(f"**{u['username']}**{tag} — {u['full_name']}  \n*{u['role']}*")
        new_pw = col2.text_input("Reset pwd", key=f"pw_{u['id']}", type="password",
            placeholder="New password", label_visibility="collapsed")
        if col2.button("Reset", key=f"reset_{u['id']}"):
            if new_pw:
                sb.table("users").update({"password_hash": hash_password(new_pw)}).eq("id", u["id"]).execute()
                st.success(f"Password reset for {u['username']}.")
            else:
                st.error("Type a new password first.")
        if u["username"] != user["username"]:
            if col3.button("🗑️", key=f"du_{u['id']}"):
                sb.table("users").delete().eq("id", u["id"]).execute()
                st.rerun()

# ============================================================
# STAFF PAGES
# ============================================================

elif not is_admin and page == "My Dashboard":
    st.title(f"👋 Welcome, {user['full_name']}!")
    today = date.today()
    if not user.get("staff_id"):
        st.warning("Your account isn't linked to a staff record. Ask an admin to link it.")
        st.stop()
    sid = user["staff_id"]
    month_start = today.replace(day=1)
    my_sales = get_staff_sales_totals(sid, month_start, today)
    my_att = sb.table("attendance").select("*").eq("staff_id", sid)\
        .gte("date", month_start.isoformat()).lte("date", today.isoformat()).execute().data
    present = sum(1 for a in my_att if a["status"] == "Present")
    halfday = sum(1 for a in my_att if a["status"] == "Half-day")
    working_days = present + 0.5 * halfday
    lb = get_month_leaderboard(today.year, today.month)
    my_rank = next((r["rank"] for r in lb if r["staff_id"] == sid), None)
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 My Sales (this month)", f"₹{my_sales:,.0f}")
    c2.metric("📅 Working Days", f"{working_days}")
    c3.metric("🏆 My Rank", f"#{my_rank}" if my_rank else "—")
    st.divider()
    if my_rank == 1 and my_sales > 0:
        st.success("🥇 You're #1 this month! Keep it up!")
    elif my_rank and my_rank <= 3:
        st.info(f"🔥 Top 3! You're at #{my_rank} — push for #1!")
    elif my_rank:
        st.warning(f"You're #{my_rank}. Time to climb the leaderboard 💪")

elif not is_admin and page == "My Attendance":
    st.title("📅 My Attendance")
    if not user.get("staff_id"):
        st.warning("Account not linked to staff.")
        st.stop()
    sid = user["staff_id"]
    today = date.today()
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", 2024, 2030, value=today.year)
    month = col2.selectbox("Month", range(1, 13), index=today.month - 1,
        format_func=lambda m: datetime(2000, m, 1).strftime("%B"))
    start = f"{year}-{month:02d}-01"
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = f"{end_year}-{end_month:02d}-01"
    att = sb.table("attendance").select("*").eq("staff_id", sid)\
        .gte("date", start).lt("date", end).order("date").execute().data
    if not att:
        st.info("No attendance records for this month.")
    else:
        df = pd.DataFrame(att)[["date", "status", "notes"]]
        df["notes"] = df["notes"].fillna("")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Present", (df["status"] == "Present").sum())
        c2.metric("Half-day", (df["status"] == "Half-day").sum())
        c3.metric("Absent", (df["status"] == "Absent").sum())
        c4.metric("Leave", (df["status"] == "Leave").sum())
        st.dataframe(df, hide_index=True, use_container_width=True)

elif not is_admin and page == "My Sales":
    st.title("💰 My Sales")
    if not user.get("staff_id"):
        st.warning("Account not linked to staff.")
        st.stop()
    sid = user["staff_id"]
    today = date.today()
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", 2024, 2030, value=today.year)
    month = col2.selectbox("Month", range(1, 13), index=today.month - 1,
        format_func=lambda m: datetime(2000, m, 1).strftime("%B"))
    start = f"{year}-{month:02d}-01"
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = f"{end_year}-{end_month:02d}-01"
    sales = sb.table("sales").select("*").eq("staff_id", sid)\
        .gte("date", start).lt("date", end).order("date").execute().data
    if not sales:
        st.info("No sales recorded yet.")
    else:
        df = pd.DataFrame(sales)[["date", "amount", "notes"]]
        df["amount"] = df["amount"].astype(float)
        df["notes"] = df["notes"].fillna("")
        total = df["amount"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", f"₹{total:,.0f}")
        c2.metric("Days", len(df))
        c3.metric("Avg/Day", f"₹{df['amount'].mean():,.0f}")
        st.dataframe(df, hide_index=True, use_container_width=True,
            column_config={"amount": st.column_config.NumberColumn("Amount", format="₹%.2f")})
        st.bar_chart(df.set_index("date")["amount"])

elif not is_admin and page == "Leaderboard":
    st.title("🏆 Leaderboard")
    today = date.today()
    col1, col2 = st.columns(2)
    year = col1.number_input("Year", 2024, 2030, value=today.year)
    month = col2.selectbox("Month", range(1, 13), index=today.month - 1,
        format_func=lambda m: datetime(2000, m, 1).strftime("%B"))
    lb = get_month_leaderboard(year, month)
    if not lb:
        st.info("No sales data for this month yet.")
    else:
        st.subheader(f"{datetime(year, month, 1).strftime('%B %Y')}")
        df = pd.DataFrame(lb)[["rank", "name", "total"]]
        df.columns = ["Rank", "Staff", "Total Sales (₹)"]
        # Highlight current user
        my_sid = user.get("staff_id")
        def highlight_me(row):
            staff_row = lb[row.name]
            if staff_row["staff_id"] == my_sid:
                return ["background-color: #fff3bf"] * len(row)
            return [""] * len(row)
        st.dataframe(df.style.apply(highlight_me, axis=1),
            hide_index=True, use_container_width=True,
            column_config={"Total Sales (₹)": st.column_config.NumberColumn(format="₹%.2f")})
        if len(lb) > 0:
            st.success(f"🥇 Top performer: **{lb[0]['name']}** with ₹{lb[0]['total']:,.0f}")
