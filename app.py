import os
import sqlite3

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- Page Config ---
st.set_page_config(
    page_title="BTCタラレバ長者 vs 現実の地獄シミュレーター",
    page_icon="💀",
    layout="wide",
)

st.markdown(
    """
    <style>
    .big-number { font-size: 2rem; font-weight: bold; }
    .loss-text { color: #ff4b4b; font-size: 1.3rem; font-weight: bold; }
    .warning-box {
        background-color: #3d0000;
        border: 2px solid #ff4b4b;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        font-size: 1.5rem;
        color: #ff4b4b;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💰 BTCタラレバ長者 vs 現実の地獄シミュレーター 💀")
st.caption("夢（理論値）と現実（手数料・破産）を比較して、目を覚まそう。")

# --- Sidebar ---
st.sidebar.header("🔧 地獄の調整ツマミ")

# Chart scale reset button
if "chart_reset_count" not in st.session_state:
    st.session_state.chart_reset_count = 0

if st.sidebar.button("🔄 チャートの表示範囲をリセット", use_container_width=True):
    st.session_state.chart_reset_count += 1

# --- Data Fetch / Update (SQLite) ---
DB_PATH = "btc_data.db"


def download_and_save_btc_data() -> int:
    """yfinance から過去5年分の BTC-JPY データを取得し SQLite に保存する。保存行数を返す。"""
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=365 * 5)
    raw = yf.download("BTC-JPY", start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

    if raw.empty:
        return 0

    if hasattr(raw.columns, "levels"):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS btc_ohlc (
            date TEXT PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    """)
    count = 0
    for _, row in raw.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"])[:10]
        cur.execute(
            "INSERT OR REPLACE INTO btc_ohlc (date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


@st.cache_data(show_spinner="BTC価格データを読み込み中...")
def fetch_btc_data(period_days: int) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM btc_ohlc WHERE date >= ? ORDER BY date",
        conn,
        params=(cutoff,),
    )
    conn.close()
    return df


@st.cache_data(show_spinner="BTC価格データを読み込み中...")
def fetch_btc_data_by_range(start_date: str, end_date: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM btc_ohlc WHERE date >= ? AND date <= ? ORDER BY date",
        conn,
        params=(start_date, end_date),
    )
    conn.close()
    return df


# --- Sidebar: データ取得ボタン (期間設定の上) ---
db_exists = os.path.exists(DB_PATH)
if db_exists:
    _conn = sqlite3.connect(DB_PATH)
    _latest = pd.read_sql_query("SELECT MAX(date) as latest FROM btc_ohlc", _conn).iloc[0]["latest"]
    _conn.close()
    st.sidebar.caption(f"DB最終日付: {_latest or '---'}")

if st.sidebar.button("📥 過去5年分のBTCデータを取得・更新", use_container_width=True):
    with st.sidebar:
        with st.spinner("yfinance からデータ取得中..."):
            try:
                n_rows = download_and_save_btc_data()
                if n_rows > 0:
                    st.success(f"{n_rows} 件のデータを保存しました。")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("データを取得できませんでした。")
            except Exception as e:
                st.error(f"取得エラー: {e}")

st.sidebar.divider()

period_options = ["過去1年", "過去3年", "過去5年", "年月日指定"]
period_label = st.sidebar.selectbox("期間設定", period_options, index=0)

if period_label == "年月日指定":
    today = datetime.now().date()
    default_start = today - timedelta(days=365)
    col_start, col_end = st.sidebar.columns(2)
    with col_start:
        start_date = st.date_input("開始日", value=default_start, max_value=today)
    with col_end:
        end_date = st.date_input("終了日", value=today, max_value=today)
    if start_date >= end_date:
        st.sidebar.error("開始日は終了日より前に設定してください。")
        st.stop()
    custom_range = True
else:
    period_day_map = {"過去1年": 365, "過去3年": 365 * 3, "過去5年": 365 * 5}
    days = period_day_map[period_label]
    custom_range = False

initial_fund = st.sidebar.number_input(
    "初期資金 (円)", min_value=10_000, max_value=1_000_000_000, value=1_000_000, step=100_000
)

fee_rate = st.sidebar.slider(
    "手数料 Maker/Taker (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05
)

slippage_rate = st.sidebar.slider(
    "スリッページ (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.1
)

leverage = st.sidebar.slider(
    "レバレッジ倍率", min_value=1, max_value=100, value=1, step=1
)

lc_maintenance = st.sidebar.slider(
    "強制ロスカットライン (証拠金維持率 %)", min_value=10, max_value=100, value=50, step=5
)


if not os.path.exists(DB_PATH):
    st.warning("データベースがまだ作成されていません。サイドバーの「📥 過去5年分のBTCデータを取得・更新」ボタンを押してください。")
    st.stop()

try:
    if custom_range:
        df = fetch_btc_data_by_range(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    else:
        df = fetch_btc_data(days)
    if df.empty:
        st.error("BTC価格データが空です。期間を変更して再度お試しください。")
        st.stop()
except Exception as e:
    st.error(f"データ読み込みに失敗しました: {e}")
    st.stop()

# Rename columns to match expected format (SQLite returns lowercase)
df = df.rename(columns={"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date").reset_index(drop=True)

# --- Simulation ---
fee_pct = fee_rate / 100.0
slip_pct = slippage_rate / 100.0
lc_threshold = lc_maintenance / 100.0

dates = df["Date"].tolist()
highs = df["High"].values
lows = df["Low"].values
closes = df["Close"].values

n = len(df)

# A: Dream (no fees) — 毎回 initial_fund で売買、損益を累積加算
dream_assets = [float(initial_fund)]
dream_cum = 0.0
for i in range(n):
    low_price = float(lows[i])
    high_price = float(highs[i])
    if low_price <= 0:
        dream_assets.append(dream_assets[-1])
        continue
    daily_pnl = initial_fund * (high_price / low_price - 1)
    dream_cum += daily_pnl
    dream_assets.append(initial_fund + dream_cum)

# B: Reality (with fees & slippage) — 毎回 initial_fund で売買、損益を累積加算
reality_assets = [float(initial_fund)]
reality_cum = 0.0
for i in range(n):
    low_price = float(lows[i])
    high_price = float(highs[i])
    if low_price <= 0:
        reality_assets.append(reality_assets[-1])
        continue
    cost = fee_pct * 2 + slip_pct * 2  # buy + sell each incur fee & slippage
    daily_pnl = initial_fund * (high_price / low_price * (1 - cost) - 1)
    reality_cum += daily_pnl
    reality_assets.append(initial_fund + reality_cum)

# C: Hell (leveraged buy & hold)
hell_assets = [float(initial_fund)]
entry_price = float(closes[0])
liquidated = False
liquidation_idx = None

for i in range(n):
    if liquidated:
        hell_assets.append(0.0)
        continue
    current_price = float(closes[i])
    price_change_pct = (current_price - entry_price) / entry_price
    pnl_pct = price_change_pct * leverage
    current_asset = initial_fund * (1 + pnl_pct)
    margin_ratio = current_asset / initial_fund if initial_fund > 0 else 0

    if margin_ratio <= lc_threshold:
        liquidated = True
        liquidation_idx = i
        hell_assets.append(0.0)
    else:
        hell_assets.append(max(current_asset, 0))

# Prepend start date for the initial fund point
plot_dates = [dates[0] - timedelta(days=1)] + dates

# --- Daily profit (per-trade) for each scenario ---
dream_daily_pnl = [dream_assets[i + 1] - dream_assets[i] for i in range(n)]
reality_daily_pnl = [reality_assets[i + 1] - reality_assets[i] for i in range(n)]
hell_daily_pnl = [hell_assets[i + 1] - hell_assets[i] for i in range(n)]

# --- BTC Candlestick Chart + Daily P&L Line ---
import numpy as np
from plotly.subplots import make_subplots

candle_fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.6, 0.4], vertical_spacing=0.03,
)

candle_fig.add_trace(go.Candlestick(
    x=df["Date"],
    open=df["Open"],
    high=df["High"],
    low=df["Low"],
    close=df["Close"],
    increasing_line_color="#00e676",
    decreasing_line_color="#ff4b4b",
    name="BTC-JPY",
), row=1, col=1)

# Zero baseline
candle_fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)

# Helper: split dates/pnl into buy (loss) and sell (profit) points
def split_buy_sell(dates_list, pnl_list):
    buy_dates, buy_vals = [], []
    sell_dates, sell_vals = [], []
    for d, v in zip(dates_list, pnl_list):
        if v >= 0:
            sell_dates.append(d)
            sell_vals.append(v)
        else:
            buy_dates.append(d)
            buy_vals.append(v)
    return buy_dates, buy_vals, sell_dates, sell_vals

scenarios = [
    ("A", dream_daily_pnl, "#00bfff", "rgba(0,191,255,0.08)"),
    ("B", reality_daily_pnl, "#ffd700", "rgba(255,215,0,0.08)"),
    ("C", hell_daily_pnl, "#ff4b4b", "rgba(255,75,75,0.08)"),
]
scenario_names = {"A": "Dream", "B": "Reality", "C": "Hell"}

for label, pnl, color, fill_color in scenarios:
    name = scenario_names[label]
    buy_d, buy_v, sell_d, sell_v = split_buy_sell(dates, pnl)

    # Line trace
    candle_fig.add_trace(go.Scatter(
        x=dates, y=pnl,
        name=f"{label}: 日次損益 ({name})",
        line=dict(color=color, width=1.2),
        fill="tozeroy", fillcolor=fill_color,
        mode="lines",
    ), row=2, col=1)

    # Sell markers (profit days) - triangle-down
    candle_fig.add_trace(go.Scatter(
        x=sell_d, y=sell_v,
        name=f"{label}: 売 ({name})",
        mode="markers",
        marker=dict(symbol="triangle-down", size=7, color="#00e676", line=dict(width=0.5, color="white")),
        showlegend=False,
    ), row=2, col=1)

    # Buy markers (loss days) - triangle-up
    candle_fig.add_trace(go.Scatter(
        x=buy_d, y=buy_v,
        name=f"{label}: 買 ({name})",
        mode="markers",
        marker=dict(symbol="triangle-up", size=7, color="#ff4b4b", line=dict(width=0.5, color="white")),
        showlegend=False,
    ), row=2, col=1)

# Auto-scale: symmetric around zero so minus side is equally visible
all_pnl = dream_daily_pnl + reality_daily_pnl + hell_daily_pnl
pnl_arr = np.array([v for v in all_pnl if v != 0.0]) if any(v != 0.0 for v in all_pnl) else np.array([0.0])
p_low, p_high = float(np.percentile(pnl_arr, 2)), float(np.percentile(pnl_arr, 98))
y_abs_max = max(abs(p_low), abs(p_high))
y_sym = y_abs_max * 1.15  # 15% margin

candle_fig.update_layout(
    title="BTC-JPY ローソク足 + 日次売買損益",
    template="plotly_dark",
    height=700,
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
)
candle_fig.update_yaxes(title_text="BTC価格 (円)", row=1, col=1)
candle_fig.update_yaxes(
    title_text="日次損益 (円)",
    range=[-y_sym, y_sym],
    zeroline=True, zerolinecolor="gray", zerolinewidth=1.5,
    row=2, col=1,
)
candle_fig.update_xaxes(title_text="日付", row=2, col=1)

_rc = st.session_state.chart_reset_count
st.plotly_chart(candle_fig, use_container_width=True, key=f"candle_{_rc}")

# --- Asset Chart ---
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=plot_dates, y=dream_assets,
    name="A: 神の現物 (Dream)",
    line=dict(color="#00bfff", width=2),
))

fig.add_trace(go.Scatter(
    x=plot_dates, y=reality_assets,
    name="B: 現実のトレード (Reality)",
    line=dict(color="#ffd700", width=2),
))

fig.add_trace(go.Scatter(
    x=plot_dates, y=hell_assets,
    name="C: レバレッジ・ガチホ (Hell)",
    line=dict(color="#ff4b4b", width=2),
))

# Skull annotation at liquidation point
if liquidation_idx is not None:
    liq_date = dates[liquidation_idx]
    fig.add_annotation(
        x=liq_date, y=0,
        text="💀 LIQUIDATED",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#ff4b4b",
        font=dict(size=16, color="#ff4b4b"),
        bgcolor="rgba(0,0,0,0.7)",
        bordercolor="#ff4b4b",
    )

fig.update_layout(
    title="資産推移シミュレーション",
    xaxis_title="日付",
    yaxis_title="資産 (円)",
    template="plotly_dark",
    height=600,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
)

st.plotly_chart(fig, use_container_width=True, key=f"asset_{_rc}")

# --- Results ---
st.header("📊 シミュレーション結果")

final_dream = dream_assets[-1]
final_reality = reality_assets[-1]
final_hell = hell_assets[-1]

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🌈 A: 神の現物")
    st.markdown(f'<p class="big-number" style="color:#00bfff;">¥{final_dream:,.0f}</p>', unsafe_allow_html=True)
    dream_return = (final_dream / initial_fund - 1) * 100
    st.metric("リターン", f"{dream_return:+,.1f}%")

with col2:
    st.subheader("😰 B: 現実のトレード")
    st.markdown(f'<p class="big-number" style="color:#ffd700;">¥{final_reality:,.0f}</p>', unsafe_allow_html=True)
    reality_return = (final_reality / initial_fund - 1) * 100
    st.metric("リターン", f"{reality_return:+,.1f}%")

with col3:
    st.subheader("🔥 C: レバレッジ・ガチホ")
    color = "#ff4b4b" if final_hell <= 0 else "#ffd700"
    st.markdown(f'<p class="big-number" style="color:{color};">¥{final_hell:,.0f}</p>', unsafe_allow_html=True)
    if liquidated:
        st.error("💀 ロスカット済み — 退場！")
    else:
        hell_return = (final_hell / initial_fund - 1) * 100
        st.metric("リターン", f"{hell_return:+,.1f}%")

st.divider()

# Fee/slippage loss
fee_loss = final_dream - final_reality
st.markdown(
    f'<p class="loss-text">📉 手数料・スリッページによる損失総額: ¥{fee_loss:,.0f}</p>',
    unsafe_allow_html=True,
)

# Warning if in debt
if final_hell < 0:
    st.markdown(
        '<div class="warning-box">🚨 追証発生！震えて眠れ！🚨</div>',
        unsafe_allow_html=True,
    )
elif liquidated:
    st.markdown(
        '<div class="warning-box">💀 強制ロスカット発動 — 全資産消滅 💀</div>',
        unsafe_allow_html=True,
    )

# --- Pie Charts ---
st.divider()
st.header("🥧 シナリオ別 資産内訳")

pie_col1, pie_col2, pie_col3 = st.columns(3)

# A: Dream — 元本 vs 利益
dream_profit = max(final_dream - initial_fund, 0)
dream_loss = max(initial_fund - final_dream, 0)

with pie_col1:
    if final_dream >= initial_fund:
        labels_a = ["元本", "利益"]
        values_a = [initial_fund, dream_profit]
        colors_a = ["#1a5276", "#00bfff"]
    else:
        labels_a = ["残存資産", "損失"]
        values_a = [max(final_dream, 0), dream_loss]
        colors_a = ["#1a5276", "#ff4b4b"]

    pie_a = go.Figure(data=[go.Pie(
        labels=labels_a, values=values_a,
        marker=dict(colors=colors_a),
        textinfo="label+percent",
        textfont=dict(size=13),
        hole=0.4,
    )])
    pie_a.update_layout(
        title="A: 神の現物 (Dream)",
        template="plotly_dark",
        height=350,
        showlegend=False,
        annotations=[dict(text=f"¥{final_dream:,.0f}", x=0.5, y=0.5,
                          font_size=14, font_color="white", showarrow=False)],
    )
    st.plotly_chart(pie_a, use_container_width=True, key=f"pie_a_{_rc}")

# B: Reality — 元本 vs 利益 vs 手数料損失
reality_profit_gross = max(final_dream - initial_fund, 0)  # profit before fees
fee_loss_amount = max(final_dream - final_reality, 0)
reality_net_profit = max(final_reality - initial_fund, 0)
reality_net_loss = max(initial_fund - final_reality, 0)

with pie_col2:
    if final_reality >= initial_fund:
        labels_b = ["元本", "純利益", "手数料損失"]
        values_b = [initial_fund, reality_net_profit, fee_loss_amount]
        colors_b = ["#7d6608", "#ffd700", "#ff4b4b"]
    else:
        labels_b = ["残存資産", "損失", "手数料損失"]
        remaining = max(final_reality, 0)
        loss_from_trade = max(initial_fund - final_dream, 0)
        values_b = [remaining, loss_from_trade, fee_loss_amount]
        colors_b = ["#7d6608", "#cc5500", "#ff4b4b"]

    pie_b = go.Figure(data=[go.Pie(
        labels=labels_b, values=values_b,
        marker=dict(colors=colors_b),
        textinfo="label+percent",
        textfont=dict(size=13),
        hole=0.4,
    )])
    pie_b.update_layout(
        title="B: 現実のトレード (Reality)",
        template="plotly_dark",
        height=350,
        showlegend=False,
        annotations=[dict(text=f"¥{final_reality:,.0f}", x=0.5, y=0.5,
                          font_size=14, font_color="white", showarrow=False)],
    )
    st.plotly_chart(pie_b, use_container_width=True, key=f"pie_b_{_rc}")

# C: Hell — 元本 vs 利益 or 損失
hell_profit = max(final_hell - initial_fund, 0)
hell_loss = max(initial_fund - final_hell, 0)

with pie_col3:
    if liquidated:
        labels_c = ["損失 (全額)"]
        values_c = [initial_fund]
        colors_c = ["#ff4b4b"]
    elif final_hell >= initial_fund:
        labels_c = ["元本", "利益"]
        values_c = [initial_fund, hell_profit]
        colors_c = ["#5b0000", "#ff4b4b"]
    else:
        labels_c = ["残存資産", "損失"]
        values_c = [max(final_hell, 0), hell_loss]
        colors_c = ["#5b0000", "#ff4b4b"]

    pie_c = go.Figure(data=[go.Pie(
        labels=labels_c, values=values_c,
        marker=dict(colors=colors_c),
        textinfo="label+percent",
        textfont=dict(size=13),
        hole=0.4,
    )])
    pie_c.update_layout(
        title="C: レバレッジ・ガチホ (Hell)",
        template="plotly_dark",
        height=350,
        showlegend=False,
        annotations=[dict(text="¥0" if liquidated else f"¥{final_hell:,.0f}",
                          x=0.5, y=0.5, font_size=14, font_color="white",
                          showarrow=False)],
    )
    st.plotly_chart(pie_c, use_container_width=True, key=f"pie_c_{_rc}")

# --- Detail Table ---
st.divider()
st.header("📋 日次売買シミュレーション詳細")

table_rows = []
dream_cum_pnl = 0.0
reality_cum_pnl = 0.0
hell_cum_pnl = 0.0

for i in range(n):
    date_str = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i])
    close_price = float(closes[i])
    low_price = float(lows[i])
    high_price = float(highs[i])

    # --- A: Dream ---
    dream_prev = dream_assets[i]
    dream_cur = dream_assets[i + 1]
    dream_pnl = dream_cur - dream_prev
    dream_cum_pnl += dream_pnl

    # --- B: Reality (detailed breakdown) --- 毎回 initial_fund で売買
    if low_price > 0:
        gross_return = high_price / low_price
        buy_amount = float(initial_fund)
        buy_fee = buy_amount * fee_pct
        buy_slip = buy_amount * slip_pct
        sell_amount = buy_amount * gross_return
        sell_fee = sell_amount * fee_pct
        sell_slip = sell_amount * slip_pct
        spread = sell_amount - buy_amount
        reality_pnl = reality_assets[i + 1] - reality_assets[i]
    else:
        buy_fee = sell_fee = buy_slip = sell_slip = spread = reality_pnl = 0.0
    reality_cum_pnl += reality_pnl

    # --- C: Hell (leverage) ---
    hell_prev = hell_assets[i]
    hell_cur = hell_assets[i + 1]
    hell_pnl = hell_cur - hell_prev
    hell_cum_pnl += hell_pnl

    current_price_c = close_price
    if i == 0:
        price_change_pct_c = 0.0
    else:
        price_change_pct_c = (current_price_c - entry_price) / entry_price * 100
    pnl_pct_c = price_change_pct_c * leverage
    margin_ratio_c = (hell_cur / initial_fund * 100) if initial_fund > 0 and hell_cur > 0 else 0.0
    lev_status = "💀 ロスカット" if (liquidation_idx is not None and i >= liquidation_idx) else "正常"

    table_rows.append({
        "日付": date_str,
        "終値 (円)": f"{close_price:,.0f}",
        "買値=安値 (円)": f"{low_price:,.0f}",
        "売値=高値 (円)": f"{high_price:,.0f}",
        "売買差額 (円)": f"{spread:,.0f}",
        "買い手数料 (円)": f"{buy_fee:,.0f}",
        "売り手数料 (円)": f"{sell_fee:,.0f}",
        "スリッページ計 (円)": f"{(buy_slip + sell_slip):,.0f}",
        "A:損益 (円)": f"{dream_pnl:+,.0f}",
        "A:損益累計 (円)": f"{dream_cum_pnl:+,.0f}",
        "B:損益 (円)": f"{reality_pnl:+,.0f}",
        "B:損益累計 (円)": f"{reality_cum_pnl:+,.0f}",
        "C:損益 (円)": f"{hell_pnl:+,.0f}",
        "C:損益累計 (円)": f"{hell_cum_pnl:+,.0f}",
        "C:変動率": f"{pnl_pct_c:+,.2f}%",
        "C:証拠金維持率": f"{margin_ratio_c:,.1f}%",
        "C:状態": lev_status,
    })

detail_df = pd.DataFrame(table_rows)

st.dataframe(
    detail_df,
    use_container_width=True,
    height=500,
)

st.divider()
st.caption("※ このシミュレーションは過去のBTC-JPY価格データに基づく理論値です。実際の取引結果を保証するものではありません。")
