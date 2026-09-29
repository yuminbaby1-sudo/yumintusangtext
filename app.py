import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- 頁面全域設定 ---
st.set_page_config(
    page_title="AI 時代尖端量化操盤與資產風控系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 1. 時代尖端主流 20 大族群與 85 檔核心股票池
# ==============================================================================
SECTOR_MAP = {
    "CPO 矽光子 / 光通訊": {
        "聯鈞 (3450)": "3450.TW", "上詮 (3363)": "3363.TWO", "聯亞 (3081)": "3081.TWO",
        "華星光 (4979)": "4979.TWO", "光聖 (6442)": "6442.TW", "眾達-KY (4977)": "4977.TW"
    },
    "CoWoS 先進封裝 / 設備": {
        "辛耘 (3583)": "3583.TW", "弘塑 (3131)": "3131.TWO", "萬潤 (6187)": "6187.TWO",
        "均豪 (5443)": "5443.TWO", "志聖 (2467)": "2467.TW"
    },
    "散熱模組 (水冷/液冷)": {
        "奇鋐 (3017)": "3017.TW", "雙鴻 (3324)": "3324.TW", "高力 (8996)": "8996.TW",
        "健策 (3653)": "3653.TW", "尼得科超眾 (6230)": "6230.TW"
    },
    "AI 伺服器 & 組裝": {
        "廣達 (2382)": "2382.TW", "緯創 (3231)": "3231.TW", "技嘉 (2376)": "2376.TW",
        "緯穎 (6669)": "6669.TW", "英業達 (2356)": "2356.TW", "神達 (3706)": "3706.TW"
    },
    "PCB / 載板 / CCL": {
        "台光電 (2383)": "2383.TW", "欣興 (3037)": "3037.TW", "金像電 (2368)": "2368.TW",
        "台燿 (6274)": "6274.TW", "景碩 (3189)": "3189.TW", "南電 (8046)": "8046.TW"
    },
    "記憶體 / 模組 / 顆粒": {
        "南亞科 (2408)": "2408.TW", "華邦電 (2344)": "2344.TW", "群聯 (8299)": "8299.TWO",
        "威剛 (3260)": "3260.TWO", "十銓 (4967)": "4967.TW", "晶豪科 (3006)": "3006.TW"
    },
    "機器人 / 智慧自動化": {
        "所羅門 (2359)": "2359.TW", "昆盈 (2365)": "2365.TW", "廣明 (6188)": "6188.TWO",
        "和碩 (4938)": "4938.TW", "羅昇 (8374)": "8374.TW", "穎漢 (4562)": "4562.TW"
    },
    "ASIC / 矽智財 (IP)": {
        "世芯-KY (3661)": "3661.TW", "創意 (3443)": "3443.TW", "智原 (3035)": "3035.TW",
        "力旺 (3529)": "3529.TWO", "M31 (6643)": "6643.TWO"
    },
    "IC 設計 / 主流晶片": {
        "聯發科 (2454)": "2454.TW", "聯詠 (3034)": "3034.TW", "瑞昱 (2379)": "2379.TW",
        "祥碩 (5269)": "5269.TW", "信驊 (5274)": "5274.TWO"
    },
    "半導體代工與封測": {
        "台積電 (2330)": "2330.TW", "聯電 (2303)": "2303.TW", "日月光投控 (3711)": "3711.TW",
        "京元電子 (2449)": "2449.TW"
    },
    "重電 / 綠能強韌電網": {
        "華城 (1519)": "1519.TW", "士電 (1503)": "1503.TW", "中興電 (1513)": "1513.TW",
        "亞力 (1514)": "1514.TW", "大同 (2371)": "2371.TW"
    },
    "軍工防衛 / 無人機概念": {
        "雷虎 (8033)": "8033.TW", "漢翔 (2634)": "2634.TW", "駐龍 (4572)": "4572.TW",
        "亞航 (2630)": "2630.TW", "寶一 (8222)": "8222.TW"
    },
    "車用電子 / 電動車鏈": {
        "貿聯-KY (3665)": "3665.TW", "台達電 (2308)": "2308.TW", "定穎投控 (3715)": "3715.TW",
        "胡連 (6279)": "6279.TW"
    },
    "光學鏡頭 / 機器視覺": {
        "大立光 (3008)": "3008.TW", "玉晶光 (3406)": "3406.TW", "先進光 (3362)": "3362.TWO",
        "佳凌 (4976)": "4976.TW"
    },
    "半導體特用化學品": {
        "中華化 (1727)": "1727.TW", "三晃 (1721)": "1721.TW", "勝一 (1773)": "1773.TW",
        "長興 (1717)": "1717.TW"
    },
    "航運 / 貨櫃與散裝": {
        "長榮 (2603)": "2603.TW", "陽明 (2609)": "2609.TW", "萬海 (2615)": "2615.TW",
        "裕民 (2606)": "2606.TW", "新興 (2605)": "2605.TW"
    },
    "生技醫療 / CDMO": {
        "保瑞 (6472)": "6472.TW", "美時 (1795)": "1795.TW", "藥華藥 (6446)": "6446.TWO",
        "晶碩 (6491)": "6491.TW"
    },
    "鋼鐵原物料龍頭": {
        "中鋼 (2002)": "2002.TW", "大成鋼 (2027)": "2027.TW", "中鴻 (2014)": "2014.TW"
    },
    "金融內資主力盤": {
        "富邦金 (2881)": "2881.TW", "國泰金 (2882)": "2882.TW", "中信金 (2891)": "2891.TW",
        "元大金 (2885)": "2885.TW"
    },
    "核心大盤權值指標": {
        "鴻海 (2317)": "2317.TW", "元大台灣50 (0050)": "0050.TW"
    }
}

# ==============================================================================
# 2. 全套高階技術指標、量能、型態學、籌碼代理計算引擎
# ==============================================================================
def calculate_all_indicators(df):
    df = df.copy()

    # 1. 均線體系 (MA5/10/20/60)
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    # 2. 布林通道與擠壓 (BandWidth - VCP 波動壓縮判定)
    std20 = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # 3. ATR (真實波動幅度 - 風控與停損依據，14日)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()

    # 4. OBV (能量潮指標 - 威科夫吸籌)
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(10).mean()

    # 5. MFI (資金流量指標 - 量價聚合動能，14日)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    rmf = tp * df['Volume']
    pos_flow = pd.Series(np.where(tp > tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    neg_flow = pd.Series(np.where(tp < tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    mfi_ratio = pos_flow / (neg_flow + 1e-9)
    df['MFI'] = 100 - (100 / (1 + mfi_ratio))

    # 6. RSI (相對強弱指標，14日)
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 7. KD (9, 3, 3)
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

    # 8. MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']

    # 9. 籌碼集中度代理量化指標 (Chip Concentration Proxy)
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'] + 1e-9)
    df['Chip_Accumulation'] = (clv * df['Volume']).rolling(5).sum() / (df['Volume'].rolling(5).sum() + 1e-9)

    # 10. 經典 K 線型態學自動偵測
    patterns = []
    for i in range(len(df)):
        p_list = []
        if i >= 1:
            c = df['Close'].iloc[i]
            o = df['Open'].iloc[i]
            h = df['High'].iloc[i]
            l = df['Low'].iloc[i]
            prev_c = df['Close'].iloc[i-1]
            prev_o = df['Open'].iloc[i-1]
            prev_h = df['High'].iloc[i-1]

            # (A) 跳空缺口 (Breakaway Gap)
            if l > prev_h:
                p_list.append("跳空突破缺口 🚀")
            # (B) 長下影線破底翻 (Hammer / 洗盤拉回)
            body = abs(c - o)
            lower_shadow = min(c, o) - l
            if lower_shadow > body * 2.0 and lower_shadow > (h - l) * 0.5:
                p_list.append("長下影線破底翻 🔨")
            # (C) 長紅吞噬 (Bullish Engulfing)
            if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
                p_list.append("長紅吞噬反轉 💥")
            # (D) 多頭排列首度回測 20MA
            if c >= df['MA20'].iloc[i] and l <= df['MA20'].iloc[i] and df['MA20'].iloc[i] > df['MA20'].iloc[i-1]:
                p_list.append("回測月線生命線守住 🛡️")

        patterns.append(" / ".join(p_list) if p_list else "型態整理中")
    df['Candle_Pattern'] = patterns

    return df

# ==============================================================================
# 3. 大盤環境與基本面資料
# ==============================================================================
@st.cache_data(ttl=600)
def get_benchmark_data():
    bm = yf.download("^TWII", period="1y", progress=False)
    if hasattr(bm.columns, 'levels') and len(bm.columns.levels) > 1:
        bm.columns = bm.columns.get_level_values(0)
    if bm.empty:
        bm = yf.download("0050.TW", period="1y", progress=False)
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
        bm_trend = "🟢 多頭主升環境 (族群輪動強勁，做多勝率高)"
    elif bm_c < bm_ma20 and bm_c < bm_ma60:
        bm_trend = "🔴 空頭防守環境 (大盤下彎，嚴格控制總部位)"
    else:
        bm_trend = "🟡 區間震盪環境 (指數平淡，資金專攻強勢題材股)"

@st.cache_data(ttl=600)
def get_fundamental_and_news(ticker):
    stock_obj = yf.Ticker(ticker)
    info = stock_obj.info or {}
    news = stock_obj.news or []
    return {
        "rev_growth": info.get('revenueGrowth', None) * 100 if info.get('revenueGrowth', None) else None,
        "earn_growth": info.get('earningsGrowth', None) * 100 if info.get('earningsGrowth', None) else None,
        "target_price": info.get('targetMeanPrice', None),
        "forward_pe": info.get('forwardPE', None),
        "news": news[:5]
    }

# ==============================================================================
# 4. 核心打分引擎 (技術 75% + 籌碼 20% + 基本面 5%)
# ==============================================================================
def score_single_stock(df_slice, bm_slice):
    if len(df_slice) < 60:
        return None
    latest = df_slice.iloc[-1]
    prev = df_slice.iloc[-2]

    # 1. 趨勢結構 (20 分)
    s_trend = 0
    if latest['Close'] > latest['MA20'] > latest['MA60']: s_trend += 10
    if latest['MA20'] > df_slice['MA20'].iloc[-5]: s_trend += 4
    half_yr_high = df_slice['High'].tail(120).max()
    if (half_yr_high - latest['Close']) / half_yr_high <= 0.15: s_trend += 6

    # 2. RS 相對強弱 vs 加權指數 (15 分)
    stock_ret20 = (latest['Close'] - df_slice['Close'].iloc[-20]) / df_slice['Close'].iloc[-20] * 100
    bm_ret20 = 0.0
    if len(bm_slice) >= 20:
        bm_ret20 = (bm_slice['Close'].iloc[-1] - bm_slice['Close'].iloc[-20]) / bm_slice['Close'].iloc[-20] * 100
    rs_alpha = stock_ret20 - bm_ret20
    s_rs = 0
    if rs_alpha > 8.0: s_rs = 15
    elif rs_alpha > 3.0: s_rs = 10
    elif rs_alpha > 0: s_rs = 5

    # 3. 量能與 MFI 資金流 (15 分)
    vol_ratio = latest['Volume'] / (latest['Vol_MA5'] + 1e-9)
    s_vol = 0
    if vol_ratio >= 1.4 and latest['Close'] > latest['Open']: s_vol += 6
    elif vol_ratio >= 1.1 and latest['Close'] > latest['Open']: s_vol += 3
    if latest['OBV'] > latest['OBV_MA10']: s_vol += 4
    if 50 <= latest['MFI'] <= 75: s_vol += 5
    elif latest['MFI'] > 75: s_vol += 2

    # 4. VCP 波動收縮與布林擠壓 (15 分)
    s_vcp = 0
    bw_min = df_slice['BB_Width'].tail(30).min()
    if latest['BB_Width'] <= bw_min * 1.3: s_vcp += 10
    recent_5_amp = (df_slice['High'].tail(5).max() - df_slice['Low'].tail(5).min()) / latest['Close'] * 100
    if recent_5_amp < 6.0: s_vcp += 5

    # 5. 擺盪指標時機共振 (10 分)
    s_mom = 0
    if 50 <= latest['K'] <= 80: s_mom += 3
    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: s_mom += 2
    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: s_mom += 3
    if 52 <= latest['RSI'] <= 68: s_mom += 2

    # 6. 籌碼集中度代理 (20 分)
    s_chip = 0
    chip_acc = latest['Chip_Accumulation']
    if chip_acc > 0.35: s_chip = 20
    elif chip_acc > 0.15: s_chip = 14
    elif chip_acc > 0: s_chip = 8

    tech_and_chip = s_trend + s_rs + s_vol + s_vcp + s_mom + s_chip

    # 風控防守試算 (ATR 停損)
    entry_p = float(latest['Close'])
    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
    low_5d = float(df_slice['Low'].tail(5).min())
    stop_l = max(low_5d, entry_p - 1.3 * atr_v)
    risk_pct = (entry_p - stop_l) / entry_p * 100

    # 追高懲罰 (單筆停損需求大於 7% 扣 30 分)
    if risk_pct > 7.0:
        tech_and_chip -= 30

    return {
        "tech_chip_score": max(0, tech_and_chip),
        "score_trend": s_trend,
        "score_rs": s_rs,
        "score_vol": s_vol,
        "score_vcp": s_vcp,
        "score_mom": s_mom,
        "score_chip": s_chip,
        "close": entry_p,
        "pct": (latest['Close'] - prev['Close']) / prev['Close'] * 100,
        "rs_alpha": rs_alpha,
        "vol_ratio": vol_ratio,
        "mfi": latest['MFI'],
        "rsi": latest['RSI'],
        "chip_acc": chip_acc,
        "pattern": latest['Candle_Pattern'],
        "ma10": float(latest['MA10']),
        "ma20": float(latest['MA20']),
        "stop_loss": stop_l,
        "risk_pct": risk_pct
    }

# ==============================================================================
# 5. 側邊欄全域控制面板：資金規模與自選外掛槽
# ==============================================================================
st.sidebar.title("🎛️ 操盤控制台")

# 部位規模計算器參數
st.sidebar.subheader("💰 實戰部位規模計算參數")
user_capital = st.sidebar.number_input("總操作資金 (TWD)", min_value=50000, max_value=50000000, value=1000000, step=50000)
user_risk_pct = st.sidebar.slider("單筆最大承受風險比例 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

st.sidebar.markdown("---")
# 動態自選股外掛槽
st.sidebar.subheader("➕ 動態加入自選觀察股")
custom_input = st.sidebar.text_input("輸入自選代碼 (例: 3533.TW 或 6274.TWO)", "")
if custom_input:
    custom_code = custom_input.strip().upper()
    if not (custom_code.endswith(".TW") or custom_code.endswith(".TWO")):
        st.sidebar.error("台股上市公司請加上 .TW，上櫃請加 .TWO")
    else:
        st.sidebar.success(f"已排入掃描池：{custom_code}")

# 組合最終掃描股票池
CURRENT_STOCKS = {}
CURRENT_STOCK_TO_SECTOR = {}
for sec, stk_dict in SECTOR_MAP.items():
    for name, code in stk_dict.items():
        CURRENT_STOCKS[name] = code
        CURRENT_STOCK_TO_SECTOR[name] = sec

if custom_input and (custom_input.strip().upper().endswith(".TW") or custom_input.strip().upper().endswith(".TWO")):
    c_code = custom_input.strip().upper()
    c_name = f"自選標的 ({c_code})"
    CURRENT_STOCKS[c_name] = c_code
    CURRENT_STOCK_TO_SECTOR[c_name] = "自選觀察族群"

# ==============================================================================
# 6. 主要功能分頁配置
# ==============================================================================
tab_daily, tab_backtest, tab_rank, tab_detail, tab_manual = st.tabs([
    "🎯 今日做多首選 (戰報+部位規模+情境試算)", 
    "📈 滾動回測與勝率戰報 (系統進化)", 
    "🔥 族群熱度與市場內部寬度榜", 
    "🔍 個股多維深度技術診斷",
    "📚 操盤大師實戰守則"
])

# ==============================================================================
# Tab 1：今日推薦 (含部位規模計算 + 實體台幣損益情境試算 + 型態雷達)
# ==============================================================================
with tab_daily:
    st.header("🎯 世紀飆股雷達：今日最佳現貨做多標的")
    st.info(f"大盤加權指數總體環境：**{bm_trend}**")

    if st.button("🚀 啟動 20 大族群大數據全指標掃描", type="primary"):
        with st.spinner("正在進行全指標股多維加權運算 (技術75% + 籌碼20% + 基本面5%)..."):
            all_tickers = list(CURRENT_STOCKS.values())
            raw_data = yf.download(all_tickers, period="1y", group_by='ticker', threads=True, progress=False)

            results = []
            above_ma20_count = 0
            valid_stock_count = 0

            for name, code in CURRENT_STOCKS.items():
                try:
                    df = raw_data[code].dropna() if code in raw_data else pd.DataFrame()
                    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                        df.columns = df.columns.get_level_values(0)
                    df = calculate_all_indicators(df)
                    
                    if len(df) >= 60:
                        valid_stock_count += 1
                        if df['Close'].iloc[-1] > df['MA20'].iloc[-1]:
                            above_ma20_count += 1

                    score_res = score_single_stock(df, benchmark_df)
                    if score_res:
                        score_res['name'] = name
                        score_res['code'] = code
                        score_res['sector'] = CURRENT_STOCK_TO_SECTOR[name]
                        score_res['df'] = df
                        results.append(score_res)
                except Exception:
                    continue

            # 市場內部寬度計算 (Market Breadth)
            breadth_ratio = (above_ma20_count / valid_stock_count * 100) if valid_stock_count > 0 else 50.0
            st.session_state['breadth_ratio'] = breadth_ratio

            if results:
                results.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                top_candidates = results[:8]

                for cand in top_candidates:
                    f_data = get_fundamental_and_news(cand['code'])
                    cand['fundamental'] = f_data
                    score_fund = 0
                    if f_data['rev_growth'] is not None and f_data['rev_growth'] > 15.0: score_fund += 3
                    elif f_data['rev_growth'] is not None and f_data['rev_growth'] > 0: score_fund += 1.5
                    if f_data['target_price'] is not None and f_data['target_price'] > cand['close']:
                        upside = (f_data['target_price'] - cand['close']) / cand['close'] * 100
                        cand['upside'] = upside
                        if upside >= 20.0: score_fund += 2
                        elif upside > 0: score_fund += 1
                    else:
                        cand['upside'] = 0.0
                    cand['score_fund'] = score_fund
                    cand['total_score'] = cand['tech_chip_score'] + score_fund

                top_candidates.sort(key=lambda x: x['total_score'], reverse=True)
                top = top_candidates[0]

                st.session_state['top_pick'] = top
                st.session_state['daily_results'] = results
                st.session_state['raw_data'] = raw_data
            else:
                st.warning("市場正處於劇烈下修期，無符合標準之標的，請嚴格空手觀望。")

    # 顯示市場內部寬度體檢
    if 'breadth_ratio' in st.session_state:
        b_val = st.session_state['breadth_ratio']
        if b_val >= 65:
            st.success(f"🌊 **市場內部健康度：極佳 ({b_val:.1f}% 股票站上月線)** — 族群普漲發動，做多順風順水！")
        elif b_val <= 35:
            st.error(f"⚠️ **市場內部健康度：嚴峻 ({b_val:.1f}% 股票站上月線)** — 盤面偏弱，嚴格控制部位或保守觀望！")
        else:
            st.info(f"⚖️ **市場內部健康度：中性整理 ({b_val:.1f}% 股票站上月線)** — 個股表現分化，僅挑選最強指標股。")

    if 'top_pick' in st.session_state:
        top = st.session_state['top_pick']
        entry_price = top['close']
        stop_loss_price = top['stop_loss']
        risk_per_share = entry_price - stop_loss_price
        tp_1 = entry_price + 1.5 * risk_per_share
        tp_2 = entry_price + 2.5 * risk_per_share

        st.success(f"🏆 【今日做多首選標的】：**{top['name']}** ｜ 所屬族群：**【{top['sector']}】** (綜合得分：{top['total_score']:.1f} 分)")
        st.write(f"🏷️ **型態特徵標籤**：`{top['pattern']}`")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🎯 建議現價進場點", f"{entry_price:.2f} 元", f"今日漲跌 {top['pct']:+.2f}%")
        c2.metric("🛡️ 初始防守停損點", f"{stop_loss_price:.2f} 元", f"-{top['risk_pct']:.2f}%", delta_color="inverse")
        c3.metric("🎯 第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-entry_price)/entry_price)*100:.2f}%")
        c4.metric("🚀 波段移動防守線 (10MA)", f"{top['ma10']:.2f} 元", "主升段沿此均線抱牢")

        # ----------------------------------------------------------------------
        # 部位規模與實體台幣損益情境試算 (P&L Dollar Simulator)
        # ----------------------------------------------------------------------
        st.markdown("---")
        st.subheader("💵 操盤手資金規模與台幣損益情境模擬")
        max_risk_amount = user_capital * (user_risk_pct / 100.0)
        shares_to_buy = int(max_risk_amount / (risk_per_share + 1e-9))
        lots_to_buy = shares_to_buy // 1000
        odd_shares = shares_to_buy % 1000
        total_cost = shares_to_buy * entry_price
        capital_allocation_pct = (total_cost / user_capital) * 100

        # 計算三種情境下的具體新台幣盈虧
        dollar_loss = - (risk_per_share * shares_to_buy)
        dollar_profit_1 = (tp_1 - entry_price) * shares_to_buy
        dollar_profit_2 = (tp_2 - entry_price) * shares_to_buy

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("單筆最大承受損失", f"NT$ {int(max_risk_amount):,} 元", f"佔總本金 {user_risk_pct}%")
        pc2.metric("建議買進規模", f"{lots_to_buy} 張 {odd_shares} 股", f"合計 {shares_to_buy:,} 股")
        pc3.metric("預計動用交割款", f"NT$ {int(total_cost):,} 元", f"佔總資金 {capital_allocation_pct:.1f}%")
        pc4.metric("每股承擔風險空間", f"{risk_per_share:.2f} 元", f"跌破 {stop_loss_price:.2f} 離場")

        st.markdown("#### 🎯 具體台幣獲利 / 虧損情境表 (下單前心理預期)：")
        sim_col1, sim_col2, sim_col3 = st.columns(3)
        sim_col1.error(f"❌ **不幸觸發停損 ({stop_loss_price:.2f} 元)**\n\n實質虧損金額：**NT$ {int(dollar_loss):,} 元**")
        sim_col2.success(f"🎯 **達成第一止盈 (+1.5R / {tp_1:.2f} 元)**\n\n預期入袋獲利：**+NT$ {int(dollar_profit_1):,} 元**")
        sim_col3.info(f"🚀 **達成波段目標 (+2.5R / {tp_2:.2f} 元)**\n\n預期狂飆獲利：**+NT$ {int(dollar_profit_2):,} 元**")

        # ----------------------------------------------------------------------
        # 完整進出場與移動停利作戰手冊
        # ----------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 操盤手進出場執行作戰手冊")
        
        col_pb1, col_pb2 = st.columns(2)
        with col_pb1:
            st.markdown(f"""
            #### 🟢 進場與防守紀律
            1. **進場時機**：
               * 於開盤後觀察，股價在 **{entry_price:.2f} 元** 附近量能溫和時分批切入。
               * 若開盤直接跳空暴漲超過 +5% 則放棄追價，等待盤中回測 5MA 不破再介入。
            2. **硬性初始停損 (Hard Stop)**：
               * 只要盤中收盤價跌破 **{stop_loss_price:.2f} 元**（虧損約 -{top['risk_pct']:.2f}%），無條件全數停損，單筆實質損失絕不超過 **NT$ {int(max_risk_amount):,} 元**。
            3. **時間停損 (Time Stop)**：
               * 進場後若 **5 個交易日** 內皆未創高且成交量萎縮低於 5MA，代表主力發動失敗，不論微賺微賠一律平倉轉移資金。
            """)
        with col_pb2:
            st.markdown(f"""
            #### 🔴 三階段階梯式移動停利 (Trailing Stop)
            1. **第一階段（獲利鎖定＋保本）**：
               * 當股價上漲觸碰 **{tp_1:.2f} 元**（+1.5R 盈虧比），市價賣出 **1/2 部位** 獲利落袋（先賺取約 +NT$ {int(dollar_profit_1/2):,} 元）。
               * **關鍵動作**：同時將剩餘 1/2 部位的停損點上調至 **買進成本價 ({entry_price:.2f} 元)**，達成該筆交易「絕對零風險」。
            2. **第二階段（短線主升段移動追蹤）**：
               * 獲利脫離成本超過 15% 後，改以 **10 日均線 (現為 {top['ma10']:.2f} 元)** 作為動態停利線。
               * 每日隨均線上移調整，收盤不破 10MA 絕不出清。
            3. **第三階段（十倍世紀飆股大波段）**：
               * 若族群持續噴發，改以 **20 日月線 (現為 {top['ma20']:.2f} 元)** 作為最後波段底線，完整吃下整段翻倍行情。
            """)

        # ----------------------------------------------------------------------
        # 六維度思考拆解
        # ----------------------------------------------------------------------
        st.markdown("---")
        st.subheader("🧠 系統為何選中它？大數據六維度加權思考拆解")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("1. 趨勢結構 (20%)", f"{top['score_trend']} / 20 分")
        m2.metric("2. 籌碼集中度 (20%)", f"{top['score_chip']} / 20 分", f"推力 {top['chip_acc']:.2f}")
        m3.metric("3. 相對大盤 RS (15%)", f"{top['score_rs']} / 15 分", f"Alpha {top['rs_alpha']:+.2f}%")
        m4.metric("4. 量能與 MFI (15%)", f"{top['score_vol']} / 15 分", f"MFI: {top['mfi']:.1f}")
        m5.metric("5. VCP 與時機 (25%)", f"{top['score_vcp'] + top['score_mom']} / 25 分")
        m6.metric("6. 基本面催化 (5%)", f"{top['score_fund']:.1f} / 5 分")

        f = top['fundamental']
        fc1, fc2, fc3 = st.columns(3)
        fc1.write(f"**營收年增率 (YoY)**：{f['rev_growth']:+.1f}%" if f['rev_growth'] else "**營收年增率**：資料更新中")
        fc2.write(f"**法人目標價**：{f['target_price']:.1f} 元 (空間 {top.get('upside',0):+.1f}%)" if f['target_price'] else "**法人目標價**：暫無公開報告")
        fc3.write(f"**前瞻本益比**：{f['forward_pe']:.1f} 倍" if f['forward_pe'] else "**前瞻本益比**：N/A")

        if f['news']:
            st.write("**🔥 最新市場利多動態：**")
            for nw in f['news']:
                st.markdown(f"* 🔗 [{nw.get('title', '新聞')}]({nw.get('link', '#')}) — *{nw.get('publisher', '')}*")

        # ----------------------------------------------------------------------
        # 視覺化點位走勢圖
        # ----------------------------------------------------------------------
        fig_top = go.Figure(data=[go.Candlestick(
            x=top['df'].index[-45:],
            open=top['df']['Open'][-45:], high=top['df']['High'][-45:],
            low=top['df']['Low'][-45:], close=top['df']['Close'][-45:],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        )])
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA10'][-45:], line=dict(color='#f39c12', width=1.5), name="10MA (移動停利)"))
        fig_top.add_trace(go.Scatter(x=top['df'].index[-45:], y=top['df']['MA20'][-45:], line=dict(color='#2980b9', width=1.5), name="20MA (生命線)"))
        fig_top.add_hline(y=stop_loss_price, line_dash="dash", line_color="#0da651", annotation_text=f"停損線 {stop_loss_price:.2f}")
        fig_top.add_hline(y=tp_1, line_dash="dash", line_color="#eb4034", annotation_text=f"第一目標 {tp_1:.2f}")
        fig_top.update_layout(height=450, title=f"{top['name']} ({top['sector']}) 走勢與動態移動停利圖", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_top, use_container_width=True)

# =========================================================
# Tab 2：滾動回測與勝率戰報 (系統自我進化引擎)
# =========================================================
with tab_backtest:
    st.header("📈 歷史營業日滾動回測與勝率戰報")
    st.caption("回溯過去 45 個營業日，檢驗系統在實戰中是否有真本事，並針對失敗單進行歸因修正。")

    backtest_days = st.slider("回測交易日天數 (營業日)", min_value=20, max_value=60, value=35)
    max_holding = st.slider("最長持股天數 (若未達止盈/止損)", min_value=5, max_value=20, value=12)

    if st.button("🔄 執行歷史營業日滾動回測與歸因檢討", type="primary"):
        with st.spinner(f"正在對過去 {backtest_days} 個營業日進行逐日選股回測與實戰損益追蹤..."):
            all_tickers = list(CURRENT_STOCKS.values())
            raw_data = st.session_state.get('raw_data', None)
            if raw_data is None:
                raw_data = yf.download(all_tickers, period="1y", group_by='ticker', threads=True, progress=False)
                st.session_state['raw_data'] = raw_data

            stock_dfs = {}
            for name, code in CURRENT_STOCKS.items():
                if code in raw_data:
                    df_item = raw_data[code].dropna()
                    if hasattr(df_item.columns, 'levels') and len(df_item.columns.levels) > 1:
                        df_item.columns = df_item.columns.get_level_values(0)
                    if len(df_item) > 80:
                        stock_dfs[name] = calculate_all_indicators(df_item)

            sample_df = list(stock_dfs.values())[0]
            dates = sample_df.index[-backtest_days-max_holding:-max_holding]

            trade_log = []
            for d in dates:
                bm_slice = benchmark_df.loc[:d]
                day_scores = []
                for name, df_item in stock_dfs.items():
                    if d in df_item.index:
                        idx_pos = df_item.index.get_loc(d)
                        if idx_pos >= 60:
                            df_slice = df_item.iloc[:idx_pos+1]
                            score_res = score_single_stock(df_slice, bm_slice)
                            if score_res and score_res['tech_chip_score'] >= 55:
                                score_res['name'] = name
                                score_res['df'] = df_item
                                score_res['entry_date'] = d
                                day_scores.append(score_res)

                if not day_scores:
                    continue

                day_scores.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                pick = day_scores[0]

                entry_date = pick['entry_date']
                full_df = pick['df']
                future_idx = full_df.index.get_loc(entry_date)
                future_window = full_df.iloc[future_idx+1 : future_idx+1+max_holding]

                if future_window.empty:
                    continue

                entry_p = pick['close']
                stop_l = pick['stop_loss']
                risk = entry_p - stop_l
                tp_1 = entry_p + 1.5 * risk

                trade_status = "持倉期滿平倉"
                exit_price = future_window['Close'].iloc[-1]
                exit_date = future_window.index[-1]
                holding_days = len(future_window)

                for f_day, row in future_window.iterrows():
                    if row['Low'] <= stop_l:
                        trade_status = "觸發止損 ❌"
                        exit_price = stop_l
                        exit_date = f_day
                        holding_days = future_window.index.get_loc(f_day) + 1
                        break
                    elif row['High'] >= tp_1:
                        trade_status = "觸發止盈 🎯"
                        exit_price = tp_1
                        exit_date = f_day
                        holding_days = future_window.index.get_loc(f_day) + 1
                        break

                pnl_pct = (exit_price - entry_p) / entry_p * 100
                is_win = (pnl_pct > 0)

                fail_reason = "--"
                if not is_win:
                    if len(bm_slice) >= 20 and bm_slice['Close'].iloc[-1] < bm_slice['Close'].rolling(20).mean().iloc[-1]:
                        fail_reason = "大盤處於月線下下修 (逆勢受阻)"
                    elif pick['vol_ratio'] > 2.5:
                        fail_reason = "當日爆巨量 (隔日沖出貨賣壓)"
                    elif pick['risk_pct'] > 5.5:
                        fail_reason = "進場離支撐過遠 (追高停損幅度大)"
                    else:
                        fail_reason = "族群動能缺乏延續性"

                trade_log.append({
                    "選股營業日": entry_date.strftime("%Y-%m-%d"),
                    "推薦標的": pick['name'],
                    "進場價": round(entry_p, 2),
                    "停損價": round(stop_l, 2),
                    "第一目標價": round(tp_1, 2),
                    "出場價": round(exit_price, 2),
                    "持有天數": holding_days,
                    "損益%": round(pnl_pct, 2),
                    "勝負判定": "勝 🟢" if is_win else "敗 🔴",
                    "狀態": trade_status,
                    "失敗歸因": fail_reason
                })

            if trade_log:
                res_df = pd.DataFrame(trade_log)
                total_trades = len(res_df)
                wins = len(res_df[res_df['損益%'] > 0])
                win_rate = (wins / total_trades) * 100
                
                win_trades = res_df[res_df['損益%'] > 0]['損益%']
                loss_trades = res_df[res_df['損益%'] <= 0]['損益%']
                profit_factor = (win_trades.sum() / (abs(loss_trades.sum()) + 1e-9)) if not loss_trades.empty else 99.0

                st.subheader("📊 滾動回測戰報摘要")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("回測交易總次數", f"{total_trades} 筆")
                k2.metric("實戰歷史勝率", f"{win_rate:.1f}%", f"{wins} 勝 / {total_trades - wins} 負")
                k3.metric("賺賠比 (Profit Factor)", f"{profit_factor:.2f}")
                k4.metric("累計報酬率", f"{res_df['損益%'].sum():+.2f}%")

                res_df['累計報酬%'] = res_df['損益%'].cumsum()
                fig_equity = go.Figure()
                fig_equity.add_trace(go.Scatter(
                    x=res_df['選股營業日'], y=res_df['累計報酬%'],
                    mode='lines+markers', name='累計獲利曲線',
                    line=dict(color='#eb4034', width=2.5),
                    fill='tozeroy'
                ))
                fig_equity.update_layout(title="歷史營業日逐日累計報酬率走勢 (%)", height=380, margin=dict(l=20,r=20,t=40,b=20))
                st.plotly_chart(fig_equity, use_container_width=True)

                st.subheader("📋 逐日交易明細清單")
                st.dataframe(res_df, use_container_width=True)
            else:
                st.warning("回測區間內無符合高分做多門檻的交易，系統成功發揮空手防守機制！")

# =========================================================
# Tab 3：20 大族群動能與市場內部寬度榜
# =========================================================
with tab_rank:
    st.header("🔥 20 大尖端族群動能熱度與多因子全景榜")
    daily_res = st.session_state.get('daily_results', None)
    if daily_res:
        filter_sec = st.selectbox("依族群篩選查看", ["全部族群"] + list(SECTOR_MAP.keys()) + (["自選觀察族群"] if custom_input else []))
        table_rows = []
        for r in daily_res:
            if filter_sec != "全部族群" and r['sector'] != filter_sec:
                continue
            table_rows.append({
                "標的": r['name'],
                "所屬族群": r['sector'],
                "綜合分(95)": r['tech_chip_score'],
                "現價": f"{r['close']:.2f}",
                "今日漲跌%": f"{r['pct']:+.2f}%",
                "型態特徵": r['pattern'],
                "籌碼強度": f"{r['chip_acc']:.2f}",
                "相對大盤RS%": f"{r['rs_alpha']:+.2f}%",
                "量比": f"{r['vol_ratio']:.2f}x",
                "MFI": f"{r['mfi']:.1f}",
                "RSI": f"{r['rsi']:.1f}",
                "建議停損%": f"-{r['risk_pct']:.2f}%"
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
    else:
        st.info("請先至第一分頁點擊『啟動大數據全指標掃描』，數據將在此自動同步呈現。")

# =========================================================
# Tab 4：個股深入多維技術診斷
# =========================================================
with tab_detail:
    st.sidebar.title("📈 個股技術分析控制台")
    all_avai_sectors = list(SECTOR_MAP.keys()) + (["自選觀察族群"] if custom_input else [])
    selected_sec = st.sidebar.selectbox("快速按族群挑選", all_avai_sectors, key="d_sec")
    
    sec_stocks = {k: v for k, v in CURRENT_STOCKS.items() if CURRENT_STOCK_TO_SECTOR[k] == selected_sec}
    selected_stock = st.sidebar.selectbox("選擇要分析的標的", list(sec_stocks.keys()), key="d_stk")
    stock_code = sec_stocks[selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2, key="d_per")
    show_ma = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA10", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖技術指標配置", [
        "精選三大動能 (KD + MACD + RSI)",
        "主力資金流向 (成交量 + OBV + MFI)",
        "波動壓縮與型態 (布林帶寬 BandWidth)",
        "🚀 全副圖完整展示 (全部指標展開)"
    ])

    df_d = yf.download(stock_code, period=period_map[selected_period], progress=False)
    if hasattr(df_d.columns, 'levels') and len(df_d.columns.levels) > 1:
        df_d.columns = df_d.columns.get_level_values(0)

    if not df_d.empty:
        df_d = calculate_all_indicators(df_d)
        latest_d = df_d.iloc[-1]
        prev_d = df_d.iloc[-2] if len(df_d) > 1 else latest_d
        p_diff = latest_d['Close'] - prev_d['Close']
        pct_diff = (p_diff / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 綜合深度技術看板 ｜ 族群：{selected_sec}")
        st.write(f"🏷️ **即時型態辨識**：`{latest_d['Candle_Pattern']}`")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("最新收盤價", f"{latest_d['Close']:.2f} 元", f"{p_diff:+.2f} ({pct_diff:+.2f}%)")
        c2.metric("單日最高 / 最低", f"{latest_d['High']:.2f} / {latest_d['Low']:.2f}")
        c3.metric("MFI 資金流量", f"{latest_d['MFI']:.1f}")
        c4.metric("RSI (14)", f"{latest_d['RSI']:.1f}")
        c5.metric("14日真實波幅 (ATR)", f"{latest_d['ATR']:.2f} 元")

        if indicator_choice == "🚀 全副圖完整展示 (全部指標展開)":
            rows, r_heights = 6, [0.38, 0.12, 0.12, 0.13, 0.12, 0.13]
            sub_titles = ("K線與均線走勢", "成交量 (Volume)", "KD 指標 (9,3,3)", "MACD (12,26,9)", "RSI (14)", "MFI 資金流量 (14)")
        elif indicator_choice == "精選三大動能 (KD + MACD + RSI)":
            rows, r_heights = 4, [0.46, 0.18, 0.18, 0.18]
            sub_titles = ("K線與均線走勢", "KD 指標", "MACD 指標", "RSI (14)")
        elif indicator_choice == "主力資金流向 (成交量 + OBV + MFI)":
            rows, r_heights = 4, [0.46, 0.18, 0.18, 0.18]
            sub_titles = ("K線與均線走勢", "成交量 (Volume)", "OBV 能量潮", "MFI 資金流量")
        else:
            rows, r_heights = 3, [0.55, 0.22, 0.23]
            sub_titles = ("K線與均線走勢", "成交量", "布林帶寬 (BandWidth)")

        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=r_heights, subplot_titles=sub_titles)

        fig.add_trace(go.Candlestick(
            x=df_d.index, open=df_d['Open'], high=df_d['High'], low=df_d['Low'], close=df_d['Close'],
            name="K線", increasing_line_color='#eb4034', decreasing_line_color='#0da651'
        ), row=1, col=1)

        ma_colors = {'MA5': '#f39c12', 'MA10': '#e67e22', 'MA20': '#2980b9', 'MA60': '#16a085'}
        for ma in show_ma:
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d[ma], mode='lines', name=ma, line=dict(color=ma_colors[ma], width=1.5)), row=1, col=1)

        if indicator_choice == "🚀 全副圖完整展示 (全部指標展開)":
            vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['K'], line=dict(color='#e74c3c', width=1.5), name="K"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['D'], line=dict(color='#3498db', width=1.5), name="D"), row=3, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="gray", row=3, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="gray", row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=4, col=1)
            hist_c = ['#eb4034' if v >= 0 else '#0da651' for v in df_d['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['MACD_Hist'], marker_color=hist_c, name="MACD柱"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['RSI'], line=dict(color='#9b59b6', width=1.4), name="RSI(14)"), row=5, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MFI'], line=dict(color='#1abc9c', width=1.4), name="MFI(14)"), row=6, col=1)
        elif indicator_choice == "精選三大動能 (KD + MACD + RSI)":
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['K'], line=dict(color='#e74c3c', width=1.5), name="K"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['D'], line=dict(color='#3498db', width=1.5), name="D"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['DIF'], line=dict(color='#2980b9', width=1.3), name="DIF"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MACD'], line=dict(color='#e67e22', width=1.3), name="MACD"), row=3, col=1)
            hist_c = ['#eb4034' if v >= 0 else '#0da651' for v in df_d['MACD_Hist']]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['MACD_Hist'], marker_color=hist_c, name="MACD柱"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['RSI'], line=dict(color='#9b59b6', width=1.4), name="RSI"), row=4, col=1)
        elif indicator_choice == "主力資金流向 (成交量 + OBV + MFI)":
            vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['OBV'], line=dict(color='#e67e22', width=1.4), name="OBV"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['OBV_MA10'], line=dict(color='gray', width=1.0), name="OBV_MA10"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['MFI'], line=dict(color='#1abc9c', width=1.4), name="MFI"), row=4, col=1)
        else:
            vol_c = ['#eb4034' if c >= o else '#0da651' for c, o in zip(df_d['Close'], df_d['Open'])]
            fig.add_trace(go.Bar(x=df_d.index, y=df_d['Volume'], marker_color=vol_c, name="成交量"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_d.index, y=df_d['BB_Width'], line=dict(color='#8e44ad', width=1.4), name="BandWidth"), row=3, col=1)

        fig.update_layout(height=950, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📥 檢視與匯出個股數據 (CSV)"):
            st.dataframe(df_d.tail(30).sort_index(ascending=False))
            st.download_button(
                label="下載完整歷史資料 CSV",
                data=df_d.to_csv().encode('utf-8-sig'),
                file_name=f"{stock_code}_history.csv",
                mime="text/csv"
            )

# =========================================================
# Tab 5：操盤大師實戰守則 (Minervini / Weinstein / 資金管理)
# =========================================================
with tab_manual:
    st.header("📚 頂尖量化操盤大師實戰守則")
    st.markdown("""
    ### 一、 華爾街傳奇動能大師 Mark Minervini 核心準則
    1. **永遠順著阻力最小的方向交易**：絕不在股價低於 60MA 季線時買進任何股票。
    2. **波動收縮型態 (VCP)**：飆股起漲前必定伴隨量能急縮與振幅收斂，那是主力清洗散戶浮額的足跡。
    3. **非對稱風險報酬比**：進場前先決定「如果我錯了，最多賠多少錢」，永遠讓賠率維持在 1 : 2 以上。

    ---
    ### 二、 資金管理第一定律：部位規模的數學
    * **嚴格的 2% 法則**：任何單筆交易的停損金額，絕不超過整體投資組合的 1.5% ~ 2%。
    * **張數計算公式**：
    $$\\text{買進股數} = \\frac{\\text{總資金} \\times \\text{風險比例 (\\%)}}{\\text{進場價} - \\text{停損價}}$$
    * 只要恪守公式，就算連續遭遇 5 次停損，總資產折損依然控制在 10% 以內，隨時能藉由一次波段翻身。
    """)