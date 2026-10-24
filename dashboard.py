
from pathlib import Path
import duckdb
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "orderflow.duckdb"

st.set_page_config(
    page_title="OrderFlow360",
    page_icon="📦",
    layout="wide"
)

st.title("📦 OrderFlow360")
st.subheader("E-commerce Order Fulfillment Analytics")

if not DB_PATH.exists():
    st.error("Warehouse not found. Run python src/warehouse.py first.")
    st.stop()

con = duckdb.connect(str(DB_PATH), read_only=True)

try:
    summary = con.execute("""
        SELECT
            COUNT(*) AS total_orders,
            COUNT(*) FILTER (
                WHERE ORDER_STATUS = 'Delivered'
            ) AS delivered_orders,
            ROUND(SUM(ORDER_VALUE), 2) AS total_value,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE SLA_MET = TRUE)
                / NULLIF(COUNT(*) FILTER (
                    WHERE ORDER_STATUS = 'Delivered'
                ), 0),
                2
            ) AS on_time_pct
        FROM FACT_ORDER_FULFILLMENT
    """).df().iloc[0]

    status = con.execute("""
        SELECT ORDER_STATUS, COUNT(*) AS Orders
        FROM FACT_ORDER_FULFILLMENT
        GROUP BY ORDER_STATUS
        ORDER BY Orders DESC
    """).df()

    monthly = con.execute("""
        SELECT
            DATE_TRUNC('month', ORDER_DATE_KEY) AS Month,
            COUNT(*) AS Orders,
            SUM(ORDER_VALUE) AS Revenue
        FROM FACT_ORDER_FULFILLMENT
        GROUP BY Month
        ORDER BY Month
    """).df()

    courier = con.execute("""
        SELECT
            c.COURIER_NAME,
            COUNT(*) FILTER (
                WHERE f.ORDER_STATUS = 'Delivered'
            ) AS Delivered,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE f.SLA_MET = TRUE)
                / NULLIF(COUNT(*) FILTER (
                    WHERE f.ORDER_STATUS = 'Delivered'
                ), 0),
                2
            ) AS On_Time_Pct
        FROM FACT_ORDER_FULFILLMENT f
        LEFT JOIN DIM_COURIER c
            ON f.COURIER_ID = c.COURIER_ID
        GROUP BY c.COURIER_NAME
        ORDER BY On_Time_Pct DESC NULLS LAST
    """).df()

finally:
    con.close()

# KPI cards
a, b, c, d = st.columns(4)

a.metric("Total Orders", f"{int(summary['total_orders']):,}")
b.metric("Delivered Orders", f"{int(summary['delivered_orders']):,}")
c.metric("Order Value", f"{summary['total_value']:,.0f}")
d.metric(
    "On-Time Delivery",
    f"{summary['on_time_pct']:.1f}%"
    if pd.notna(summary["on_time_pct"]) else "N/A"
)

st.divider()

# Filters
statuses = ["All"] + status["ORDER_STATUS"].tolist()
selected = st.selectbox("Filter by order status", statuses)

if selected == "All":
    filtered_status = status
else:
    filtered_status = status[status["ORDER_STATUS"] == selected]

left, right = st.columns(2)

with left:
    st.subheader("Orders by Status")
    st.bar_chart(filtered_status.set_index("ORDER_STATUS")["Orders"])

with right:
    st.subheader("Monthly Order Trend")
    st.line_chart(monthly.set_index("Month")["Orders"])

left, right = st.columns(2)

with left:
    st.subheader("Monthly Revenue")
    st.line_chart(monthly.set_index("Month")["Revenue"])

with right:
    st.subheader("Courier SLA Performance")
    st.bar_chart(courier.set_index("COURIER_NAME")["On_Time_Pct"])

st.subheader("Courier Performance Details")
st.dataframe(courier, use_container_width=True)

st.subheader("Monthly KPI Data")
st.dataframe(monthly, use_container_width=True)
