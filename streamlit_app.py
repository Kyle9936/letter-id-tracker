import streamlit as st
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
import io
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

st.set_page_config(
    page_title="Letter Identification Progress Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Letter Identification Progress Tracker")

# Hide Streamlit UI chrome but keep sidebar always visible
st.markdown(
    """<style>
    [data-testid="manage-app-button"] {display: none;}
    .stAppDeployButton {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    .reportview-container .main footer {display: none;}
    footer {display: none;}
    #MainMenu {display: none;}
    ._container_gzau3_1 {display: none;}
    ._link_gzau3_10 {display: none;}
    .viewerBadge_container__r5tak {display: none;}
    .viewerBadge_link__qRIco {display: none;}
    [data-testid="stMainMenu"] {display: none;}
    .stMainMenu {display: none;}
    .stBottom > div {display: none;}
    [data-testid="stBottom"] {display: none;}

    /* Force sidebar to always stay open */
    [data-testid="stSidebar"] {
        min-width: 310px !important;
        max-width: 310px !important;
        transform: none !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 310px !important;
    }
    /* Hide the collapse button so users can't collapse it */
    button[kind="headerNoPadding"] {
        display: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

conn = st.connection("gsheets", type=GSheetsConnection)

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()

df = conn.read(ttl="5m")

if df is None or df.empty:
    st.warning("No data found in the Google Sheet.")
    st.stop()

# Load saved letter toggle state from "Letter State" worksheet
try:
    letter_state_df = conn.read(worksheet="Letter State", ttl="5m")
    if letter_state_df is None or letter_state_df.empty:
        letter_state_df = pd.DataFrame(columns=["Student Name", "Uppercase", "Lowercase", "Sounds"])
except Exception:
    letter_state_df = pd.DataFrame(columns=["Student Name", "Uppercase", "Lowercase", "Sounds"])

def load_saved_toggle_state():
    """Build a dict of {student: {category: set_of_unknown_letters}} from the Letter State sheet."""
    saved = {}
    for _, row in letter_state_df.iterrows():
        name = row.get("Student Name", "")
        if not name or pd.isna(name):
            continue
        saved[name] = {}
        for cat in ["Uppercase", "Lowercase", "Sounds"]:
            val = row.get(cat, "")
            if pd.isna(val) or str(val).strip() == "":
                saved[name][cat] = set()
            else:
                saved[name][cat] = {l.strip().upper() for l in str(val).split(",")}
    return saved

saved_toggle_state = load_saved_toggle_state()

required_cols = ["Student Name", "Week", "Uppercase", "Lowercase", "Sound Total", "Letter Sound"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing columns: {', '.join(missing)}")
    st.stop()

df["Week"] = pd.to_datetime(df["Week"], format="mixed")
df = df.sort_values(["Student Name", "Week"])
df["Week Label"] = df["Week"].dt.strftime("%b %d, %Y")

df["Total Letter ID %"] = ((df["Uppercase"] + df["Lowercase"]) / 52 * 100).round(1)
df["Letter Sound %"] = (df["Letter Sound"] / 26 * 100).round(1)

students = sorted(df["Student Name"].unique().tolist())

with st.sidebar:
    st.header("Filters", divider=True)
    selected_students = st.multiselect("Students", students, default=students)
    metrics = st.pills(
        "Metrics",
        ["Total Letter ID %", "Letter Sound %"],
        selection_mode="multi",
        default=["Total Letter ID %", "Letter Sound %"],
    )

    st.divider()
    with st.expander("Add New Student"):
        new_student_name = st.text_input("Student Name", key="new_student_name")
        if st.button("Add Student"):
            if not new_student_name.strip():
                st.warning("Enter a student name.")
            elif new_student_name.strip() in students:
                st.warning("Student already exists.")
            else:
                from datetime import date
                new_row = pd.DataFrame([{
                    "Student Name": new_student_name.strip(),
                    "Week": date.today().strftime("%m/%d/%Y"),
                    "Uppercase": 0,
                    "Lowercase": 0,
                    "Sound Total": 0,
                    "Letter Sound": 0,
                }])
                main_data = conn.read(ttl="0m")
                updated = pd.concat([main_data, new_row], ignore_index=True)
                conn.update(data=updated)
                st.cache_data.clear()
                st.success(f"Added {new_student_name.strip()}!")
                st.rerun()

if not selected_students:
    st.warning("Select at least one student.")
    st.stop()

if not metrics:
    st.warning("Select at least one metric.")
    st.stop()

filtered = df[df["Student Name"].isin(selected_students)]

latest = filtered.loc[filtered.groupby("Student Name")["Week"].idxmax()]
most_recent_date = latest["Week"].max().strftime("%B %d, %Y")

def score_color(pct):
    if pct >= 80:
        return "green"
    elif pct >= 65:
        return "yellow"
    elif pct >= 40:
        return "orange"
    else:
        return "red"

COLOR_MAP = {"green": "#09AB3B", "yellow": "#FACA2B", "orange": "#FF8C00", "red": "#FF2B2B"}
COLOR_MAP_SOFT = {"green": "#66BB6A", "yellow": "#FFD54F", "orange": "#FFB74D", "red": "#EF9A9A"}

css_rules = []
for idx, (_, row) in enumerate(latest.iterrows()):
    tid = row['Total Letter ID %']
    ls = row['Letter Sound %']
    css_rules.append(f'.st-key-tid_{idx} [data-testid="stMetricValue"] {{ color: {COLOR_MAP[score_color(tid)]} !important; }}')
    css_rules.append(f'.st-key-ls_{idx} [data-testid="stMetricValue"] {{ color: {COLOR_MAP[score_color(ls)]} !important; }}')

st.markdown(f'<style>{" ".join(css_rules)}</style>', unsafe_allow_html=True)

def progress_bar_html(val):
    color = COLOR_MAP_SOFT[score_color(val)]
    return (
        f'<div style="background:#e0e0e0;border-radius:4px;width:100%;height:20px;position:relative;">'
        f'<div style="background:{color};width:{val}%;height:100%;border-radius:4px;"></div>'
        f'<span style="position:absolute;top:0;left:50%;transform:translateX(-50%);font-size:12px;line-height:20px;color:#333;font-weight:600;">{val:.1f}%</span>'
        f'</div>'
    )

LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

tab_scorecard, tab_individual, tab_cohort, tab_ranking, tab_letters, tab_pdf = st.tabs(
    ["Student Scorecard", "Individual Progress", "Cohort Progress", "Student Ranking", "Letter Detail", "Export PDF"]
)

with tab_scorecard:
    st.subheader("Student Scorecard")
    for idx, (_, row) in enumerate(latest.iterrows()):
        with st.container(border=True):
            student_date = row["Week"].strftime("%m/%d/%Y")
            st.markdown(f"**{row['Student Name']}** &nbsp;·&nbsp; Last assessed: {student_date}")
            cols = st.columns(5)
            cols[0].metric("Uppercase ID", f"{int(row['Uppercase'])}/26")
            cols[1].metric("Lowercase ID", f"{int(row['Lowercase'])}/26")
            tid = row['Total Letter ID %']
            with cols[2]:
                with st.container(key=f"tid_{idx}"):
                    st.metric("Total Letter ID", f"{tid:.0f}%")
            cols[3].metric("Sound Total", f"{int(row['Sound Total'])}/26")
            ls = row['Letter Sound %']
            with cols[4]:
                with st.container(key=f"ls_{idx}"):
                    st.metric("Letter Sound", f"{ls:.0f}%")

with tab_individual:
    for student in selected_students:
        student_df = filtered[filtered["Student Name"] == student].sort_values("Week")
        week_order = student_df["Week Label"].drop_duplicates().tolist()
        student_melted = student_df.melt(
            id_vars=["Student Name", "Week", "Week Label"],
            value_vars=[m for m in metrics],
            var_name="Metric",
            value_name="Score (%)",
        )
        student_melted["Label"] = student_melted["Score (%)"].round(0).astype(int).astype(str) + "%"

        metric_order = ["Total Letter ID %", "Letter Sound %"]

        with st.container(border=True):
            st.markdown(f"**{student}**")

            bars = (
                alt.Chart(student_melted)
                .mark_bar()
                .encode(
                    x=alt.X("Week Label:O", title="Week", sort=week_order, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Score (%):Q", title="Score (%)", scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color("Metric:N", sort=metric_order),
                    xOffset=alt.XOffset("Metric:N", sort=metric_order),
                    tooltip=["Week Label", "Metric", "Score (%)"],
                )
            )

            labels = (
                alt.Chart(student_melted)
                .mark_text(dy=-8, fontSize=11)
                .encode(
                    x=alt.X("Week Label:O", sort=week_order),
                    y=alt.Y("Score (%):Q"),
                    text="Label:N",
                    xOffset=alt.XOffset("Metric:N", sort=metric_order),
                )
            )

            chart = bars + labels
            st.altair_chart(chart, width="stretch")

            display_cols = ["Week", "Uppercase", "Lowercase", "Sound Total"] + [m for m in metrics]
            table_df = student_df[display_cols].sort_values("Week").reset_index(drop=True)
            table_df["Week"] = table_df["Week"].dt.strftime("%b %d, %Y")

            header_cols = ["Week", "Uppercase ID", "Lowercase ID"]
            if "Total Letter ID %" in metrics:
                header_cols.append("Total Letter ID %")
            header_cols.append("Sound Total")
            if "Letter Sound %" in metrics:
                header_cols.append("Letter Sound %")

            header_row = "".join(
                f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">{c}</th>'
                for c in header_cols
            )

            body_rows = ""
            for _, r in table_df.iterrows():
                cells = (
                    f'<td style="padding:6px 12px;font-size:13px;">{r["Week"]}</td>'
                    f'<td style="padding:6px 12px;font-size:13px;">{int(r["Uppercase"])}</td>'
                    f'<td style="padding:6px 12px;font-size:13px;">{int(r["Lowercase"])}</td>'
                )
                if "Total Letter ID %" in metrics:
                    cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Total Letter ID %"])}</td>'
                cells += f'<td style="padding:6px 12px;font-size:13px;">{int(r["Sound Total"])}</td>'
                if "Letter Sound %" in metrics:
                    cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Letter Sound %"])}</td>'
                body_rows += f"<tr>{cells}</tr>"

            html_table = (
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;">'
                f'<thead><tr>{header_row}</tr></thead>'
                f'<tbody>{body_rows}</tbody>'
                f'</table></div>'
            )
            st.markdown(html_table, unsafe_allow_html=True)

with tab_cohort:
    cohort_df = filtered.groupby(["Week", "Week Label"], as_index=False)[
        ["Sound Total", "Total Letter ID %", "Letter Sound %"]
    ].mean().round(1)
    cohort_df = cohort_df.sort_values("Week")
    cohort_week_order = cohort_df["Week Label"].drop_duplicates().tolist()

    cohort_melted = cohort_df.melt(
        id_vars=["Week", "Week Label"],
        value_vars=[m for m in metrics],
        var_name="Metric",
        value_name="Score (%)",
    )
    cohort_melted["Label"] = cohort_melted["Score (%)"].round(0).astype(int).astype(str) + "%"

    with st.container(border=True):
        st.markdown(f"**All selected students** ({len(selected_students)} students)")

        cohort_metric_order = ["Total Letter ID %", "Letter Sound %"]

        cohort_bars = (
            alt.Chart(cohort_melted)
            .mark_bar()
            .encode(
                x=alt.X("Week Label:O", title="Week", sort=cohort_week_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Score (%):Q", title="Avg Score (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Metric:N", sort=cohort_metric_order),
                xOffset=alt.XOffset("Metric:N", sort=cohort_metric_order),
                tooltip=["Week Label", "Metric", "Score (%)"],
            )
        )

        cohort_labels = (
            alt.Chart(cohort_melted)
            .mark_text(dy=-8, fontSize=11)
            .encode(
                x=alt.X("Week Label:O", sort=cohort_week_order),
                y=alt.Y("Score (%):Q"),
                text="Label:N",
                xOffset=alt.XOffset("Metric:N", sort=cohort_metric_order),
            )
        )

        cohort_chart = cohort_bars + cohort_labels
        st.altair_chart(cohort_chart, width="stretch")

        cohort_table_df = cohort_df.copy()
        cohort_table_df["Week"] = cohort_table_df["Week"].dt.strftime("%b %d, %Y")

        cohort_header_cols = ["Week"]
        if "Total Letter ID %" in metrics:
            cohort_header_cols.append("Total Letter ID %")
        cohort_header_cols.append("Avg Sound Total")
        if "Letter Sound %" in metrics:
            cohort_header_cols.append("Letter Sound %")

        cohort_header = "".join(
            f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">{c}</th>'
            for c in cohort_header_cols
        )

        cohort_body = ""
        for _, r in cohort_table_df.iterrows():
            cells = f'<td style="padding:6px 12px;font-size:13px;">{r["Week"]}</td>'
            if "Total Letter ID %" in metrics:
                cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Total Letter ID %"])}</td>'
            cells += f'<td style="padding:6px 12px;font-size:13px;">{r["Sound Total"]:.1f}</td>'
            if "Letter Sound %" in metrics:
                cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Letter Sound %"])}</td>'
            cohort_body += f"<tr>{cells}</tr>"

        cohort_html = (
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>{cohort_header}</tr></thead>'
            f'<tbody>{cohort_body}</tbody>'
            f'</table></div>'
        )
        st.markdown(cohort_html, unsafe_allow_html=True)

with tab_ranking:
    st.subheader(f"Student Ranking - {most_recent_date}")

    rank_cols = st.columns(2)

    with rank_cols[0]:
        st.markdown("**Total Letter ID %**")
        tid_ranked = latest[["Student Name", "Total Letter ID %"]].sort_values("Total Letter ID %", ascending=False).reset_index(drop=True)
        tid_ranked.index += 1
        tid_header = (
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Rank</th>'
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Student</th>'
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Total Letter ID %</th>'
        )
        tid_body = ""
        for rank, (_, r) in enumerate(tid_ranked.iterrows(), start=1):
            tid_body += (
                f'<tr>'
                f'<td style="padding:6px 12px;font-size:13px;font-weight:600;">{rank}</td>'
                f'<td style="padding:6px 12px;font-size:13px;">{r["Student Name"]}</td>'
                f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Total Letter ID %"])}</td>'
                f'</tr>'
            )
        tid_html = (
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>{tid_header}</tr></thead>'
            f'<tbody>{tid_body}</tbody>'
            f'</table></div>'
        )
        st.markdown(tid_html, unsafe_allow_html=True)

    with rank_cols[1]:
        st.markdown("**Letter Sound %**")
        ls_ranked = latest[["Student Name", "Letter Sound %"]].sort_values("Letter Sound %", ascending=False).reset_index(drop=True)
        ls_ranked.index += 1
        ls_header = (
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Rank</th>'
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Student</th>'
            '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">Letter Sound %</th>'
        )
        ls_body = ""
        for rank, (_, r) in enumerate(ls_ranked.iterrows(), start=1):
            ls_body += (
                f'<tr>'
                f'<td style="padding:6px 12px;font-size:13px;font-weight:600;">{rank}</td>'
                f'<td style="padding:6px 12px;font-size:13px;">{r["Student Name"]}</td>'
                f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r["Letter Sound %"])}</td>'
                f'</tr>'
            )
        ls_html = (
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>{ls_header}</tr></thead>'
            f'<tbody>{ls_body}</tbody>'
            f'</table></div>'
        )
        st.markdown(ls_html, unsafe_allow_html=True)

with tab_letters:
    st.subheader("Letter Detail")

    selected_student_detail = st.selectbox("Select a student", students, key="letter_detail_student")

    # Initialize session state for this student's toggles if not already set
    # "known" set = letters the student knows. New students default to empty (know nothing).
    state_key = f"toggles_{selected_student_detail}"
    if state_key not in st.session_state:
        saved = saved_toggle_state.get(selected_student_detail, None)
        # A student with a Letter State row but all-empty unknown sets has no real saved data yet
        has_saved_data = saved is not None and any(len(saved.get(c, set())) > 0 for c in ["Uppercase", "Lowercase", "Sounds"])
        if has_saved_data:
            # Saved state stores UNKNOWN letters; invert to get known
            st.session_state[state_key] = {
                "Uppercase": set(LETTERS) - saved.get("Uppercase", set()),
                "Lowercase": set(LETTERS) - saved.get("Lowercase", set()),
                "Sounds": set(LETTERS) - saved.get("Sounds", set()),
            }
        else:
            # Brand-new student or no real data: knows nothing
            st.session_state[state_key] = {
                "Uppercase": set(),
                "Lowercase": set(),
                "Sounds": set(),
            }

    def toggle_letter(student, category, letter):
        key = f"toggles_{student}"
        if letter in st.session_state[key][category]:
            st.session_state[key][category].remove(letter)
        else:
            st.session_state[key][category].add(letter)

    with st.container(border=True):
        st.markdown(f"**{selected_student_detail}**")
        st.caption("Click a letter to toggle between known (green) and unknown (red).")

        # Build CSS to color individual letter buttons green (known) or light red (unknown)
        toggle_css = []
        safe_name = selected_student_detail.replace(" ", "_")
        for cat_key in ["Uppercase", "Lowercase", "Sounds"]:
            known = st.session_state[state_key][cat_key]
            for letter in LETTERS:
                btn_key = f"btn_{safe_name}_{cat_key}_{letter}"
                if letter in known:
                    toggle_css.append(
                        f'.st-key-{btn_key} button '
                        f'{{ background-color: #09AB3B !important; color: white !important; border: none !important; }}'
                    )
                else:
                    toggle_css.append(
                        f'.st-key-{btn_key} button '
                        f'{{ background-color: #EF9A9A !important; color: white !important; border: none !important; }}'
                    )
        st.markdown(f'<style>{" ".join(toggle_css)}</style>', unsafe_allow_html=True)

        for cat_label, cat_key, show_lower in [
            ("Uppercase Letters", "Uppercase", False),
            ("Lowercase Letters", "Lowercase", True),
            ("Letter Sounds", "Sounds", False),
        ]:
            known = st.session_state[state_key][cat_key]
            count = len(known)
            st.markdown(f"**{cat_label} ({count}/26)**")

            # Render 26 buttons in rows of 13
            for row_start in range(0, 26, 13):
                cols = st.columns(13)
                for i, col in enumerate(cols):
                    idx = row_start + i
                    letter = LETTERS[idx]
                    display = letter.lower() if show_lower else letter
                    col.button(
                        display,
                        key=f"btn_{safe_name}_{cat_key}_{letter}",
                        on_click=toggle_letter,
                        args=(selected_student_detail, cat_key, letter),
                        use_container_width=True,
                    )

        # Auto-computed scores
        upper_count = len(st.session_state[state_key]["Uppercase"])
        lower_count = len(st.session_state[state_key]["Lowercase"])
        sound_count = len(st.session_state[state_key]["Sounds"])
        tid_pct = round((upper_count + lower_count) / 52 * 100, 1)
        ls_pct = round(sound_count / 26 * 100, 1)

        st.divider()
        st.markdown("**Auto-Computed Scores**")
        score_cols = st.columns(5)
        score_cols[0].metric("Uppercase ID", f"{upper_count}/26")
        score_cols[1].metric("Lowercase ID", f"{lower_count}/26")
        score_cols[2].metric("Total Letter ID", f"{tid_pct:.0f}%")
        score_cols[3].metric("Sound Total", f"{sound_count}/26")
        score_cols[4].metric("Letter Sound", f"{ls_pct:.0f}%")

        # Save Assessment button
        st.divider()
        if st.button("Save Assessment", type="primary", icon=":material/save:", key="save_assessment"):
            from datetime import date

            # Compute unknown letters (inverse of known) for storage
            unknown_upper = sorted(set(LETTERS) - st.session_state[state_key]["Uppercase"])
            unknown_lower = sorted(set(LETTERS) - st.session_state[state_key]["Lowercase"])
            unknown_sounds = sorted(set(LETTERS) - st.session_state[state_key]["Sounds"])

            # 1) Update Letter State worksheet
            existing_names = letter_state_df["Student Name"].tolist() if not letter_state_df.empty else []
            if selected_student_detail in existing_names:
                updated_state = letter_state_df.copy()
                mask = updated_state["Student Name"] == selected_student_detail
                updated_state.loc[mask, "Uppercase"] = ",".join(unknown_upper)
                updated_state.loc[mask, "Lowercase"] = ",".join(unknown_lower)
                updated_state.loc[mask, "Sounds"] = ",".join(unknown_sounds)
            else:
                new_row = pd.DataFrame([{
                    "Student Name": selected_student_detail,
                    "Uppercase": ",".join(unknown_upper),
                    "Lowercase": ",".join(unknown_lower),
                    "Sounds": ",".join(unknown_sounds),
                }])
                updated_state = pd.concat([letter_state_df, new_row], ignore_index=True)

            conn.update(worksheet="Letter State", data=updated_state)

            # 2) Append new assessment row to main data sheet
            today = date.today().strftime("%m/%d/%Y")
            new_assessment = pd.DataFrame([{
                "Student Name": selected_student_detail,
                "Week": today,
                "Uppercase": upper_count,
                "Lowercase": lower_count,
                "Sound Total": sound_count,
                "Letter Sound": sound_count,
            }])
            main_data = conn.read(ttl="0m")
            # Keep only the required columns that exist in the main sheet
            main_cols = main_data.columns.tolist()
            for col in new_assessment.columns:
                if col not in main_cols:
                    new_assessment = new_assessment.drop(columns=[col])
            updated_main = pd.concat([main_data, new_assessment], ignore_index=True)
            conn.update(data=updated_main)

            st.cache_data.clear()
            st.success(f"Assessment saved for {selected_student_detail} ({today}).")
            st.rerun()

with tab_pdf:
    st.subheader("Export PDF Report")

    pdf_scope = st.selectbox("Select student", ["All Students"] + students, key="pdf_student")

    def generate_pdf(student_rows, all_data):
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)

        for _, row in student_rows.iterrows():
            pdf.add_page()
            name = row["Student Name"]
            date = row["Week"].strftime("%B %d, %Y")

            # Header
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 10, name, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 6, f"Assessment Date: {date}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

            # Scores table
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "Scores", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "B", 10)
            col_w = 38
            headers = ["Uppercase", "Lowercase", "Letter ID %", "Sound Total", "Sound %"]
            for h in headers:
                pdf.cell(col_w, 7, h, border=1)
            pdf.ln()
            pdf.set_font("Helvetica", "", 10)
            values = [
                f"{int(row['Uppercase'])}/26",
                f"{int(row['Lowercase'])}/26",
                f"{row['Total Letter ID %']:.1f}%",
                f"{int(row['Sound Total'])}/26",
                f"{row['Letter Sound %']:.1f}%",
            ]
            for v in values:
                pdf.cell(col_w, 7, v, border=1)
            pdf.ln(12)

            # Progress bar chart
            student_history = all_data[all_data["Student Name"] == name].sort_values("Week")
            if len(student_history) > 1:
                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(0, 8, "Progress Over Time", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                week_labels = student_history["Week Label"].tolist()
                tid_vals = student_history["Total Letter ID %"].tolist()
                ls_vals = student_history["Letter Sound %"].tolist()

                fig, ax = plt.subplots(figsize=(7, 3))
                x = range(len(week_labels))
                bar_width = 0.35
                bars1 = ax.bar([i - bar_width / 2 for i in x], tid_vals, bar_width, label="Total Letter ID %", color="#5B9BD5")
                bars2 = ax.bar([i + bar_width / 2 for i in x], ls_vals, bar_width, label="Letter Sound %", color="#ED7D31")

                for bar in bars1:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=7)
                for bar in bars2:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=7)

                ax.set_xticks(list(x))
                ax.set_xticklabels(week_labels, fontsize=8)
                ax.set_ylim(0, 110)
                ax.set_ylabel("Score (%)", fontsize=9)
                ax.legend(fontsize=8, loc="upper left")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                fig.tight_layout()

                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=150)
                plt.close(fig)
                buf.seek(0)

                pdf.image(buf, x=pdf.l_margin, w=170)
                pdf.ln(4)

            # Letter detail grids from saved toggle state
            if name in saved_toggle_state:
                unknown = saved_toggle_state[name]
                known_upper = set(LETTERS) - unknown.get("Uppercase", set())
                known_lower = set(LETTERS) - unknown.get("Lowercase", set())
                known_sounds = set(LETTERS) - unknown.get("Sounds", set())

                for label, known, is_lower in [("Uppercase Letters", known_upper, False), ("Lowercase Letters", known_lower, True), ("Letter Sounds", known_sounds, False)]:
                    pdf.set_font("Helvetica", "B", 12)
                    pdf.cell(0, 8, f"{label} ({len(known)}/26)", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 10)

                    for i, letter in enumerate(LETTERS):
                        if letter in known:
                            pdf.set_fill_color(102, 187, 106)
                            pdf.set_text_color(255, 255, 255)
                        else:
                            pdf.set_fill_color(239, 154, 154)
                            pdf.set_text_color(255, 255, 255)
                        display = letter.lower() if is_lower else letter
                        pdf.cell(14, 14, display, border=0, fill=True, align="C")
                        if (i + 1) % 13 == 0:
                            pdf.ln()
                    pdf.set_text_color(0, 0, 0)
                    pdf.ln(6)

        return bytes(pdf.output())

    if pdf_scope == "All Students":
        pdf_data_rows = latest
    else:
        pdf_data_rows = latest[latest["Student Name"] == pdf_scope]

    if st.button("Generate PDF"):
        pdf_bytes = generate_pdf(pdf_data_rows, filtered)
        file_label = pdf_scope.replace(" ", "_") if pdf_scope != "All Students" else "All_Students"
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"Letter_ID_Report_{file_label}.pdf",
            mime="application/pdf",
        )
