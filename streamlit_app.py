import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Letter ID progress tracker",
    page_icon=":material/school:",
    layout="wide",
)

st.title("Letter identification progress tracker")

uploaded_file = st.file_uploader(
    "Upload student data CSV",
    type=["csv"],
    help="Columns: Student Name, Week, Uppercase, Lowercase, Letter Sound",
)

if uploaded_file is None:
    st.info(
        "Upload a CSV with columns: **Student Name**, **Week** (date), "
        "**Uppercase** (out of 26), **Lowercase** (out of 26), **Letter Sound** (out of 26).",
        icon=":material/upload_file:",
    )
    st.stop()

df = pd.read_csv(uploaded_file)

required_cols = ["Student Name", "Week", "Uppercase", "Lowercase", "Letter Sound"]
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

if not selected_students:
    st.warning("Select at least one student.")
    st.stop()

if not metrics:
    st.warning("Select at least one metric.")
    st.stop()

filtered = df[df["Student Name"].isin(selected_students)]

latest = filtered.loc[filtered.groupby("Student Name")["Week"].idxmax()]
most_recent_date = latest["Week"].max().strftime("%B %d, %Y")

st.subheader(f"Student scorecard - {most_recent_date}")

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

for idx, (_, row) in enumerate(latest.iterrows()):
    with st.container(border=True):
        st.markdown(f"**{row['Student Name']}**")
        cols = st.columns(4)
        cols[0].metric("Uppercase ID", f"{int(row['Uppercase'])}/26")
        cols[1].metric("Lowercase ID", f"{int(row['Lowercase'])}/26")
        tid = row['Total Letter ID %']
        with cols[2]:
            with st.container(key=f"tid_{idx}"):
                st.metric("Total Letter ID", f"{tid:.0f}%")
        ls = row['Letter Sound %']
        with cols[3]:
            with st.container(key=f"ls_{idx}"):
                st.metric("Letter Sound", f"{ls:.0f}%")

st.subheader("Individual student progress")

def progress_bar_html(val):
    color = COLOR_MAP_SOFT[score_color(val)]
    return (
        f'<div style="background:#e0e0e0;border-radius:4px;width:100%;height:20px;position:relative;">'
        f'<div style="background:{color};width:{val}%;height:100%;border-radius:4px;"></div>'
        f'<span style="position:absolute;top:0;left:50%;transform:translateX(-50%);font-size:12px;line-height:20px;color:#333;font-weight:600;">{val:.1f}%</span>'
        f'</div>'
    )

for student in selected_students:
    student_df = filtered[filtered["Student Name"] == student]
    student_melted = student_df.melt(
        id_vars=["Student Name", "Week", "Week Label"],
        value_vars=[m for m in metrics],
        var_name="Metric",
        value_name="Score (%)",
    )
    student_melted["Label"] = student_melted["Score (%)"].round(0).astype(int).astype(str) + "%"

    with st.container(border=True):
        st.markdown(f"**{student}**")

        bars = (
            alt.Chart(student_melted)
            .mark_bar()
            .encode(
                x=alt.X("Week Label:O", title="Week", sort=alt.SortField("Week"), axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Score (%):Q", title="Score (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Metric:N"),
                xOffset="Metric:N",
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
                xOffset="Metric:N",
            )
        )

        chart = bars + labels
        st.altair_chart(chart, use_container_width=True)

        display_cols = ["Week", "Uppercase", "Lowercase"] + [m for m in metrics]
        table_df = student_df[display_cols].sort_values("Week").reset_index(drop=True)
        table_df["Week"] = table_df["Week"].dt.strftime("%b %d, %Y")

        header_row = "".join(
            f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">{c}</th>'
            for c in ["Week", "Uppercase ID", "Lowercase ID"] + [m for m in metrics if m in table_df.columns]
        )

        body_rows = ""
        for _, r in table_df.iterrows():
            cells = (
                f'<td style="padding:6px 12px;font-size:13px;">{r["Week"]}</td>'
                f'<td style="padding:6px 12px;font-size:13px;">{int(r["Uppercase"])}</td>'
                f'<td style="padding:6px 12px;font-size:13px;">{int(r["Lowercase"])}</td>'
            )
            for m in metrics:
                if m in table_df.columns:
                    cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r[m])}</td>'
            body_rows += f"<tr>{cells}</tr>"

        html_table = (
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>{header_row}</tr></thead>'
            f'<tbody>{body_rows}</tbody>'
            f'</table></div>'
        )
        st.markdown(html_table, unsafe_allow_html=True)

st.subheader("Cohort progress")

cohort_df = filtered.groupby(["Week", "Week Label"], as_index=False)[
    ["Total Letter ID %", "Letter Sound %"]
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

    cohort_bars = (
        alt.Chart(cohort_melted)
        .mark_bar()
        .encode(
            x=alt.X("Week Label:O", title="Week", sort=alt.SortField("Week"), axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Score (%):Q", title="Avg Score (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Metric:N"),
            xOffset="Metric:N",
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
            xOffset="Metric:N",
        )
    )

    cohort_chart = cohort_bars + cohort_labels
    st.altair_chart(cohort_chart, use_container_width=True)

    cohort_table_df = cohort_df.copy()
    cohort_table_df["Week"] = cohort_table_df["Week"].dt.strftime("%b %d, %Y")

    cohort_header = "".join(
        f'<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #ddd;font-size:13px;">{c}</th>'
        for c in ["Week"] + [m for m in metrics if m in cohort_table_df.columns]
    )

    cohort_body = ""
    for _, r in cohort_table_df.iterrows():
        cells = f'<td style="padding:6px 12px;font-size:13px;">{r["Week"]}</td>'
        for m in metrics:
            if m in cohort_table_df.columns:
                cells += f'<td style="padding:6px 12px;min-width:140px;">{progress_bar_html(r[m])}</td>'
        cohort_body += f"<tr>{cells}</tr>"

    cohort_html = (
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{cohort_header}</tr></thead>'
        f'<tbody>{cohort_body}</tbody>'
        f'</table></div>'
    )
    st.markdown(cohort_html, unsafe_allow_html=True)

with st.expander("Raw data", icon=":material/table:"):
    st.dataframe(filtered, hide_index=True, use_container_width=True)
