import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
import psycopg


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="Job Market Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("JOB_DB_HOST", "localhost"),
    "port": int(os.getenv("JOB_DB_PORT", "5432")),
    "dbname": os.getenv("JOB_DB_NAME", "job_pipeline"),
    "user": os.getenv("JOB_DB_USER", "job_user"),
    "password": os.getenv("JOB_DB_PASSWORD"),
}


# ---------------------------------------------------------
# STYLING
# ---------------------------------------------------------

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1550px;
    }

    [data-testid="stMetric"] {
        background-color: rgba(250, 250, 250, 0.035);
        border: 1px solid rgba(150, 150, 150, 0.16);
        padding: 16px;
        border-radius: 12px;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.88rem;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.75rem;
        font-weight: 700;
    }

    div[data-testid="stPlotlyChart"] {
        border: 1px solid rgba(150, 150, 150, 0.12);
        border-radius: 12px;
        padding: 6px;
    }

    .dashboard-subtitle {
        color: #8b949e;
        font-size: 0.98rem;
        margin-top: -10px;
        margin-bottom: 18px;
    }

    .small-muted {
        color: #8b949e;
        font-size: 0.84rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

DECISION_ORDER = ["apply", "maybe", "skip", "pending", "unknown"]


def clean_text(series: pd.Series, fallback: str = "Unknown") -> pd.Series:
    return series.fillna("").astype(str).str.strip().replace("", fallback)


def normalize_decision(series: pd.Series) -> pd.Series:
    values = series.fillna("").astype(str).str.strip().str.lower()
    return values.replace("", "pending")


def empty_chart_message(message: str = "No data for the selected filters."):
    st.info(message)


def horizontal_bar(data, x, y, x_label, height=390):
    fig = px.bar(
        data,
        x=x,
        y=y,
        orientation="h",
        text=x,
        labels={x: x_label, y: ""},
    )
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=20, t=15, b=10),
        yaxis={"categoryorder": "total ascending"},
        xaxis_title=x_label,
        hovermode="y unified",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    query = """
        SELECT
            id,
            source,
            source_job_id,
            job_title,
            company,
            location,
            country,
            date_posted,
            job_url,
            application_type,
            ai_status,
            ai_score,
            ai_decision,
            ai_reason,
            first_seen_at,
            last_seen_at
        FROM public.jobs
        ORDER BY first_seen_at DESC NULLS LAST, id DESC
    """

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [column.name for column in cur.description]

    frame = pd.DataFrame(rows, columns=columns)

    if frame.empty:
        return frame

    for col in ["date_posted", "first_seen_at", "last_seen_at"]:
        frame[col] = pd.to_datetime(frame[col], errors="coerce", utc=True)

    frame["country"] = clean_text(frame["country"]).str.title()
    frame["company"] = clean_text(frame["company"])
    frame["job_title"] = clean_text(frame["job_title"])
    frame["location"] = clean_text(frame["location"])
    frame["source"] = clean_text(frame["source"])
    frame["application_type"] = clean_text(frame["application_type"])
    frame["ai_status"] = clean_text(frame["ai_status"], "pending").str.lower()
    frame["ai_decision"] = normalize_decision(frame["ai_decision"])
    frame["ai_score"] = pd.to_numeric(frame["ai_score"], errors="coerce")

    return frame


# ---------------------------------------------------------
# HEADER + REFRESH
# ---------------------------------------------------------

header_left, header_right = st.columns([6, 1])

with header_left:
    st.title("Job Market Intelligence")
    st.markdown(
        """
        <div class="dashboard-subtitle">
            Operational view of job-market ingestion, AI scoring, and application opportunities
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    st.write("")
    if st.button("↻ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    df = load_data()
except Exception as exc:
    st.error("Could not load jobs from PostgreSQL.")
    st.code(str(exc))
    st.stop()

if df.empty:
    st.warning("The jobs table is currently empty.")
    st.stop()


# ---------------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------------

st.sidebar.header("Filters")

country_options = sorted(df["country"].dropna().unique().tolist())
source_options = sorted(df["source"].dropna().unique().tolist())
decision_options = [
    d for d in DECISION_ORDER if d in set(df["ai_decision"].dropna().unique())
]
company_options = sorted(df["company"].dropna().unique().tolist())

selected_countries = st.sidebar.multiselect(
    "Country",
    country_options,
    default=country_options,
)

selected_sources = st.sidebar.multiselect(
    "Source",
    source_options,
    default=source_options,
)

selected_decisions = st.sidebar.multiselect(
    "AI decision",
    decision_options,
    default=decision_options,
)

selected_companies = st.sidebar.multiselect(
    "Company",
    company_options,
    default=[],
    placeholder="All companies",
)

min_date = df["date_posted"].dropna().min()
max_date = df["date_posted"].dropna().max()

selected_dates = None
if pd.notna(min_date) and pd.notna(max_date):
    selected_dates = st.sidebar.date_input(
        "Posting date",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date(),
    )

search_term = st.sidebar.text_input(
    "Search",
    placeholder="Title, company, location...",
)

st.sidebar.divider()
show_only_scored = st.sidebar.checkbox("Only scored jobs", value=False)


# ---------------------------------------------------------
# APPLY FILTERS
# ---------------------------------------------------------

filtered_df = df.copy()

if selected_countries:
    filtered_df = filtered_df[filtered_df["country"].isin(selected_countries)]
else:
    filtered_df = filtered_df.iloc[0:0]

if selected_sources:
    filtered_df = filtered_df[filtered_df["source"].isin(selected_sources)]
else:
    filtered_df = filtered_df.iloc[0:0]

if selected_decisions:
    filtered_df = filtered_df[filtered_df["ai_decision"].isin(selected_decisions)]
else:
    filtered_df = filtered_df.iloc[0:0]

if selected_companies:
    filtered_df = filtered_df[filtered_df["company"].isin(selected_companies)]

if selected_dates and len(selected_dates) == 2:
    start_date = pd.Timestamp(selected_dates[0], tz="UTC")
    end_date = pd.Timestamp(selected_dates[1], tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    filtered_df = filtered_df[
        filtered_df["date_posted"].between(start_date, end_date)
    ]

if show_only_scored:
    filtered_df = filtered_df[filtered_df["ai_score"].notna()]

if search_term:
    needle = search_term.strip()
    mask = (
        filtered_df["job_title"].str.contains(needle, case=False, na=False)
        | filtered_df["company"].str.contains(needle, case=False, na=False)
        | filtered_df["location"].str.contains(needle, case=False, na=False)
        | filtered_df["country"].str.contains(needle, case=False, na=False)
    )
    filtered_df = filtered_df[mask]


# ---------------------------------------------------------
# DATA FRESHNESS
# ---------------------------------------------------------

latest_seen = df["last_seen_at"].max()
latest_ingested = df["first_seen_at"].max()

freshness_parts = []
if pd.notna(latest_ingested):
    freshness_parts.append(f"latest ingestion: {latest_ingested.strftime('%d %b %Y %H:%M UTC')}")
if pd.notna(latest_seen):
    freshness_parts.append(f"latest seen: {latest_seen.strftime('%d %b %Y %H:%M UTC')}")

if freshness_parts:
    st.caption(" • ".join(freshness_parts))


# ---------------------------------------------------------
# KPI SUMMARY
# ---------------------------------------------------------

total_jobs = len(filtered_df)
scored_jobs = int(filtered_df["ai_score"].notna().sum())
pending_jobs = int((filtered_df["ai_decision"] == "pending").sum())
apply_jobs = int((filtered_df["ai_decision"] == "apply").sum())
maybe_jobs = int((filtered_df["ai_decision"] == "maybe").sum())
skip_jobs = int((filtered_df["ai_decision"] == "skip").sum())
avg_score = filtered_df["ai_score"].mean()

scored_decision_count = apply_jobs + maybe_jobs + skip_jobs
apply_rate = (apply_jobs / scored_decision_count * 100) if scored_decision_count else 0

now_utc = pd.Timestamp.now(tz="UTC")
new_7d = int(
    filtered_df["first_seen_at"].ge(now_utc - pd.Timedelta(days=7)).fillna(False).sum()
)

kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

kpi1.metric("Jobs", f"{total_jobs:,}")
kpi2.metric("New · 7 days", f"{new_7d:,}")
kpi3.metric("APPLY", f"{apply_jobs:,}", f"{apply_rate:.1f}% of decided")
kpi4.metric("MAYBE", f"{maybe_jobs:,}")
kpi5.metric("Pending AI", f"{pending_jobs:,}")
kpi6.metric("Avg AI score", f"{avg_score:.1f}" if pd.notna(avg_score) else "N/A")

st.write("")


# ---------------------------------------------------------
# TOP-LEVEL ANALYTICS
# ---------------------------------------------------------

left, right = st.columns([2, 1])

with left:
    st.subheader("Job posting activity")
    daily_jobs = (
        filtered_df.dropna(subset=["date_posted"])
        .assign(posting_day=lambda x: x["date_posted"].dt.floor("D"))
        .groupby("posting_day")
        .size()
        .reset_index(name="jobs")
        .sort_values("posting_day")
    )

    if daily_jobs.empty:
        empty_chart_message()
    else:
        fig_daily = px.area(
            daily_jobs,
            x="posting_day",
            y="jobs",
            markers=True,
            labels={"posting_day": "Date", "jobs": "Job postings"},
        )
        fig_daily.update_layout(
            height=355,
            margin=dict(l=10, r=10, t=15, b=10),
            xaxis_title=None,
            yaxis_title="Jobs",
            hovermode="x unified",
        )
        fig_daily.update_traces(line=dict(width=2.5))
        st.plotly_chart(fig_daily, use_container_width=True)

with right:
    st.subheader("AI decisions")
    decision_counts = (
        filtered_df.groupby("ai_decision")
        .size()
        .reset_index(name="jobs")
    )
    decision_counts["ai_decision"] = pd.Categorical(
        decision_counts["ai_decision"], categories=DECISION_ORDER, ordered=True
    )
    decision_counts = decision_counts.sort_values("ai_decision")

    if decision_counts.empty:
        empty_chart_message()
    else:
        fig_decision = px.bar(
            decision_counts,
            x="ai_decision",
            y="jobs",
            text="jobs",
            labels={"ai_decision": "", "jobs": "Jobs"},
        )
        fig_decision.update_layout(
            height=355,
            margin=dict(l=10, r=10, t=15, b=10),
            showlegend=False,
            xaxis_title=None,
            yaxis_title="Jobs",
        )
        fig_decision.update_traces(textposition="outside")
        st.plotly_chart(fig_decision, use_container_width=True)


# ---------------------------------------------------------
# PIPELINE ANALYTICS
# ---------------------------------------------------------

st.subheader("Pipeline activity")

pipeline_left, pipeline_right = st.columns(2)

with pipeline_left:
    ingestion_daily = (
        filtered_df.dropna(subset=["first_seen_at"])
        .assign(ingestion_day=lambda x: x["first_seen_at"].dt.floor("D"))
        .groupby("ingestion_day")
        .size()
        .reset_index(name="new_jobs")
        .sort_values("ingestion_day")
    )

    if ingestion_daily.empty:
        empty_chart_message("No ingestion timestamps available.")
    else:
        fig_ingestion = px.line(
            ingestion_daily,
            x="ingestion_day",
            y="new_jobs",
            markers=True,
            labels={"ingestion_day": "Date", "new_jobs": "New jobs ingested"},
            title="New jobs ingested per day",
        )
        fig_ingestion.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=45, b=10),
            xaxis_title=None,
            yaxis_title="New jobs",
            hovermode="x unified",
        )
        st.plotly_chart(fig_ingestion, use_container_width=True)

with pipeline_right:
    source_counts = (
        filtered_df.groupby("source")
        .size()
        .reset_index(name="jobs")
        .sort_values("jobs", ascending=False)
    )

    if source_counts.empty:
        empty_chart_message()
    else:
        st.plotly_chart(
            horizontal_bar(source_counts, "jobs", "source", "Jobs", height=350),
            use_container_width=True,
        )


# ---------------------------------------------------------
# AI SCORE ANALYTICS
# ---------------------------------------------------------

st.subheader("AI scoring")

score_left, score_right = st.columns(2)
scored_df = filtered_df.dropna(subset=["ai_score"]).copy()

with score_left:
    if scored_df.empty:
        empty_chart_message("No scored jobs for the selected filters.")
    else:
        fig_score = px.histogram(
            scored_df,
            x="ai_score",
            nbins=20,
            labels={"ai_score": "AI score", "count": "Jobs"},
            title="Score distribution",
        )
        fig_score.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=45, b=10),
            yaxis_title="Jobs",
            xaxis_title="AI score",
            showlegend=False,
        )
        st.plotly_chart(fig_score, use_container_width=True)

with score_right:
    if scored_df.empty:
        empty_chart_message("No scored jobs for the selected filters.")
    else:
        score_by_decision = (
            scored_df.groupby("ai_decision")["ai_score"]
            .agg(["count", "mean"])
            .reset_index()
            .rename(columns={"count": "jobs", "mean": "avg_score"})
        )
        score_by_decision["avg_score"] = score_by_decision["avg_score"].round(1)
        score_by_decision["ai_decision"] = pd.Categorical(
            score_by_decision["ai_decision"], categories=DECISION_ORDER, ordered=True
        )
        score_by_decision = score_by_decision.sort_values("ai_decision")

        fig_avg_score = px.bar(
            score_by_decision,
            x="ai_decision",
            y="avg_score",
            text="avg_score",
            hover_data={"jobs": True},
            labels={"ai_decision": "", "avg_score": "Average AI score", "jobs": "Jobs"},
            title="Average score by AI decision",
        )
        fig_avg_score.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=45, b=10),
            xaxis_title=None,
            yaxis_title="Average score",
            showlegend=False,
        )
        fig_avg_score.update_traces(textposition="outside")
        st.plotly_chart(fig_avg_score, use_container_width=True)


# ---------------------------------------------------------
# MARKET BREAKDOWNS
# ---------------------------------------------------------

st.subheader("Market breakdown")

market_left, market_right = st.columns(2)

with market_left:
    country_counts = (
        filtered_df.groupby("country")
        .size()
        .reset_index(name="jobs")
        .sort_values("jobs", ascending=False)
    )

    if country_counts.empty:
        empty_chart_message()
    else:
        st.plotly_chart(
            horizontal_bar(country_counts, "jobs", "country", "Jobs"),
            use_container_width=True,
        )

with market_right:
    top_companies = (
        filtered_df.groupby("company")
        .size()
        .reset_index(name="jobs")
        .sort_values("jobs", ascending=False)
        .head(12)
    )

    if top_companies.empty:
        empty_chart_message()
    else:
        st.plotly_chart(
            horizontal_bar(top_companies, "jobs", "company", "Jobs"),
            use_container_width=True,
        )

roles_left, apps_right = st.columns(2)

with roles_left:
    st.markdown("#### Most common job titles")
    top_roles = (
        filtered_df.groupby("job_title")
        .size()
        .reset_index(name="jobs")
        .sort_values("jobs", ascending=False)
        .head(15)
    )
    if top_roles.empty:
        empty_chart_message()
    else:
        st.plotly_chart(
            horizontal_bar(top_roles, "jobs", "job_title", "Jobs", height=480),
            use_container_width=True,
        )

with apps_right:
    st.markdown("#### Application type")
    app_counts = (
        filtered_df.groupby("application_type")
        .size()
        .reset_index(name="jobs")
        .sort_values("jobs", ascending=False)
        .head(15)
    )
    if app_counts.empty:
        empty_chart_message()
    else:
        st.plotly_chart(
            horizontal_bar(app_counts, "jobs", "application_type", "Jobs", height=480),
            use_container_width=True,
        )


# ---------------------------------------------------------
# DATA QUALITY / PROCESS COVERAGE
# ---------------------------------------------------------

st.subheader("Data quality & processing coverage")

missing_location = filtered_df["location"].eq("Unknown").sum()
missing_country = filtered_df["country"].eq("Unknown").sum()
missing_posting_date = filtered_df["date_posted"].isna().sum()
missing_url = filtered_df["job_url"].fillna("").astype(str).str.strip().eq("").sum()

country_coverage = ((total_jobs - missing_country) / total_jobs * 100) if total_jobs else 0
location_coverage = ((total_jobs - missing_location) / total_jobs * 100) if total_jobs else 0
posting_date_coverage = ((total_jobs - missing_posting_date) / total_jobs * 100) if total_jobs else 0
scoring_coverage = (scored_jobs / total_jobs * 100) if total_jobs else 0

q1, q2, q3, q4, q5 = st.columns(5)
q1.metric("Country coverage", f"{country_coverage:.1f}%")
q2.metric("Location coverage", f"{location_coverage:.1f}%")
q3.metric("Posting date coverage", f"{posting_date_coverage:.1f}%")
q4.metric("AI scoring coverage", f"{scoring_coverage:.1f}%")
q5.metric("Missing URLs", f"{int(missing_url):,}")


# ---------------------------------------------------------
# JOB EXPLORER
# ---------------------------------------------------------

st.subheader("Job explorer")

sort_option = st.selectbox(
    "Sort by",
    ["Newest ingested", "Newest posted", "Highest AI score"],
    index=0,
    label_visibility="collapsed",
)

if sort_option == "Newest posted":
    table_df = filtered_df.sort_values(["date_posted", "id"], ascending=[False, False])
elif sort_option == "Highest AI score":
    table_df = filtered_df.sort_values(["ai_score", "id"], ascending=[False, False], na_position="last")
else:
    table_df = filtered_df.sort_values(["first_seen_at", "id"], ascending=[False, False])

export_columns = [
    "id",
    "date_posted",
    "first_seen_at",
    "job_title",
    "company",
    "location",
    "country",
    "source",
    "application_type",
    "ai_decision",
    "ai_score",
    "ai_reason",
    "job_url",
]

view_df = table_df[export_columns].copy()

st.dataframe(
    view_df,
    use_container_width=True,
    hide_index=True,
    height=620,
    column_config={
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "date_posted": st.column_config.DatetimeColumn("Posted", format="DD MMM YYYY"),
        "first_seen_at": st.column_config.DatetimeColumn("First seen", format="DD MMM YYYY HH:mm"),
        "job_title": st.column_config.TextColumn("Job title", width="large"),
        "company": st.column_config.TextColumn("Company", width="medium"),
        "location": st.column_config.TextColumn("Location", width="medium"),
        "country": "Country",
        "source": "Source",
        "application_type": "Application type",
        "ai_decision": "AI decision",
        "ai_score": st.column_config.NumberColumn("AI score", format="%.1f"),
        "ai_reason": st.column_config.TextColumn("AI reason", width="large"),
        "job_url": st.column_config.LinkColumn("Job link", display_text="Open"),
    },
)

csv_data = view_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered jobs as CSV",
    data=csv_data,
    file_name=f"jobs_filtered_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
    mime="text/csv",
)


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.divider()
st.caption(
    f"PostgreSQL • Streamlit • Plotly • {len(df):,} total database rows • "
    f"dashboard cache TTL: 5 minutes"
)

