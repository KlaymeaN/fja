from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


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
# PATHS
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Change this if your dashboard.py is not inside src/
PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "jobs"


# ---------------------------------------------------------
# STYLING
# ---------------------------------------------------------

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    [data-testid="stMetric"] {
        background-color: rgba(250, 250, 250, 0.04);
        border: 1px solid rgba(150, 150, 150, 0.15);
        padding: 20px;
        border-radius: 14px;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.9rem;
    }

    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
    }

    div[data-testid="stPlotlyChart"] {
        border: 1px solid rgba(150, 150, 150, 0.12);
        border-radius: 14px;
        padding: 8px;
    }

    .dashboard-subtitle {
        color: #8b949e;
        font-size: 1rem;
        margin-top: -12px;
        margin-bottom: 25px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_parquet(PARQUET_PATH)

    df["date_posted"] = pd.to_datetime(
        df["date_posted"],
        errors="coerce"
    )

    # Friendly display names
    df["country"] = (
        df["country"]
        .fillna("unknown")
        .str.title()
    )

    df["company"] = df["company"].fillna("Unknown")
    df["job_title"] = df["job_title"].fillna("Unknown")
    df["location"] = df["location"].fillna("Unknown")

    return df


try:
    df = load_data()

except Exception as exc:
    st.error("Could not load the processed Parquet dataset.")
    st.code(str(exc))
    st.stop()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("Job Market Intelligence")

st.markdown(
    """
    <div class="dashboard-subtitle">
        Job posting trends collected through a multi-source Python + PySpark data pipeline
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------------

st.sidebar.header("Filters")

country_options = sorted(df["country"].dropna().unique())

selected_countries = st.sidebar.multiselect(
    "Country",
    options=country_options,
    default=country_options,
)

min_date = df["date_posted"].min()
max_date = df["date_posted"].max()

if pd.notna(min_date) and pd.notna(max_date):

    selected_dates = st.sidebar.date_input(
        "Date range",
        value=(
            min_date.date(),
            max_date.date(),
        ),
        min_value=min_date.date(),
        max_value=max_date.date(),
    )

else:
    selected_dates = None


search_term = st.sidebar.text_input(
    "Search job titles",
    placeholder="e.g. Data Engineer",
)


# ---------------------------------------------------------
# APPLY FILTERS
# ---------------------------------------------------------

filtered_df = df[
    df["country"].isin(selected_countries)
].copy()


if selected_dates and len(selected_dates) == 2:

    start_date = pd.Timestamp(selected_dates[0])
    end_date = pd.Timestamp(selected_dates[1])

    filtered_df = filtered_df[
        filtered_df["date_posted"].between(
            start_date,
            end_date
        )
    ]


if search_term:

    filtered_df = filtered_df[
        filtered_df["job_title"]
        .str.contains(
            search_term,
            case=False,
            na=False,
        )
    ]


# ---------------------------------------------------------
# KPIs
# ---------------------------------------------------------

total_jobs = len(filtered_df)

unique_companies = filtered_df["company"].nunique()

unique_locations = (
    filtered_df["location"]
    .replace("", pd.NA)
    .dropna()
    .nunique()
)

latest_date = filtered_df["date_posted"].max()

latest_date_text = (
    latest_date.strftime("%d %b %Y")
    if pd.notna(latest_date)
    else "N/A"
)


kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(
        "Job Postings",
        f"{total_jobs:,}",
    )

with kpi2:
    st.metric(
        "Companies",
        f"{unique_companies:,}",
    )

with kpi3:
    st.metric(
        "Locations",
        f"{unique_locations:,}",
    )

with kpi4:
    st.metric(
        "Latest Posting",
        latest_date_text,
    )


st.write("")


# ---------------------------------------------------------
# DAILY JOB POSTINGS
# ---------------------------------------------------------

st.subheader("Job Posting Activity")

daily_jobs = (
    filtered_df
    .dropna(subset=["date_posted"])
    .groupby("date_posted")
    .size()
    .reset_index(name="jobs")
    .sort_values("date_posted")
)


fig_daily = px.area(
    daily_jobs,
    x="date_posted",
    y="jobs",
    markers=True,
    labels={
        "date_posted": "Date",
        "jobs": "Job postings",
    },
)

fig_daily.update_layout(
    height=360,
    margin=dict(l=10, r=10, t=20, b=10),
    xaxis_title=None,
    yaxis_title="Jobs",
    hovermode="x unified",
)

fig_daily.update_traces(
    line=dict(width=3)
)

st.plotly_chart(
    fig_daily,
    use_container_width=True,
)


# ---------------------------------------------------------
# COUNTRY + COMPANIES
# ---------------------------------------------------------

left, right = st.columns(2)


with left:

    st.subheader("Jobs by Country")

    country_counts = (
        filtered_df
        .groupby("country")
        .size()
        .reset_index(name="jobs")
        .sort_values(
            "jobs",
            ascending=False
        )
    )

    fig_country = px.bar(
        country_counts,
        x="jobs",
        y="country",
        orientation="h",
        text="jobs",
        labels={
            "jobs": "Jobs",
            "country": "",
        },
    )

    fig_country.update_layout(
        height=400,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis={
            "categoryorder": "total ascending"
        },
        xaxis_title="Job postings",
    )

    fig_country.update_traces(
        textposition="outside"
    )

    st.plotly_chart(
        fig_country,
        use_container_width=True,
    )


with right:

    st.subheader("Top Hiring Companies")

    top_companies = (
        filtered_df
        .groupby("company")
        .size()
        .reset_index(name="jobs")
        .sort_values(
            "jobs",
            ascending=False
        )
        .head(10)
    )

    fig_companies = px.bar(
        top_companies,
        x="jobs",
        y="company",
        orientation="h",
        text="jobs",
        labels={
            "jobs": "Jobs",
            "company": "",
        },
    )

    fig_companies.update_layout(
        height=400,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis={
            "categoryorder": "total ascending"
        },
        xaxis_title="Job postings",
    )

    fig_companies.update_traces(
        textposition="outside"
    )

    st.plotly_chart(
        fig_companies,
        use_container_width=True,
    )


# ---------------------------------------------------------
# ROLE ANALYSIS
# ---------------------------------------------------------

st.subheader("Most Common Job Titles")

top_roles = (
    filtered_df
    .groupby("job_title")
    .size()
    .reset_index(name="jobs")
    .sort_values(
        "jobs",
        ascending=False
    )
    .head(15)
)


fig_roles = px.bar(
    top_roles,
    x="jobs",
    y="job_title",
    orientation="h",
    text="jobs",
    labels={
        "jobs": "Number of postings",
        "job_title": "",
    },
)

fig_roles.update_layout(
    height=520,
    margin=dict(l=10, r=10, t=20, b=10),
    yaxis={
        "categoryorder": "total ascending"
    },
    xaxis_title="Job postings",
)

fig_roles.update_traces(
    textposition="outside"
)

st.plotly_chart(
    fig_roles,
    use_container_width=True,
)


# ---------------------------------------------------------
# SIMPLE DATA QUALITY / PIPELINE INSIGHT
# ---------------------------------------------------------

st.subheader("Dataset Overview")

unknown_country = (
    filtered_df["country"]
    .eq("Unknown")
    .sum()
)

missing_location = (
    filtered_df["location"]
    .isin(["", "Unknown"])
    .sum()
)

quality1, quality2, quality3 = st.columns(3)

with quality1:

    known_country_pct = (
        ((total_jobs - unknown_country) / total_jobs * 100)
        if total_jobs
        else 0
    )

    st.metric(
        "Country identified",
        f"{known_country_pct:.1f}%",
    )

with quality2:

    location_pct = (
        ((total_jobs - missing_location) / total_jobs * 100)
        if total_jobs
        else 0
    )

    st.metric(
        "Location available",
        f"{location_pct:.1f}%",
    )

with quality3:

    st.metric(
        "Unique job titles",
        f"{filtered_df['job_title'].nunique():,}",
    )


# ---------------------------------------------------------
# DATA TABLE
# ---------------------------------------------------------

st.subheader("Explore Job Postings")

table_df = (
    filtered_df[
        [
            "date_posted",
            "job_title",
            "company",
            "location",
            "country",
        ]
    ]
    .sort_values(
        "date_posted",
        ascending=False
    )
)


st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "date_posted": st.column_config.DateColumn(
            "Posted",
            format="DD MMM YYYY",
        ),
        "job_title": "Job Title",
        "company": "Company",
        "location": "Location",
        "country": "Country",
    },
)


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.divider()

st.caption(
    "Built with Python • PySpark • Parquet • Streamlit • Plotly"
)
