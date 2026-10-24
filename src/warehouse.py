
from pathlib import Path
import duckdb

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DB_PATH = BASE_DIR / "data" / "orderflow.duckdb"
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"


def build_warehouse():
    # Create a persistent local DuckDB database
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    try:
        # Convert Windows paths to forward-slash paths
        orders_path = (PROCESSED_DIR / "orders_clean.csv").as_posix()
        customers_path = (PROCESSED_DIR / "customers.csv").as_posix()
        couriers_path = (PROCESSED_DIR / "couriers.csv").as_posix()

        # Create source views from curated CSV files
        con.execute(f"""
            CREATE OR REPLACE VIEW source_orders AS
            SELECT * FROM read_csv_auto('{orders_path}')
        """)

        con.execute(f"""
            CREATE OR REPLACE VIEW source_customers AS
            SELECT * FROM read_csv_auto('{customers_path}')
        """)

        con.execute(f"""
            CREATE OR REPLACE VIEW source_couriers AS
            SELECT * FROM read_csv_auto('{couriers_path}')
        """)

        print("Curated CSV files loaded as source views.")

        # Build warehouse tables using schema.sql
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        con.execute(schema_sql)

        print("Warehouse tables created.")

        # Verify table counts
        tables = [
            "DIM_CUSTOMER",
            "DIM_COURIER",
            "DIM_DATE",
            "FACT_ORDER_FULFILLMENT",
        ]

        for table in tables:
            count = con.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            print(f"{table}: {count} rows")

        # Reconcile source orders with fact table
        source_count = con.execute(
            "SELECT COUNT(*) FROM source_orders"
        ).fetchone()[0]

        fact_count = con.execute(
            "SELECT COUNT(*) FROM FACT_ORDER_FULFILLMENT"
        ).fetchone()[0]

        print(f"\nSource orders: {source_count}")
        print(f"Fact table rows: {fact_count}")
        print(
            "Reconciliation:",
            "PASS" if source_count == fact_count else "FAIL"
        )

        # Check for missing customer or courier matches
        unmatched = con.execute("""
            SELECT COUNT(*)
            FROM FACT_ORDER_FULFILLMENT
            WHERE CUSTOMER_ID IS NULL
               OR COURIER_ID IS NULL
        """).fetchone()[0]

        print(f"Orders with unmatched customer/courier: {unmatched}")
        print(f"\nDatabase saved at: {DB_PATH}")

    finally:
        con.close()


if __name__ == "__main__":
    build_warehouse()
