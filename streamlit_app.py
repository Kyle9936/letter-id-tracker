import streamlit as st
import pandas as pd
import altair as alt
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Letter Identification Progress Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Letter Identification Progress Tracker")

st.markdown(
    """<style>
    [data-testid="manage-app-button"] {display: none;}
    .stAppDeployButton {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    .reportview-container .main footer {display: none;}
    footer {display: none;}
    #MainMenu {display: none;}
    header [data-testid="stToolbar"] {display: none;}
    ._container_gzau3_1 {display: none;}
    ._link_gzau3_10 {display: none;}
    .viewerBadge_container__r5tak {display: none;}
    .viewerBadge_link__qRIco {display: none;}
    [data-testid="stMainMenu"] {display: none;}
    [data-testid="baseButton-header"] {display: none;}
    .stMainMenu {display: none;}
    header {visibility: hidden;}
    .stBottom > div {display: none;}
    [data-testid="stBottom"] {display: none;}
    </style>""",
    unsafe_allow_html=True,
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1Fegdy8X2EqHGSOyvOTeU_TM4sRYSp1vECd8BTzNwKkw/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

if st.button("Refresh data", icon=":material/refresh:"):
    st.cache_data.clear()

df = conn.read(spreadsheet=SHEET_URL, ttl="5m")

if df is None or df.empty:
    st.warning("No data found in the Google Sheet.")
    st.stop()

required_cols = ["Student Name", "Week", "Uppercase", "Lowercase", "Sound Total", "Letter Sound"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing columns: {', '.join(missing)}")
    st.stop()

df["Week"] = pd.to_datetime(df["Week"])
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
    gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.secrets.get("gemini_api_key", "")

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

def parse_known_letters(val):
    if pd.isna(val) or str(val).strip() == "":
        return set()
    return {l.strip().upper() for l in str(val).split(",")}

def letter_grid_html(title, known_set, lowercase=False):
    cells = ""
    for letter in LETTERS:
        if letter in known_set:
            bg = "#66BB6A"
            color = "#fff"
        else:
            bg = "#EF9A9A"
            color = "#fff"
        display = letter.lower() if lowercase else letter
        cells += (
            f'<div style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:36px;height:36px;margin:2px;border-radius:4px;'
            f'background:{bg};color:{color};font-weight:600;font-size:14px;">'
            f'{display}</div>'
        )
    count = len(known_set)
    return (
        f'<div style="margin-bottom:12px;">'
        f'<div style="font-weight:600;font-size:14px;margin-bottom:4px;">{title} ({count}/26)</div>'
        f'<div style="max-width:480px;">{cells}</div>'
        f'</div>'
    )

HAS_LETTER_DETAIL = all(c in df.columns for c in ["Known Uppercase", "Known Lowercase", "Known Sounds"])

tab_scorecard, tab_individual, tab_cohort, tab_ranking, tab_letters, tab_pdf, tab_chat = st.tabs(
    ["Student Scorecard", "Individual Progress", "Cohort Progress", "Student Ranking", "Letter Detail", "Export PDF", "Ask Your Data"]
)

with tab_scorecard:
    st.subheader(f"Student Scorecard - {most_recent_date}")
    for idx, (_, row) in enumerate(latest.iterrows()):
        with st.container(border=True):
            st.markdown(f"**{row['Student Name']}**")
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
        student_df = filtered[filtered["Student Name"] == student]
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
                    x=alt.X("Week Label:O", title="Week", sort=alt.SortField("Week"), axis=alt.Axis(labelAngle=0)),
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
                    x=alt.X("Week Label:O", sort=alt.SortField("Week")),
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
                x=alt.X("Week Label:O", title="Week", sort=alt.SortField("Week"), axis=alt.Axis(labelAngle=0)),
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
                x=alt.X("Week Label:O", sort=alt.SortField("Week")),
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
    st.subheader(f"Letter Detail - {most_recent_date}")

    if not HAS_LETTER_DETAIL:
        st.info(
            "Add columns 'Known Uppercase', 'Known Lowercase', and 'Known Sounds' to your Google Sheet "
            "with comma-separated letters (e.g., A,B,C,D,E) to enable this view."
        )
    else:
        selected_student_detail = st.selectbox("Select a student", students, key="letter_detail_student")
        student_latest = latest[latest["Student Name"] == selected_student_detail]

        if student_latest.empty:
            st.warning("No data for this student.")
        else:
            row = student_latest.iloc[0]
            known_upper = parse_known_letters(row.get("Known Uppercase", ""))
            known_lower = parse_known_letters(row.get("Known Lowercase", ""))
            known_sounds = parse_known_letters(row.get("Known Sounds", ""))

            with st.container(border=True):
                st.markdown(f"**{selected_student_detail}**")
                st.markdown(
                    letter_grid_html("Uppercase Letters", known_upper)
                    + letter_grid_html("Lowercase Letters", known_lower, lowercase=True)
                    + letter_grid_html("Letter Sounds", known_sounds),
                    unsafe_allow_html=True,
                )

with tab_pdf:
    st.subheader("Export PDF Report")

    pdf_scope = st.selectbox("Select student", ["All Students"] + students, key="pdf_student")

    def generate_pdf(student_rows):
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

            # Letter detail grids (if available)
            if HAS_LETTER_DETAIL:
                known_upper = parse_known_letters(row.get("Known Uppercase", ""))
                known_lower = parse_known_letters(row.get("Known Lowercase", ""))
                known_sounds = parse_known_letters(row.get("Known Sounds", ""))

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
        pdf_bytes = generate_pdf(pdf_data_rows)
        file_label = pdf_scope.replace(" ", "_") if pdf_scope != "All Students" else "All_Students"
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"Letter_ID_Report_{file_label}.pdf",
            mime="application/pdf",
        )

with tab_chat:
    if not gemini_api_key:
        st.info("Add your Gemini API key to Streamlit secrets (GEMINI_API_KEY) to start asking questions about your data.", icon=":material/key:")
    else:
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        data_summary = filtered.to_csv(index=False)

        system_prompt = (
            "You are a helpful teaching assistant analyzing student letter identification progress data. "
            "You have access to the following student data:\n\n"
            f"{data_summary}\n\n"
            "Columns explained:\n"
            "- Student Name: the student's name\n"
            "- Week: the date of the assessment\n"
            "- Uppercase: number of uppercase letters identified (out of 26)\n"
            "- Lowercase: number of lowercase letters identified (out of 26)\n"
            "- Sound Total: number of letter sounds identified (out of 26)\n"
            "- Letter Sound: number of letter sounds identified (out of 26)\n"
            "- Total Letter ID %: combined uppercase + lowercase as a percentage of 52\n"
            "- Letter Sound %: letter sounds as a percentage of 26\n"
            "- Known Uppercase: comma-separated list of specific uppercase letters the student knows\n"
            "- Known Lowercase: comma-separated list of specific lowercase letters the student knows\n"
            "- Known Sounds: comma-separated list of specific letter sounds the student knows\n\n"
            "Answer questions clearly and concisely. When discussing performance, reference the color thresholds: "
            "green (80%+), yellow (65-79%), orange (40-64%), red (below 40%). "
            "Provide actionable insights when possible."
        )

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask a question about your student data..."):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            client = genai.Client(api_key=gemini_api_key)
            contents = [
                types.Content(
                    role="user" if m["role"] == "user" else "model",
                    parts=[types.Part.from_text(text=m["content"])],
                )
                for m in st.session_state.chat_messages
            ]

            with st.chat_message("assistant"):
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                        ),
                    )
                    reply = response.text
                    st.markdown(reply)
                except Exception as e:
                    reply = None
                    st.error(f"Gemini API error: {e}")

            if reply:
                st.session_state.chat_messages.append({"role": "assistant", "content": reply})
