import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="台股智慧操盤與精選系統", layout="wide", initial_sidebar_state="expanded")

# --- 核心高流動性選股觀察池 (覆蓋半導體、AI、重電、航運、熱門電子) ---
STOCK_POOL = {
    "台積電 (2330)": "2330.TW",
    "聯發科 (2454)": "2454.TW",
    "鴻海 (2317)": "2317.TW",
    "廣達 (2382)": "2382.TW",
    "緯創 (3231)": "3231.TW",
    "台達電 (2308)": "2308.TW",
    "長榮 (2603)": "2603.TW",
    "陽明 (2609)": "2609.TW",
    "華城 (1519)": "1519.TW",
    "士電 (1503)": "1503.TW",
    "奇鋐 (3017)": "3017.TW",
    "雙鴻 (3324)": "3324.TW",
    "世芯-KY (3661)": "3661.TW",
    "聯詠 (3034)": "3034.TW",
    "元大台灣50 (0050)": "0050.TW"
}

# --- 指標運算函式 ---
def calculate_indicators(df):
    # 均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

    # ATR (真實波動幅度，14天)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = ((df['Close'] - low_min) / (high_max - low_min + 1e-9)) * 100
    rsv = rsv.fillna(50)

    k_list, d_list = [], []
    k, d = 50.0, 50.0
    for r in rsv:
        k = (2/3) * k + (1/3) * r
        d = (2/3) * d + (1/3) * k
        k_list.append(k)
        d_list.append(d)
    df['K'] = k_list
    df['D'] = d_list

    # MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    return df

@st.cache_data(ttl=600)
def fetch_stock_data(ticker, period="6mo"):
    data = yf.download(ticker, period=period)
    if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1:
        data.columns = data.columns.get_level_values(0)
    return data

# --- 頁面頂部分頁切換 ---
tab_daily, tab_detail = st.tabs(["🎯 每日強勢做多推薦 (含停損停利)", "🔍 個股深入技術診斷看板"])

# ==========================================
# 分頁 1：每日精選做多標的 (Minervini / 趨勢動能法)
# ==========================================
with tab_daily:
    st.header("🎯 大師操盤系統：今日最佳現貨做多標的")
    st.caption("基於 Mark Minervini 趨勢模板、Stan Weinstein 階段突破與量價共振模型，全自動掃描並動態計算最佳風險報酬比。")

    if st.button("🚀 立即執行全市場動能掃描", type="primary"):
        with st.spinner("正在對股票池進行深度技術指標與量價形態分析..."):
            best_pick = None
            highest_score = -999
            scan_results = []

            for name, code in STOCK_POOL.items():
                try:
                    df = fetch_stock_data(code, period="6mo")
                    if len(df) < 60:
                        continue
                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    prev = df.iloc[-2]

                    # 1. 核心多頭濾網 (非多頭不碰)
                    is_bull = latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']
                    above_ma5 = latest['Close'] > latest['MA5']
                    if not (is_bull and above_ma5):
                        continue

                    # 2. 評分權重計算 (趨勢強度 + 量能放大 + KD/MACD動能)
                    score = 0
                    # 量能加分
                    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
                    if vol_ratio > 1.5: score += 30
                    elif vol_ratio > 1.1: score += 15
                    
                    # 漲跌動能加分
                    pct_change = (latest['Close'] - prev['Close']) / prev['Close'] * 100
                    if 1.5 <= pct_change <= 6.5: score += 25
                    elif pct_change > 6.5: score += 10 # 漲太多防追高
                    
                    # KD 多方訊號加分
                    if 50 <= latest['K'] <= 80: score += 20
                    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: score += 15 # 黃金交叉
                    
                    # MACD 紅柱加分
                    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: score += 15

                    scan_results.append({
                        "name": name,
                        "code": code,
                        "score": score,
                        "close": latest['Close'],
                        "pct": pct_change,
                        "vol_ratio": vol_ratio,
                        "atr": latest['ATR'] if not np.isnan(latest['ATR']) else latest['Close'] * 0.02,
                        "low5": df['Low'].tail(5).min(),
                        "df": df
                    })
                except Exception:
                    continue

            if scan_results:
                # 排序選出最高分冠軍
                scan_results.sort(key=lambda x: x['score'], reverse=True)
                top = scan_results[0]
                
                # 風控試算：ATR 與關鍵支撐
                entry_price = float(top['close'])
                atr_val = float(top['atr'])
                
                # 止損點設為：近5日低點 與 (進場價 - 1.5*ATR) 的較高者，但最大不超過 7%
                stop_loss = max(top['low5'], entry_price - 1.5 * atr_val)
                if (entry_price - stop_loss) / entry_price > 0.07:
                    stop_loss = entry_price * 0.93 # 嚴格單筆上限 7%
                elif stop_loss >= entry_price:
                    stop_loss = entry_price * 0.96

                risk = entry_price - stop_loss
                take_profit_1 = entry_price + 1.5 * risk  # 盈虧比 1:1.5
                take_profit_2 = entry_price + 2.5 * risk  # 盈虧比 1:2.5

                st.success(f"🏆 今日綜合評分最高做多標的：**{top['name']}** (綜合技術得分：{top['score']} 分)")

                # 風控數值展示卡
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("建議進場參考價 (現價)", f"{entry_price:.2f} 元", f"今日漲跌 {top['pct']:+.2f}%")
                c2.metric("🛡️ 嚴格防守止損價", f"{stop_loss:.2f} 元", f"-{((entry_price-stop_loss)/entry_price)*100:.2f}%", delta_color="inverse")
                c3.metric("🎯 第一止盈目標 (1.5R)", f"{take_profit_1:.2f} 元", f"+{((take_profit_1-entry_price)/entry_price)*100:.2f}%")
                c4.metric("🚀 波段止盈目標 (2.5R)", f"{take_profit_2:.2f} 元", f"+{((take_profit_2-entry_price)/entry_price)*100:.2f}%")

                st.info(f"""
                **📌 操盤手戰術指引：**
                * **進場邏輯**：均線多頭排列、成交量達 5MA 均量之 **{top['vol_ratio']:.2f} 倍**、動能指標共振向上。
                * **出場紀律**：若盤中收盤跌破 **{stop_loss:.2f} 元** 立即嚴格停損出場；若抵達第一目標價 **{take_profit_1:.2f} 元** 可先分批獲利了結 1/2，剩餘部位將停損點拉至成本價保護，挑戰波段目標 **{take_profit_2:.2f} 元**。
                """)

                # 繪製推薦標的精簡走勢圖
                fig_top = go.Figure(data=[go.Candlestick(
                    x=top['df'].index[-40:],
                    open=top['df']['Open'][-40:],
                    high=top['df']['High'][-40:],
                    low=top['df']['Low'][-40:],
                    close=top['df']['Close'][-40:],
                    name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
                )])
                # 標註停損與止盈線
                fig_top.add_hline(y=stop_loss, line_dash="dash", line_color="green", annotation_text=f"停損線 {stop_loss:.2f}")
                fig_top.add_hline(y=take_profit_1, line_dash="dash", line_color="red", annotation_text=f"第一目標 {take_profit_1:.2f}")
                fig_top.add_hline(y=take_profit_2, line_dash="dash", line_color="orange", annotation_text=f"波段目標 {take_profit_2:.2f}")
                fig_top.update_layout(height=450, title=f"{top['name']} 近期關鍵點位分佈圖", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig_top, use_container_width=True)
            else:
                st.warning("⚠️ 今日市場整體處於拉回或盤整狀態，股票池內暫無符合高勝率嚴格多頭條件的標的，建議觀望保留現金！")
    else:
        st.write("👉 點擊上方按鈕，系統將自動演算並篩選出今日最佳的一檔做多標的。")

# ==========================================
# 分頁 2：個股深入技術診斷 (保留完整技術看板)
# ==========================================
with tab_detail:
    st.sidebar.title("📈 個股診斷控制台")
    selected_stock = st.sidebar.selectbox("選擇診斷標的", list(STOCK_POOL.keys()))
    stock_code = STOCK_POOL[selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2)
    show_ma = st.sidebar.multiselect("均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖技術指標", ["KD 指標 (9,3,3)", "MACD (12,26,9)", "兩者皆顯示"])

    df_detail = fetch_stock_data(stock_code, period_map[selected_period])
    if not df_detail.empty:
        df_detail = calculate_indicators(df_detail)
        latest_d = df_detail.iloc[-1]
        prev_d = df_detail.iloc[-2] if len(df_detail) > 1 else latest_d
        p_change = latest_d['Close'] - prev_d['Close']
        pct_change_d = (p_change / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 綜合技術看板")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("收盤價", f"{latest_d['Close']:.2f} 元", f"{p_change:+.2f} ({pct_change_d:+.2f}%)")
        m2.metric("最高 / 最低", f"{latest_d['High']:.2f} / {latest_d['Low']:.2f}")
        m3.metric("5日均量 (Vol 5MA)", f"{int(latest_d['Vol_MA5']):,} 股")
        m4.metric("14日 ATR (真實波幅)", f"{latest_d['ATR']:.2f} 元")

        # 繪圖
        rows, row_heights = (4, [0.5, 0.16, 0.17, 0.17]) if indicator_choice == "兩者皆顯示" else (3, [0.55, 0.22, 0.23])
        sub_titles = ("K線與均線走勢", "成交量", "KD" if indicator_choice != "兩者皆顯示" else "KD", "MACD")
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)
        fig.add_trace(go.Candlestick(
            x=df_detail.index, open=df_detail['Open'], high=df_detail['High'], low=df_detail['Low'], close=df_detail['Close'],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        ), row=1, col=1)

        ma_colors = {'MA5': '#f39c12', 'MA10': '#9b59b6', 'MA20': '#2980b9', 'MA60': '#16a085'}
        for ma in show_ma:
            fig.add_trace(go.Scatter(x=df_detail.index, y=df_detail[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

        vol_colors = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_detail['Close'], df_detail['Open'])]
        fig.add_trace(go.Bar(x=df_detail.index, y=df_detail['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)

        curr = 3
        if indicator_choice in ["KD 指標 (9,3,3)", "兩者皆顯示"]:
            fig.add_trace(go.Scatter(x=df_detail.index, y=df_detail['K'], line=dict(color='#e74c3c', width=1.5), name="K"), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df_detail.index, y=df_detail['D'], line=dict(color='#3498db', width=1.5), name="D"), row=curr, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="gray", row=curr, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="gray", row=curr, col=1)
            curr += 1

        if indicator_choice in ["MACD (12,26,9)", "兩者皆顯示"]:
            fig.add_trace(go.Scatter(x=df_detail.index, y=df_detail['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df_detail.index, y=df_detail['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=curr, col=1)
            hist_c = ['#eb4034' if v >= 0 else '#0da651' for v in df_detail['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_detail.index, y=df_detail['MACD_Hist'], marker_color=hist_c, name="MACD柱"), row=curr, col=1)

        fig.update_layout(height=800, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)