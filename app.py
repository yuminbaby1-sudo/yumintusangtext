import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI 族群動能與量化操盤系統", layout="wide", initial_sidebar_state="expanded")

# --- 時代尖端主流族群分類池 (近 50 檔關鍵人氣指標標的) ---
SECTOR_MAP = {
    "PCB / 載板 / CCL": {
        "台光電 (2383)": "2383.TW", "欣興 (3037)": "3037.TW", 
        "金像電 (2368)": "2368.TW", "台燿 (6274)": "6274.TW", "景碩 (3189)": "3189.TW"
    },
    "記憶體 / 模組": {
        "南亞科 (2408)": "2408.TW", "華邦電 (2344)": "2344.TW", 
        "群聯 (8299)": "8299.TWO", "威剛 (3260)": "3260.TWO", "十銓 (4967)": "4967.TW"
    },
    "CPO 矽光子 / 光通訊": {
        "聯鈞 (3450)": "3450.TW", "上詮 (3363)": "3363.TWO", 
        "聯亞 (3081)": "3081.TWO", "華星光 (4979)": "4979.TWO", "光聖 (6442)": "6442.TW"
    },
    "散熱模組 (水冷/液冷)": {
        "奇鋐 (3017)": "3017.TW", "雙鴻 (3324)": "3324.TW", 
        "高力 (8996)": "8996.TW", "健策 (3653)": "3653.TW"
    },
    "AI 伺服器 & 組裝": {
        "廣達 (2382)": "2382.TW", "緯創 (3231)": "3231.TW", 
        "技嘉 (2376)": "2376.TW", "緯穎 (6669)": "6669.TW", "英業達 (2356)": "2356.TW"
    },
    "重電 / 綠能電網": {
        "華城 (1519)": "1519.TW", "士電 (1503)": "1503.TW", 
        "中興電 (1513)": "1513.TW", "亞力 (1514)": "1514.TW"
    },
    "機器人 / 自動化": {
        "所羅門 (2359)": "2359.TW", "和碩 (4938)": "4938.TW", 
        "昆盈 (2365)": "2365.TW", "廣明 (6188)": "6188.TWO"
    },
    "CoWoS 設備 / 先進封裝": {
        "辛耘 (3583)": "3583.TW", "弘塑 (3131)": "3131.TWO", 
        "萬潤 (6187)": "6187.TWO", "均豪 (5443)": "5443.TWO"
    },
    "ASIC / 矽智財 / IC設計": {
        "世芯-KY (3661)": "3661.TW", "創意 (3443)": "3443.TW", 
        "智原 (3035)": "3035.TW", "聯發科 (2454)": "2454.TW"
    },
    "核心權值 & 航運指標": {
        "台積電 (2330)": "2330.TW", "鴻海 (2317)": "2317.TW", 
        "台達電 (2308)": "2308.TW", "長榮 (2603)": "2603.TW", "陽明 (2609)": "2609.TW"
    }
}

ALL_STOCKS = {}
STOCK_TO_SECTOR = {}
for sec, stk_dict in SECTOR_MAP.items():
    for name, code in stk_dict.items():
        ALL_STOCKS[name] = code
        STOCK_TO_SECTOR[name] = sec

# --- 高階技術指標計算函式 ---
def calculate_indicators(df):
    df = df.copy()
    # 均線
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    # 布林通道與擠壓 (VCP 波動收縮特徵)
    std20 = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # ATR (真實波動幅度)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()

    # OBV (能量潮指標)
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(10).mean()

    # KD (9, 3, 3)
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
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

# --- 大盤基準指數與環境濾網 ---
@st.cache_data(ttl=600)
def get_benchmark_data():
    bm = yf.download("^TWII", period="6mo", progress=False)
    if hasattr(bm.columns, 'levels') and len(bm.columns.levels) > 1:
        bm.columns = bm.columns.get_level_values(0)
    if bm.empty:
        bm = yf.download("0050.TW", period="6mo", progress=False)
        if hasattr(bm.columns, 'levels') and len(bm.columns.levels) > 1:
            bm.columns = bm.columns.get_level_values(0)
    return bm

benchmark_df = get_benchmark_data()
bm_trend = "中性整理"
if not benchmark_df.empty:
    bm_c = benchmark_df['Close'].iloc[-1]
    bm_ma20 = benchmark_df['Close'].rolling(20).mean().iloc[-1]
    bm_ma60 = benchmark_df['Close'].rolling(60).mean().iloc[-1]
    if bm_c > bm_ma20 > bm_ma60:
        bm_trend = "🟢 多頭主升環境 (族群飆股順風推進，勝率最高)"
    elif bm_c < bm_ma20 and bm_c < bm_ma60:
        bm_trend = "🔴 空頭防守環境 (大盤下彎，嚴格控制部位或多觀望)"
    else:
        bm_trend = "🟡 震盪整理環境 (指數平淡，資金專攻強勢題材族群)"

# --- 頁籤切換 ---
tab_daily, tab_rank, tab_detail = st.tabs([
    "🎯 今日最佳現貨做多標的", 
    "🔥 族群熱度與全體評分榜", 
    "🔍 個股多維深入技術診斷"
])

# =========================================================
# 分頁 1：今日推薦 (大數據精選＋停損停利)
# =========================================================
with tab_daily:
    st.header("🎯 尖端族群量化掃描：今日精選現貨做多標的")
    st.info(f"當前大盤架構：**{bm_trend}**")

    if st.button("🚀 啟動 10 大主流族群大數據動能掃描", type="primary"):
        with st.spinner("正在對 PCB、記憶體、CPO、散熱、AI、重電等指標股進行五維加權計算..."):
            all_tickers = list(ALL_STOCKS.values())
            # 批次平行抓取所有標的
            raw_data = yf.download(all_tickers, period="6mo", group_by='ticker', threads=True, progress=False)

            bm_ret_20d = 0.0
            if len(benchmark_df) >= 20:
                bm_ret_20d = (benchmark_df['Close'].iloc[-1] - benchmark_df['Close'].iloc[-20]) / benchmark_df['Close'].iloc[-20] * 100

            results = []
            sector_scores = {sec: [] for sec in SECTOR_MAP.keys()}

            for name, code in ALL_STOCKS.items():
                try:
                    df = raw_data[code].dropna() if code in raw_data else pd.DataFrame()
                    if len(df) < 60:
                        continue
                    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                        df.columns = df.columns.get_level_values(0)

                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    prev = df.iloc[-2]
                    sector_name = STOCK_TO_SECTOR[name]

                    # 1. 趨勢與架構 (30%)
                    score_trend = 0
                    if latest['Close'] > latest['MA20'] > latest['MA60']:
                        score_trend += 15
                    if latest['MA20'] > df['MA20'].iloc[-5]:
                        score_trend += 5
                    half_yr_high = df['High'].tail(120).max()
                    if (half_yr_high - latest['Close']) / half_yr_high <= 0.15:
                        score_trend += 10

                    # 2. 相對強弱 RS vs 大盤 (25%)
                    stock_ret_20d = (latest['Close'] - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100
                    rs_alpha = stock_ret_20d - bm_ret_20d
                    score_rs = 0
                    if rs_alpha > 8.0: score_rs = 25
                    elif rs_alpha > 3.0: score_rs = 18
                    elif rs_alpha > 0: score_rs = 10

                    # 3. 威科夫量價與吸籌 (20%)
                    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
                    score_vol = 0
                    if vol_ratio >= 1.4 and latest['Close'] > latest['Open']: score_vol += 12
                    elif vol_ratio >= 1.1 and latest['Close'] > latest['Open']: score_vol += 7
                    if latest['OBV'] > latest['OBV_MA10']: score_vol += 8

                    # 4. VCP 波動收斂與布林擠壓 (15%)
                    score_vcp = 0
                    bw_min_recent = df['BB_Width'].tail(30).min()
                    if latest['BB_Width'] <= bw_min_recent * 1.3: score_vcp += 10
                    recent_5_amp = (df['High'].tail(5).max() - df['Low'].tail(5).min()) / latest['Close'] * 100
                    if recent_5_amp < 6.0: score_vcp += 5

                    # 5. 時機動能共振 (10%)
                    score_mom = 0
                    if 50 <= latest['K'] <= 80: score_mom += 4
                    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: score_mom += 3
                    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: score_mom += 3

                    total_score = score_trend + score_rs + score_vol + score_vcp + score_mom

                    # 風控檢驗：計算進場防守空間
                    entry_p = float(latest['Close'])
                    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
                    low_5d = float(df['Low'].tail(5).min())
                    stop_l = max(low_5d, entry_p - 1.3 * atr_v)
                    risk_pct = (entry_p - stop_l) / entry_p * 100

                    # 懲罰機制：追高過度超過 7% 者重扣 30 分
                    if risk_pct > 7.0:
                        total_score -= 30

                    final_score = max(0, total_score)
                    sector_scores[sector_name].append(final_score)

                    results.append({
                        "name": name,
                        "code": code,
                        "sector": sector_name,
                        "total_score": final_score,
                        "score_trend": score_trend,
                        "score_rs": score_rs,
                        "score_vol": score_vol,
                        "score_vcp": score_vcp,
                        "score_mom": score_mom,
                        "close": entry_p,
                        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
                        "rs_alpha": rs_alpha,
                        "vol_ratio": vol_ratio,
                        "stop_loss": stop_l,
                        "risk_pct": risk_pct,
                        "df": df
                    })
                except Exception:
                    continue

            if results:
                results.sort(key=lambda x: x['total_score'], reverse=True)
                top = results[0]

                # 計算 1.5R 與 2.5R 目標價
                risk_amt = top['close'] - top['stop_loss']
                tp_1 = top['close'] + 1.5 * risk_amt
                tp_2 = top['close'] + 2.5 * risk_amt

                # 計算族群平均分
                sector_avg = {sec: (np.mean(sc) if sc else 0) for sec, sc in sector_scores.items()}
                top_sector = max(sector_avg, key=sector_avg.get)

                st.success(f"🏆 【今日全市場做多綜合評分冠軍】：**{top['name']}** ｜ 所屬族群：**【{top['sector']}】**")
                st.caption(f"🔥 今日全市場最強資金集中族群：**【{top_sector}】** (族群平均得分：{sector_avg[top_sector]:.1f} 分)")

                # 風控展示卡
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🎯 建議現價進場點", f"{top['close']:.2f} 元", f"今日 {top['pct']:+.2f}%")
                c2.metric("🛡️ 嚴格防守停損點", f"{top['stop_loss']:.2f} 元", f"-{top['risk_pct']:.2f}%", delta_color="inverse")
                c3.metric("📈 第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-top['close'])/top['close'])*100:.2f}%")
                c4.metric("🚀 波段主力目標 (2.5R)", f"{tp_2:.2f} 元", f"+{((tp_2-top['close'])/top['close'])*100:.2f}%")

                st.markdown("---")
                st.subheader("🧠 大數據思考維度拆解 (系統為何選中它？)")
                m_t, m_r, m_v, m_vc, m_m = st.columns(5)
                m_t.metric("1. 趨勢與架構 (30%)", f"{top['score_trend']} / 30 分")
                m_r.metric("2. 相對大盤 RS (25%)", f"{top['score_rs']} / 25 分", f"Alpha {top['rs_alpha']:+.2f}%")
                m_v.metric("3. 威科夫量能 (20%)", f"{top['score_vol']} / 20 分", f"量比 {top['vol_ratio']:.2f}x")
                m_vc.metric("4. 波動收縮 VCP (15%)", f"{top['score_vcp']} / 15 分")
                m_m.metric("5. 時機動能 (10%)", f"{top['score_mom']} / 10 分")

                st.info(f"""
                **📌 操盤手作戰與風控指引：**
                * **族群效應**：該股隸屬於 **{top['sector']}**，且具有領頭羊突破姿態。
                * **相對優勢 (RS)**：近一個月超越大盤加權指數 **{top['rs_alpha']:+.2f}%**，顯現大戶抗跌吸籌強烈。
                * **進出場守則**：
                    * 買進參考價：**{top['close']:.2f} 元**。
                    * 停損底線：若收盤價跌破 **{top['stop_loss']:.2f} 元**（控制虧損在 **{top['risk_pct']:.2f}%** 內），立即嚴格執行紀律出場。
                    * 停利步驟：碰觸第一目標 **{tp_1:.2f} 元** 減碼 1/2 入袋，其餘部位將停損移至進場成本價，無風險博取波段目標 **{tp_2:.2f} 元**。
                """)

                # 繪製點位 K 線圖
                fig_top = go.Figure(data=[go.Candlestick(
                    x=top['df'].index[-45:],
                    open=top['df']['Open'][-45:],
                    high=top['df']['High'][-45:],
                    low=top['df']['Low'][-45:],
                    close=top['df']['Close'][-45:],
                    name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
                )])
                fig_top.add_hline(y=top['stop_loss'], line_dash="dash", line_color="#0da651", annotation_text=f"停損線 {top['stop_loss']:.2f}")
                fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#eb4034", annotation_text=f"第一目標 {tp_1:.2f}")
                fig_top.add_hline(y=tp_2, line_dash="dash", line_color="#f39c12", annotation_text=f"波段目標 {tp_2:.2f}")
                fig_top.update_layout(height=450, title=f"{top['name']} ({top['sector']}) 關鍵防守與目標走勢圖", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig_top, use_container_width=True)

                st.session_state['results'] = results
                st.session_state['sector_avg'] = sector_avg
            else:
                st.warning("市場目前處於深幅回檔期，無符合嚴格做多標準之標的，建議空手保護本金。")
    else:
        st.write("👉 點擊上方按鈕，系統將自動演算 PCB、記憶體、CPO、散熱等 10 大熱門族群指標股。")

# =========================================================
# 分頁 2：族群熱度與全體評分榜
# =========================================================
with tab_rank:
    st.header("🔥 時代尖端族群熱度與多因子評分全景榜")
    if 'results' in st.session_state and st.session_state['results']:
        # 顯示族群熱度排行
        st.subheader("📊 10 大尖端族群動能熱度排行")
        sec_df = pd.DataFrame([
            {"族群名稱": k, "族群平均動能分": f"{v:.1f} 分"} 
            for k, v in sorted(st.session_state['sector_avg'].items(), key=lambda x: x[1], reverse=True)
        ])
        st.dataframe(sec_df, use_container_width=True)

        st.subheader("📋 所有個股綜合評分明細")
        filter_sec = st.selectbox("依族群篩選查看", ["全部族群"] + list(SECTOR_MAP.keys()))
        
        table_rows = []
        for r in st.session_state['results']:
            if filter_sec != "全部族群" and r['sector'] != filter_sec:
                continue
            table_rows.append({
                "標的": r['name'],
                "所屬族群": r['sector'],
                "總分": r['total_score'],
                "現價": f"{r['close']:.2f}",
                "今日漲跌%": f"{r['pct']:+.2f}%",
                "相對大盤RS超額%": f"{r['rs_alpha']:+.2f}%",
                "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                "趨勢(30)": r['score_trend'],
                "RS(25)": r['score_rs'],
                "量能(20)": r['score_vol'],
                "VCP(15)": r['score_vcp'],
                "時機(10)": r['score_mom'],
                "建議停損%": f"-{r['risk_pct']:.2f}%"
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
    else:
        st.info("請先在第一分頁點擊『啟動 10 大主流族群大數據動能掃描』，數據將在此自動呈現。")

# =========================================================
# 分頁 3：個股深入技術診斷 (全功能保留)
# =========================================================
with tab_detail:
    st.sidebar.title("📈 個股技術分析控制台")
    selected_sec = st.sidebar.selectbox("快速按族群挑選", list(SECTOR_MAP.keys()))
    selected_stock = st.sidebar.selectbox("選擇要分析的標的", list(SECTOR_MAP[selected_sec].keys()))
    stock_code = SECTOR_MAP[selected_sec][selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2)
    show_ma = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖技術指標", ["KD 指標 (9,3,3)", "MACD (12,26,9)", "布林帶寬 (VCP壓縮)", "全指標展示"])

    df_d = yf.download(stock_code, period=period_map[selected_period], progress=False)
    if hasattr(df_d.columns, 'levels') and len(df_d.columns.levels) > 1:
        df_d.columns = df_d.columns.get_level_values(0)

    if not df_d.empty:
        df_d = calculate_indicators(df_d)
        latest_d = df_d.iloc[-1]
        prev_d = df_d.iloc[-2] if len(df_d) > 1 else latest_d
        p_diff = latest_d['Close'] - prev_d['Close']
        pct_diff = (p_diff / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 綜合深度技術看板 ｜ 族群：{selected_sec}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("最新收盤價", f"{latest_d['Close']:.2f} 元", f"{p_diff:+.2f} ({pct_diff:+.2f}%)")
        c2.metric("單日最高 / 最低", f"{latest_d['High']:.2f} / {latest_d['Low']:.2f}")
        c3.metric("5日均量 (Vol 5MA)", f"{int(latest_d['Vol_MA5']):,} 股")
        c4.metric("14日真實波幅 (ATR)", f"{latest_d['ATR']:.2f} 元")
        c5.metric("布林帶寬 (BandWidth)", f"{latest_d['BB_Width']:.3f}")

        # 子圖架構
        if indicator_choice == "全指標展示":
            rows, r_heights = 5, [0.44, 0.14, 0.14, 0.14, 0.14]
            sub_titles = ("K線與均線走勢", "成交量 (Volume)", "KD 指標", "MACD 指標", "布林帶寬 (波動擠壓)")
        elif indicator_choice == "布林帶寬 (VCP壓縮)":
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線走勢", "成交量", "布林帶寬 (BandWidth)")
        else:
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線走勢", "成交量", indicator_choice)

        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=r_heights, subplot_titles=sub_titles)

        # 1. K 線圖 (紅漲綠跌)
        fig.add_trace(go.Candlestick(
            x=df_d.index, open=df_d['Open'], high=df_d['High'], low=df_d['Low'], close=df_d['Close'],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        ), row=1, col=1)

        ma_colors = {'MA5': '#f39c12', 'MA10': '#9b59b6', 'MA20': '#2980b9', 'MA60': '#16a085'}
        for ma in show_ma:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

        # 2. 成交量
        vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
        fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)

        # 3. 副圖
        cur = 3
        if indicator_choice in ["KD 指標 (9,3,3)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['K'], line=dict(color='#e74c3c', width=1.5), name="K (9)"), row=cur, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['D'], line=dict(color='#3498db', width=1.5), name="D (9)"), row=cur, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="gray", row=cur, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="gray", row=cur, col=1)
            cur += 1

        if indicator_choice in ["MACD (12,26,9)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=cur, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=cur, col=1)
            hist_c = ['#eb4034' if v >= 0 else '#0da651' for v in df_d['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['MACD_Hist'], marker_color=hist_c, name="MACD柱"), row=cur, col=1)
            cur += 1

        if indicator_choice in ["布林帶寬 (VCP壓縮)", "全指標展示"]:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['BB_Width'], line=dict(color='#8e44ad', width=1.4), name="BandWidth"), row=cur, col=1)

        fig.update_layout(height=900, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📥 檢視與匯出個股數據 (CSV)"):
            st.dataframe(df_d.tail(30).sort_index(ascending=False))
            st.download_button(
                label="下載完整歷史資料 CSV",
                data=df_d.to_csv().encode('utf-8-sig'),
                file_name=f"{stock_code}_history.csv",
                mime="text/csv"
            )