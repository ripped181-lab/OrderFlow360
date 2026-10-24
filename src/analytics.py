
from pathlib import Path
import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "orderflow.duckdb"

con = duckdb.connect(str(DB_PATH), read_only=True)

try:
    print("\n===== ORDER STATUS SUMMARY =====")
    print(con.execute("""
        SELECT
            ORDER_STATUS,
            COUNT(*) AS TOTAL_ORDERS,
            ROUND(SUM(ORDER_VALUE), 2) AS TOTAL_ORDER_VALUE
        FROM FACT_ORDER_FULFILLMENT
        GROUP BY ORDER_STATUS
        ORDER BY TOTAL_ORDERS DESC
    """).df().to_string(index=False))

    print("\n===== DELIVERY SLA PERFORMANCE =====")
    print(con.execute("""
        SELECT
            COUNT(*) AS DELIVERED_ORDERS,
            COUNT(*) FILTER (WHERE SLA_MET = TRUE) AS ON_TIME_ORDERS,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE SLA_MET = TRUE)
                / NULLIF(COUNT(*), 0),
                2
            ) AS ON_TIME_PERCENTAGE
        FROM FACT_ORDER_FULFILLMENT
        WHERE ORDER_STATUS = 'Delivered'
    """).df().to_string(index=False))

    print("\n===== MONTHLY ORDER TRENDS =====")
    print(con.execute("""
        SELECT
            YEAR(ORDER_DATE_KEY) AS YEAR,
            MONTH(ORDER_DATE_KEY) AS MONTH,
            COUNT(*) AS TOTAL_ORDERS,
            ROUND(SUM(ORDER_VALUE), 2) AS REVENUE
        FROM FACT_ORDER_FULFILLMENT
        GROUP BY YEAR, MONTH
        ORDER BY YEAR, MONTH
    """).df().to_string(index=False))

finally:
    con.close()
