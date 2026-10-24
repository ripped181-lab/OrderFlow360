
from pathlib import Path
import re
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# ORDERFLOW360 — FULFILLMENT INTELLIGENCE DASHBOARD
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "orderflow.duckdb"

st.set_page_config(
    page_title="OrderFlow360 | Analytics",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------- UI THEME ----------------------------

st.markdown("""
<style>
.stApp {
    background: #0b1220;
    color: #e5edf8;
}
[data-testid="stSidebar"] {
    background: #111c2e;
    border-right: 1px solid #283952;
}
.hero {
    background: linear-gradient(120deg, #172b4b, #12445a);
    border: 1px solid #345879;
    padding: 24px 28px;
    border-radius: 18px;
    margin-bottom: 22px;
}
.hero h1 {
    color: #f4f8ff;
    font-size: 2.4rem;
    margin-bottom: 5px;
}
.hero p {
    color: #c7d8ed;
    margin: 0;
}
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #182740, #111b2d);
    border: 1px solid #2b405d;
    padding: 16px;
    border-radius: 13px;
}
[data-testid="stMetricLabel"] {
    color: #b7c9df;
}
[data-testid="stMetricValue"] {
    color: #f4f8ff;
}
h2, h3 {
    color: #edf4ff;
}
.small-note {
    color: #9fb2ca;
    font-size: 0.88rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
    <h1>📦 OrderFlow360</h1>
    <p>Fulfillment Intelligence · Customer Analytics · Courier SLA Monitoring</p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# HELPERS: SCHEMA DISCOVERY AND COLUMN NORMALIZATION
# ============================================================

def norm_name(name):
    """Normalize a column name for flexible matching."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def find_column(columns, candidates):
    """Return the actual column matching one of the candidate names."""
    lookup = {norm_name(c): c for c in columns}

    for candidate in candidates:
        key = norm_name(candidate)
        if key in lookup:
            return lookup[key]

    return None


def read_table(con, table_name):
    safe = '"' + table_name.replace('"', '""') + '"'
    return con.execute(f"SELECT * FROM {safe}").df()


def table_columns(con, table_name):
    safe = "'" + table_name.replace("'", "''") + "'"
    info = con.execute(f"PRAGMA table_info({safe})").df()
    return info["name"].tolist()


def find_table(table_names, candidates):
    """Find a table using likely warehouse naming conventions."""
    lookup = {norm_name(t): t for t in table_names}

    for candidate in candidates:
        key = norm_name(candidate)
        if key in lookup:
            return lookup[key]

    return None


def rename_to_canonical(df, mapping):
    """
    Rename discovered source columns to canonical dashboard names.
    Existing values are preserved.
    """
    rename = {}

    for canonical, candidates in mapping.items():
        actual = find_column(df.columns, candidates)
        if actual is not None and actual != canonical:
            if canonical not in df.columns:
                rename[actual] = canonical

    return df.rename(columns=rename)


def to_datetime_safe(series):
    """
    Support datetime strings, timestamps, and common integer
    date keys such as 20261024.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    text = series.astype("string").str.strip()
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    # Integer/string date keys in YYYYMMDD form.
    eight_digits = text.str.fullmatch(r"\d{8}", na=False)

    if eight_digits.any():
        result.loc[eight_digits] = pd.to_datetime(
            text.loc[eight_digits],
            format="%Y%m%d",
            errors="coerce",
        )

    other = ~eight_digits & text.notna()

    if other.any():
        result.loc[other] = pd.to_datetime(
            text.loc[other],
            errors="coerce",
            format="mixed",
        )

    # Unix epoch support for numeric timestamp columns.
    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        epoch_mask = numeric.notna() & ~eight_digits

        if epoch_mask.any():
            values = numeric.loc[epoch_mask]
            median = values.abs().median()

            if median > 1e17:
                unit = "ns"
            elif median > 1e14:
                unit = "us"
            elif median > 1e11:
                unit = "ms"
            else:
                unit = "s"

            result.loc[epoch_mask] = pd.to_datetime(
                values, unit=unit, errors="coerce"
            )

    return result


def fmt_num(value, digits=0):
    if pd.isna(value):
        return "N/A"
    return f"{value:,.{digits}f}"


def fmt_money(value):
    if pd.isna(value):
        return "N/A"
    return f"₹{value:,.2f}"


def fmt_pct(value):
    if pd.isna(value):
        return "N/A"
    return f"{value:.2f}%"


def apply_chart_theme(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dbeafe"),
        margin=dict(l=15, r=15, t=55, b=15),
        legend_title_text="",
    )
    return fig


def download_csv(df, filename, label):
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
    )


# ============================================================
# LOAD THE ACTUAL WAREHOUSE
# ============================================================

if not DB_PATH.exists():
    st.error(f"Database not found: {DB_PATH}")
    st.info(
        "Check that data/orderflow.duckdb exists. "
        "Run your warehouse creation script first."
    )
    st.stop()

try:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        table_names = con.execute("SHOW TABLES").df().iloc[:, 0].tolist()

        if not table_names:
            st.error("The DuckDB database has no tables.")
            st.stop()

        fact_table = find_table(
            table_names,
            [
                "FACT_ORDER_FULFILLMENT",
                "FACT_ORDERS",
                "ORDERS_CLEAN",
                "ORDERS",
                "ORDER_TRANSACTIONS",
            ],
        )

        # If the preferred names are absent, look for a table
        # containing both an order identifier and an order status.
        if fact_table is None:
            for table in table_names:
                cols = table_columns(con, table)
                has_order = find_column(
                    cols, ["ORDER_ID", "ORDERID", "TRANSACTION_ID"]
                )
                has_status = find_column(
                    cols, ["ORDER_STATUS", "STATUS"]
                )
                if has_order and has_status:
                    fact_table = table
                    break

        if fact_table is None:
            st.error(
                "Could not identify the order fact table. "
                "Available tables: " + ", ".join(table_names)
            )
            st.stop()

        raw_fact = read_table(con, fact_table)

        customer_table = find_table(
            table_names,
            ["DIM_CUSTOMER", "CUSTOMERS", "CUSTOMER_MASTER", "CUSTOMERS_CLEAN"],
        )

        courier_table = find_table(
            table_names,
            ["DIM_COURIER", "COURIERS", "COURIER_MASTER", "COURIERS_CLEAN"],
        )

        raw_customers = (
            read_table(con, customer_table)
            if customer_table else pd.DataFrame()
        )

        raw_couriers = (
            read_table(con, courier_table)
            if courier_table else pd.DataFrame()
        )

except Exception as exc:
    st.error(f"Could not read the DuckDB warehouse: {exc}")
    st.stop()


# ============================================================
# MAP COMMON SOURCE COLUMN NAMES
# ============================================================

fact_mapping = {
    "ORDER_ID": [
        "ORDER_ID", "ORDERID", "TRANSACTION_ID", "ORDER_NUMBER",
    ],
    "CUSTOMER_ID": [
        "CUSTOMER_ID", "CUSTOMERID", "CLIENT_ID",
    ],
    "COURIER_ID": [
        "COURIER_ID", "COURIERID", "DELIVERY_PARTNER_ID",
        "SHIPPER_ID",
    ],
    "COURIER_NAME": [
        "COURIER_NAME", "COURIER", "DELIVERY_PARTNER",
        "SHIPPER_NAME",
    ],
    "CUSTOMER_NAME": [
        "CUSTOMER_NAME", "CLIENT_NAME",
    ],
    "ORDER_STATUS": [
        "ORDER_STATUS", "STATUS", "ORDERSTATE",
    ],
    "ORDER_VALUE": [
        "ORDER_VALUE", "TOTAL_ORDER_VALUE", "ORDER_AMOUNT",
        "LINE_TOTAL", "TOTAL_AMOUNT",
    ],
    "ORDER_DATE": [
        "ORDER_DATE", "ORDER_DATE_KEY", "ORDER_TIMESTAMP",
        "CREATED_AT", "PURCHASE_DATE",
    ],
    "SHIPPED_DATE": [
        "SHIPPED_DATE", "SHIP_DATE", "DISPATCH_DATE",
        "SHIPPING_DATE",
    ],
    "DELIVERY_DATE": [
        "DELIVERY_DATE", "DELIVERED_DATE", "ACTUAL_DELIVERY_DATE",
    ],
    "DELIVERY_DURATION_DAYS": [
        "DELIVERY_DURATION_DAYS", "DELIVERY_DAYS",
        "ACTUAL_DELIVERY_DAYS",
    ],
    "SLA_MET": [
        "SLA_MET", "IS_ON_TIME", "ON_TIME",
        "DELIVERED_ON_TIME",
    ],
    "SLA_DAYS": [
        "SLA_DAYS", "SLA_DAYS_TARGET", "DELIVERY_SLA_DAYS",
        "TARGET_DELIVERY_DAYS",
    ],
    "QUANTITY": ["QUANTITY", "QTY", "UNITS"],
    "CATEGORY": ["CATEGORY", "PRODUCT_CATEGORY"],
}

fact = rename_to_canonical(raw_fact, fact_mapping)

if "ORDER_ID" not in fact.columns:
    st.error(
        f"Table '{fact_table}' does not have a recognizable order ID column."
    )
    st.write("Available columns:", list(raw_fact.columns))
    st.stop()

# Use row identity only as a last-resort fallback.
# It does not establish that each row is a distinct business order.
if "ORDER_STATUS" not in fact.columns:
    st.error(
        f"Table '{fact_table}' has no recognizable order status column. "
        "Status-based KPIs cannot be calculated."
    )
    st.write("Available columns:", list(raw_fact.columns))
    st.stop()

customer_mapping = {
    "CUSTOMER_ID": ["CUSTOMER_ID", "CUSTOMERID", "CLIENT_ID"],
    "CUSTOMER_NAME": ["CUSTOMER_NAME", "CLIENT_NAME", "NAME"],
}

courier_mapping = {
    "COURIER_ID": [
        "COURIER_ID", "COURIERID", "DELIVERY_PARTNER_ID", "SHIPPER_ID",
    ],
    "COURIER_NAME": [
        "COURIER_NAME", "COURIER", "DELIVERY_PARTNER", "SHIPPER_NAME", "NAME",
    ],
    "SLA_DAYS": [
        "SLA_DAYS", "SLA_DAYS_TARGET", "DELIVERY_SLA_DAYS",
        "TARGET_DELIVERY_DAYS",
    ],
}

if not raw_customers.empty:
    customers = rename_to_canonical(raw_customers, customer_mapping)

    if (
        "CUSTOMER_ID" in customers.columns
        and "CUSTOMER_NAME" in customers.columns
    ):
        customers = customers[
            ["CUSTOMER_ID", "CUSTOMER_NAME"]
        ].drop_duplicates("CUSTOMER_ID")

        if "CUSTOMER_NAME" not in fact.columns:
            if "CUSTOMER_ID" in fact.columns:
                fact = fact.merge(
                    customers,
                    on="CUSTOMER_ID",
                    how="left",
                    validate="many_to_one",
                )

if not raw_couriers.empty:
    couriers = rename_to_canonical(raw_couriers, courier_mapping)

    if "COURIER_ID" in couriers.columns:
        keep = ["COURIER_ID"] + [
            c for c in ["COURIER_NAME", "SLA_DAYS"]
            if c in couriers.columns
        ]

        couriers = couriers[keep].drop_duplicates("COURIER_ID")

        if "COURIER_ID" in fact.columns:
            additions = [
                c for c in ["COURIER_NAME", "SLA_DAYS"]
                if c in couriers.columns and c not in fact.columns
            ]

            if additions:
                fact = fact.merge(
                    couriers[["COURIER_ID"] + additions],
                    on="COURIER_ID",
                    how="left",
                    validate="many_to_one",
                )

# Provide placeholders for optional columns. Missing values remain
# missing and are NOT fabricated.
for col in [
    "CUSTOMER_ID", "CUSTOMER_NAME", "COURIER_ID", "COURIER_NAME",
    "ORDER_VALUE", "ORDER_DATE", "SHIPPED_DATE", "DELIVERY_DATE",
    "DELIVERY_DURATION_DAYS", "SLA_MET", "SLA_DAYS",
    "QUANTITY", "CATEGORY",
]:
    if col not in fact.columns:
        fact[col] = pd.NA


# ============================================================
# STANDARDIZE DATA
# ============================================================

fact["ORDER_STATUS"] = (
    fact["ORDER_STATUS"]
    .astype("string")
    .str.strip()
    .str.upper()
    .str.replace(r"[\s-]+", "_", regex=True)
)

status_map = {
    "DELIVERED": "Delivered",
    "CANCELLED": "Cancelled",
    "CANCELED": "Cancelled",
    "RETURNED": "Returned",
    "IN_TRANSIT": "In Transit",
    "SHIPPED": "Shipped",
    "PROCESSING": "Processing",
}

fact["ORDER_STATUS"] = fact["ORDER_STATUS"].replace(status_map)

for col in ["ORDER_VALUE", "QUANTITY", "SLA_DAYS",
            "DELIVERY_DURATION_DAYS"]:
    fact[col] = pd.to_numeric(fact[col], errors="coerce")

for col in ["ORDER_DATE", "SHIPPED_DATE", "DELIVERY_DATE"]:
    fact[col] = to_datetime_safe(fact[col])

# Calculate delivery duration from actual dates if not already present.
duration_from_dates = (
    fact["DELIVERY_DATE"] - fact["SHIPPED_DATE"]
).dt.total_seconds() / 86400

fact["DELIVERY_DURATION_DAYS"] = (
    fact["DELIVERY_DURATION_DAYS"].fillna(duration_from_dates)
)

# Standardize SLA booleans from common string/numeric representations.
def parse_boolean(series):
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")

    mapping = {
        "TRUE": True, "T": True, "YES": True, "Y": True, "1": True,
        "FALSE": False, "F": False, "NO": False, "N": False, "0": False,
    }

    text = series.astype("string").str.strip().str.upper()
    mapped = text.map(mapping)

    return mapped.astype("boolean")


fact["SLA_MET"] = parse_boolean(fact["SLA_MET"])

# If the SLA flag is absent, derive it only when actual duration and
# a valid SLA target are available. Existing explicit SLA flags win.
can_derive_sla = (
    fact["DELIVERY_DURATION_DAYS"].notna()
    & fact["SLA_DAYS"].notna()
    & (fact["SLA_DAYS"] >= 0)
)

derived_sla = (
    fact["DELIVERY_DURATION_DAYS"] <= fact["SLA_DAYS"]
)

fact.loc[
    fact["SLA_MET"].isna() & can_derive_sla,
    "SLA_MET"
] = derived_sla.loc[
    fact["SLA_MET"].isna() & can_derive_sla
].astype("boolean")

# Stable order ID values are required for distinct-order counts.
fact["ORDER_ID"] = fact["ORDER_ID"].astype("string").str.strip()

# Add a single canonical date column for the date filter and trend.
fact["ORDER_DATE"] = pd.to_datetime(
    fact["ORDER_DATE"], errors="coerce"
)

# Inform the user of source limitations.
warnings = []

if fact["CUSTOMER_ID"].isna().all():
    warnings.append("No recognizable customer ID data; distinct customers and customer rankings are unavailable.")

if fact["COURIER_NAME"].isna().all() and fact["COURIER_ID"].isna().all():
    warnings.append("No recognizable courier information; courier analysis is unavailable.")

if fact["SLA_DAYS"].notna().sum() == 0:
    warnings.append("No SLA target values found. Average SLA days cannot be calculated.")

if fact["DELIVERY_DURATION_DAYS"].notna().sum() == 0:
    warnings.append("No delivery durations found. Average delivery days cannot be calculated.")

if fact["ORDER_DATE"].notna().sum() == 0:
    warnings.append("No usable order dates found. Monthly order and status trends cannot be calculated.")

for warning in warnings:
    st.warning(warning)

with st.expander("Warehouse diagnostics — view detected schema"):
    st.write("Database:", str(DB_PATH))
    st.write("Fact table:", fact_table)
    st.write("Tables detected:", table_names)
    st.write("Original fact columns:", list(raw_fact.columns))
    st.write("Canonical columns:", list(fact.columns))


# ============================================================
# SIDEBAR FILTERS
# ============================================================

st.sidebar.title("Dashboard Controls")
st.sidebar.caption("Filter the dashboard results.")

date_data = fact["ORDER_DATE"].dropna()

if not date_data.empty:
    min_date = date_data.min().date()
    max_date = date_data.max().date()

    date_range = st.sidebar.date_input(
        "Order date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
        date_mask = fact["ORDER_DATE"].dt.date.between(
            start_date, end_date
        ) | fact["ORDER_DATE"].isna()
        filtered = fact.loc[date_mask].copy()
    else:
        filtered = fact.copy()
else:
    filtered = fact.copy()
    st.sidebar.info("No valid order date available.")

all_statuses = sorted(
    filtered["ORDER_STATUS"].dropna().unique().tolist()
)

selected_statuses = st.sidebar.multiselect(
    "Order status",
    options=all_statuses,
    default=all_statuses,
)

filtered = filtered[
    filtered["ORDER_STATUS"].isin(selected_statuses)
].copy()

courier_labels = filtered["COURIER_NAME"].fillna(
    filtered["COURIER_ID"].astype("string")
)

filtered["COURIER_LABEL"] = courier_labels.fillna("Unknown courier")

all_couriers = sorted(filtered["COURIER_LABEL"].unique().tolist())

selected_couriers = st.sidebar.multiselect(
    "Courier",
    options=all_couriers,
    default=all_couriers,
)

filtered = filtered[
    filtered["COURIER_LABEL"].isin(selected_couriers)
].copy()

st.sidebar.divider()
st.sidebar.caption("OrderFlow360 · HCLTech Hackathon")


# ============================================================
# KPI CALCULATIONS
# ============================================================

# Counts use unique ORDER_ID, not row count.
total_orders = filtered["ORDER_ID"].nunique()

delivered = filtered[
    filtered["ORDER_STATUS"] == "Delivered"
].copy()

cancelled = filtered[
    filtered["ORDER_STATUS"] == "Cancelled"
].copy()

returned = filtered[
    filtered["ORDER_STATUS"] == "Returned"
].copy()

in_transit = filtered[
    filtered["ORDER_STATUS"] == "In Transit"
].copy()

distinct_customers = filtered["CUSTOMER_ID"].nunique()

delivered_count = delivered["ORDER_ID"].nunique()
cancelled_count = cancelled["ORDER_ID"].nunique()
returned_count = returned["ORDER_ID"].nunique()
in_transit_count = in_transit["ORDER_ID"].nunique()

avg_delivery_days = delivered["DELIVERY_DURATION_DAYS"].mean()
avg_sla_days = delivered["SLA_DAYS"].mean()

known_sla = delivered[delivered["SLA_MET"].notna()]
on_time_count = int((known_sla["SLA_MET"] == True).sum())
late_count = int((known_sla["SLA_MET"] == False).sum())

on_time_pct = (
    100 * on_time_count / len(known_sla)
    if len(known_sla) else float("nan")
)

late_pct = (
    100 * late_count / len(known_sla)
    if len(known_sla) else float("nan")
)

# Explicit working definition:
# shipment success rate = delivered unique orders / all unique orders.
shipment_success_rate = (
    100 * delivered_count / total_orders
    if total_orders else float("nan")
)

# Top 10 customers by unique order count.
customer_metrics = (
    filtered.dropna(subset=["CUSTOMER_ID"])
    .groupby(["CUSTOMER_ID", "CUSTOMER_NAME"], dropna=False)
    .agg(
        Total_Orders=("ORDER_ID", "nunique"),
        Total_Order_Value=("ORDER_VALUE", "sum"),
    )
    .reset_index()
    .sort_values(
        ["Total_Orders", "Total_Order_Value"],
        ascending=[False, False],
    )
    .head(10)
)

# Orders by courier.
orders_by_courier = (
    filtered.groupby("COURIER_LABEL")
    .agg(Total_Orders=("ORDER_ID", "nunique"))
    .reset_index()
    .sort_values("Total_Orders", ascending=False)
)

# Courier metrics: SLA percentages use only known SLA outcomes.
courier_metrics = (
    delivered.groupby("COURIER_LABEL", dropna=False)
    .agg(
        Delivered_Orders=("ORDER_ID", "nunique"),
        On_Time_Orders=("SLA_MET", lambda s: int((s == True).sum())),
        Late_Orders=("SLA_MET", lambda s: int((s == False).sum())),
        Known_SLA_Orders=("SLA_MET", lambda s: int(s.notna().sum())),
        Average_Delivery_Days=("DELIVERY_DURATION_DAYS", "mean"),
        Average_SLA_Days=("SLA_DAYS", "mean"),
    )
    .reset_index()
)

courier_metrics["On_Time_Pct"] = (
    100 * courier_metrics["On_Time_Orders"]
    / courier_metrics["Known_SLA_Orders"].replace(0, float("nan"))
)

courier_metrics["Delay_Pct"] = (
    100 * courier_metrics["Late_Orders"]
    / courier_metrics["Known_SLA_Orders"].replace(0, float("nan"))
)

# Monthly order trend.
monthly_source = filtered.dropna(subset=["ORDER_DATE"]).copy()
monthly_source["Month"] = (
    monthly_source["ORDER_DATE"].dt.to_period("M").dt.to_timestamp()
)

monthly_orders = (
    monthly_source.groupby("Month")
    .agg(
        Total_Orders=("ORDER_ID", "nunique"),
        Order_Value=("ORDER_VALUE", "sum"),
    )
    .reset_index()
    .sort_values("Month")
)

# Monthly delivery trend uses actual delivery date.
delivery_source = filtered[
    (filtered["ORDER_STATUS"] == "Delivered")
    & filtered["DELIVERY_DATE"].notna()
].copy()

delivery_source["Month"] = (
    delivery_source["DELIVERY_DATE"].dt.to_period("M").dt.to_timestamp()
)

monthly_deliveries = (
    delivery_source.groupby("Month")
    .agg(Delivered_Orders=("ORDER_ID", "nunique"))
    .reset_index()
    .sort_values("Month")
)

# Status-wise trend.
status_trend = (
    monthly_source.groupby(["Month", "ORDER_STATUS"])
    .agg(Orders=("ORDER_ID", "nunique"))
    .reset_index()
)

# Courier-wise trend by order month.
courier_trend = (
    monthly_source.groupby(["Month", "COURIER_LABEL"])
    .agg(Orders=("ORDER_ID", "nunique"))
    .reset_index()
)

# Data quality diagnostics.
unknown_sla_count = int(
    (delivered["SLA_MET"].isna()).sum()
)

unmatched_customer_count = (
    int(filtered["CUSTOMER_NAME"].isna().sum())
    if "CUSTOMER_NAME" in filtered.columns else len(filtered)
)

unmatched_courier_count = int(
    filtered["COURIER_LABEL"].eq("Unknown courier").sum()
)

duplicate_extra_rows = len(filtered) - filtered["ORDER_ID"].nunique()


# ============================================================
# EXECUTIVE OVERVIEW
# ============================================================

st.subheader("Executive Overview")
st.caption(
    "All metrics respond to the selected date, status, and courier filters."
)

row1 = st.columns(5)
row1[0].metric("Total Orders", fmt_num(total_orders))
row1[1].metric("Delivered Orders", fmt_num(delivered_count))
row1[2].metric("Cancelled Orders", fmt_num(cancelled_count))
row1[3].metric("Returned Orders", fmt_num(returned_count))
row1[4].metric("In-Transit Orders", fmt_num(in_transit_count))

row2 = st.columns(5)
row2[0].metric("Distinct Customers", fmt_num(distinct_customers))
row2[1].metric("Avg Delivery Days", fmt_num(avg_delivery_days, 2))
row2[2].metric("Avg SLA Days", fmt_num(avg_sla_days, 2))
row2[3].metric("On-Time Delivery", fmt_pct(on_time_pct))
row2[4].metric("Late Delivery", fmt_pct(late_pct))

row3 = st.columns(3)
row3[0].metric("Shipment Success Rate", fmt_pct(shipment_success_rate))
row3[1].metric("On-Time Orders", fmt_num(on_time_count))
row3[2].metric("Late Orders", fmt_num(late_count))

st.markdown(
    '<p class="small-note">On-time and late delivery percentages use '
    'delivered orders with a known SLA outcome. Shipment success rate is '
    'defined here as delivered unique orders divided by all unique orders.</p>',
    unsafe_allow_html=True,
)

st.divider()


# ============================================================
# FIVE MANDATORY ANALYTICS GROUPS + DATA QUALITY
# ============================================================

tab_orders, tab_customers, tab_fulfillment, tab_couriers, tab_trends, tab_quality = st.tabs([
    "📦 Order Metrics",
    "👥 Customer Metrics",
    "⏱️ Fulfillment Metrics",
    "🚚 Courier Metrics",
    "📈 Trend Metrics",
    "🛡️ Data Quality",
])


# --------------------- ORDER METRICS ------------------------

with tab_orders:
    st.subheader("Order Metrics")

    left, right = st.columns(2)

    status_summary = (
        filtered.groupby("ORDER_STATUS", dropna=False)
        .agg(Orders=("ORDER_ID", "nunique"))
        .reset_index()
        .sort_values("Orders", ascending=False)
    )

    with left:
        if not status_summary.empty:
            fig = px.bar(
                status_summary,
                x="ORDER_STATUS",
                y="Orders",
                text="Orders",
                title="Orders by Status",
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("No orders match the filters.")

    with right:
        if not status_summary.empty:
            fig = px.pie(
                status_summary,
                names="ORDER_STATUS",
                values="Orders",
                hole=0.55,
                title="Order Status Distribution",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("No status data available.")

    st.dataframe(status_summary, use_container_width=True, hide_index=True)
    download_csv(status_summary, "order_metrics.csv", "Download order metrics")


# -------------------- CUSTOMER METRICS ----------------------

with tab_customers:
    st.subheader("Customer Metrics")

    a, b = st.columns(2)
    a.metric("Distinct Customers", fmt_num(distinct_customers))
    b.metric("Customers in Top 10", fmt_num(len(customer_metrics)))

    st.markdown("#### Top 10 Customers by Orders")

    if not customer_metrics.empty:
        chart_data = customer_metrics.copy()
        chart_data["Customer_Label"] = (
            chart_data["CUSTOMER_NAME"]
            .fillna(chart_data["CUSTOMER_ID"].astype(str))
        )

        fig = px.bar(
            chart_data.sort_values("Total_Orders"),
            x="Total_Orders",
            y="Customer_Label",
            orientation="h",
            text="Total_Orders",
            title="Most Frequent Customers",
        )
        st.plotly_chart(apply_chart_theme(fig), use_container_width=True)

        display = customer_metrics.rename(columns={
            "CUSTOMER_ID": "Customer ID",
            "CUSTOMER_NAME": "Customer Name",
            "Total_Orders": "Total Orders",
            "Total_Order_Value": "Total Order Value",
        })

        st.dataframe(display, use_container_width=True, hide_index=True)
        download_csv(display, "top_10_customers.csv", "Download top 10 customers")
    else:
        st.warning(
            "Customer IDs or customer records are unavailable. "
            "Check the customer master and fact-table schema."
        )


# ------------------- FULFILLMENT METRICS --------------------

with tab_fulfillment:
    st.subheader("Fulfillment Metrics")

    left, right = st.columns(2)

    with left:
        outcome = pd.DataFrame({
            "SLA Outcome": ["On time", "Late", "Unknown"],
            "Orders": [
                on_time_count,
                late_count,
                unknown_sla_count,
            ],
        })

        fig = px.bar(
            outcome,
            x="SLA Outcome",
            y="Orders",
            text="Orders",
            title="Delivered Orders by SLA Outcome",
        )
        st.plotly_chart(apply_chart_theme(fig), use_container_width=True)

    with right:
        duration_data = delivered[
            delivered["DELIVERY_DURATION_DAYS"].notna()
        ]

        if not duration_data.empty:
            fig = px.histogram(
                duration_data,
                x="DELIVERY_DURATION_DAYS",
                nbins=20,
                title="Delivery Duration Distribution",
                labels={
                    "DELIVERY_DURATION_DAYS": "Delivery duration (days)"
                },
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("Delivery-duration data is unavailable.")

    fulfillment_summary = pd.DataFrame({
        "KPI": [
            "Average Delivery Days",
            "Average SLA Days",
            "On-Time Delivery %",
            "Late Delivery %",
            "Shipment Success Rate",
            "Delivered Orders",
            "On-Time Orders",
            "Late Orders",
            "Unknown SLA Outcomes",
        ],
        "Value": [
            avg_delivery_days,
            avg_sla_days,
            on_time_pct,
            late_pct,
            shipment_success_rate,
            delivered_count,
            on_time_count,
            late_count,
            unknown_sla_count,
        ],
    })

    st.dataframe(
        fulfillment_summary,
        use_container_width=True,
        hide_index=True,
    )
    download_csv(
        fulfillment_summary,
        "fulfillment_metrics.csv",
        "Download fulfillment metrics",
    )

    st.caption(
        "Average SLA days is calculated from the SLA_DAYS value available "
        "for delivered orders. Confirm whether your case study intends "
        "the courier target, a promised order-level SLA, or another measure."
    )


# ---------------------- COURIER METRICS ----------------------

with tab_couriers:
    st.subheader("Courier Metrics")

    left, right = st.columns(2)

    with left:
        if not orders_by_courier.empty:
            fig = px.bar(
                orders_by_courier,
                x="COURIER_LABEL",
                y="Total_Orders",
                text="Total_Orders",
                title="Orders by Courier",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("Courier data is unavailable.")

    with right:
        valid_rates = courier_metrics.dropna(subset=["On_Time_Pct"])

        if not valid_rates.empty:
            fig = px.bar(
                valid_rates.sort_values("On_Time_Pct"),
                x="On_Time_Pct",
                y="COURIER_LABEL",
                orientation="h",
                text="On_Time_Pct",
                title="Courier-wise On-Time %",
            )
            fig.update_traces(texttemplate="%{text:.1f}%")
            fig.update_xaxes(title="On-time delivery (%)")
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("No known courier SLA outcomes are available.")

    display_couriers = courier_metrics.rename(columns={
        "COURIER_LABEL": "Courier",
        "Delivered_Orders": "Delivered Orders",
        "On_Time_Orders": "On-Time Orders",
        "Late_Orders": "Late Orders",
        "Known_SLA_Orders": "Known SLA Outcomes",
        "On_Time_Pct": "On-Time %",
        "Delay_Pct": "Delay %",
        "Average_Delivery_Days": "Average Delivery Days",
        "Average_SLA_Days": "Average SLA Days",
    })

    st.markdown("#### Courier KPI Details")
    st.dataframe(
        display_couriers,
        use_container_width=True,
        hide_index=True,
    )
    download_csv(
        display_couriers,
        "courier_metrics.csv",
        "Download courier metrics",
    )

    ranked = courier_metrics.dropna(subset=["On_Time_Pct"])

    if not ranked.empty:
        # Display both rank and volume; a tiny sample can distort rankings.
        best = ranked.sort_values("On_Time_Pct", ascending=False).iloc[0]
        worst = ranked.sort_values("On_Time_Pct", ascending=True).iloc[0]

        a, b = st.columns(2)
        a.metric(
            "Best Performing Courier",
            str(best["COURIER_LABEL"]),
            f"{best['On_Time_Pct']:.1f}% on time",
        )
        b.metric(
            "Worst Performing Courier",
            str(worst["COURIER_LABEL"]),
            f"{worst['On_Time_Pct']:.1f}% on time",
        )

        st.caption(
            "Best/worst rankings are based on on-time percentage among "
            "known SLA outcomes. Review delivered volume before acting."
        )


# ----------------------- TREND METRICS ----------------------

with tab_trends:
    st.subheader("Trend Metrics")

    left, right = st.columns(2)

    with left:
        if not monthly_orders.empty:
            fig = px.line(
                monthly_orders,
                x="Month",
                y="Total_Orders",
                markers=True,
                title="Monthly Order Trend",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("Monthly order trend requires valid order dates.")

    with right:
        if not monthly_deliveries.empty:
            fig = px.line(
                monthly_deliveries,
                x="Month",
                y="Delivered_Orders",
                markers=True,
                title="Monthly Delivery Trend",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info(
                "Monthly delivery trend requires valid DELIVERY_DATE values."
            )

    left, right = st.columns(2)

    with left:
        if not status_trend.empty:
            fig = px.line(
                status_trend,
                x="Month",
                y="Orders",
                color="ORDER_STATUS",
                markers=True,
                title="Status-wise Trend",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("Status trend data is unavailable.")

    with right:
        if not courier_trend.empty:
            fig = px.line(
                courier_trend,
                x="Month",
                y="Orders",
                color="COURIER_LABEL",
                markers=True,
                title="Courier-wise Trend",
            )
            st.plotly_chart(apply_chart_theme(fig), use_container_width=True)
        else:
            st.info("Courier trend data is unavailable.")

    st.subheader("Monthly Order Value")
    if not monthly_orders.empty:
        fig = px.area(
            monthly_orders,
            x="Month",
            y="Order_Value",
            title="Monthly Order Value Trend",
        )
        st.plotly_chart(apply_chart_theme(fig), use_container_width=True)

    st.subheader("Monthly Order Table")
    st.dataframe(
        monthly_orders,
        use_container_width=True,
        hide_index=True,
    )
    download_csv(
        monthly_orders,
        "monthly_order_trend.csv",
        "Download monthly order trend",
    )


# ----------------------- DATA QUALITY -----------------------

with tab_quality:
    st.subheader("Data Quality & Reconciliation")

    quality = pd.DataFrame({
        "Check": [
            "Fact rows after filters",
            "Distinct order IDs",
            "Extra rows beyond distinct order IDs",
            "Missing customer name matches",
            "Unknown courier labels",
            "Delivered orders with unknown SLA outcome",
        ],
        "Count": [
            len(filtered),
            filtered["ORDER_ID"].nunique(),
            duplicate_extra_rows,
            unmatched_customer_count,
            unmatched_courier_count,
            unknown_sla_count,
        ],
    })

    a, b, c = st.columns(3)
    a.metric("Fact Rows", fmt_num(len(filtered)))
    b.metric("Unique Orders", fmt_num(filtered["ORDER_ID"].nunique()))
    c.metric("Extra Rows", fmt_num(duplicate_extra_rows))

    st.dataframe(quality, use_container_width=True, hide_index=True)
    download_csv(quality, "data_quality_report.csv", "Download data quality report")

    st.info(
        "Extra rows beyond unique order IDs are not automatically duplicates. "
        "Confirm the fact-table grain before deciding whether to remove rows."
    )

    if unknown_sla_count:
        st.warning(
            f"{unknown_sla_count:,} delivered orders have no known SLA outcome. "
            "They are excluded from the on-time and late percentage denominator."
        )

    if unmatched_customer_count or unmatched_courier_count:
        st.warning(
            "Some customer or courier dimension matches are missing. "
            "Investigate these records before relying on rankings."
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    "OrderFlow360 · E-commerce Order Fulfillment Analytics · "
    "Metrics depend on the available source data and defined business rules."
)
