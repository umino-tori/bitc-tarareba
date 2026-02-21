"""BTC-JPY の過去5年分 OHLC データを yfinance から取得し SQLite3 に保存する."""

import sqlite3
from datetime import datetime, timedelta

import yfinance as yf

DB_PATH = "btc_data.db"
TABLE_NAME = "btc_ohlc"


def main():
    # 過去5年分のデータを取得
    end = datetime.now()
    start = end - timedelta(days=365 * 5)
    print(f"Downloading BTC-JPY data from {start:%Y-%m-%d} to {end:%Y-%m-%d} ...")

    df = yf.download("BTC-JPY", start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

    if df.empty:
        print("ERROR: No data downloaded.")
        return

    # Flatten multi-level columns if present
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    print(f"Downloaded {len(df)} rows.")

    # SQLite に保存
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            date TEXT PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    """)

    rows_inserted = 0
    for _, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"])[:10]
        cur.execute(
            f"INSERT OR REPLACE INTO {TABLE_NAME} (date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])),
        )
        rows_inserted += 1

    conn.commit()
    conn.close()
    print(f"Saved {rows_inserted} rows to {DB_PATH} (table: {TABLE_NAME}).")


if __name__ == "__main__":
    main()
