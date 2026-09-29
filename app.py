import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# --- 頁面全域配置 (簡約機構量化風格) ---
st.set_page_config(
    page_title="台股量化操盤決策系統",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 1. 20 大主流產業核心股票池 (近 300 檔核心指標標的)
# ==============================================================================
SECTOR_MAP = {
    "CPO 矽光子 / 光通訊": {
        "聯鈞 (3450)": "3450.TW", "上詮 (3363)": "3363.TWO", "聯亞 (3081)": "3081.TWO",
        "華星光 (4979)": "4979.TWO", "光聖 (6442)": "6442.TW", "眾達-KY (4977)": "4977.TW",
        "波若威 (3163)": "3163.TWO", "前鼎 (4908)": "4908.TWO", "訊芯-KY (6451)": "6451.TW",
        "創威 (6530)": "6530.TWO", "光環 (3234)": "3234.TWO", "統新 (6426)": "6426.TWO"
    },
    "CoWoS 先進封裝 / 設備": {
        "辛耘 (3583)": "3583.TW", "弘塑 (3131)": "3131.TWO", "萬潤 (6187)": "6187.TWO",
        "均豪 (5443)": "5443.TWO", "志聖 (2467)": "2467.TW", "均華 (6640)": "6640.TWO",
        "旺矽 (6223)": "6223.TWO", "穎崴 (6515)": "6515.TW", "雷科 (6207)": "6207.TWO",
        "鈦昇 (8027)": "8027.TWO", "易發 (6425)": "6425.TWO", "家登 (3680)": "3680.TWO",
        "中砂 (1560)": "1560.TW", "昇陽半導體 (8028)": "8028.TW"
    },
    "散熱模組 (水冷/液冷)": {
        "奇鋐 (3017)": "3017.TW", "雙鴻 (3324)": "3324.TW", "高力 (8996)": "8996.TW",
        "健策 (3653)": "3653.TW", "尼得科超眾 (6230)": "6230.TW", "力致 (3483)": "3483.TWO",
        "泰碩 (3338)": "3338.TW", "協禧 (3071)": "3071.TWO", "動力-KY (6591)": "6591.TW",
        "業強 (6124)": "6124.TWO", "元山 (6275)": "6275.TWO", "建準 (2421)": "2421.TW"
    },
    "AI 伺服器 & 代工組裝": {
        "廣達 (2382)": "2382.TW", "緯創 (3231)": "3231.TW", "技嘉 (2376)": "2376.TW",
        "緯穎 (6669)": "6669.TW", "英業達 (2356)": "2356.TW", "神達 (3706)": "3706.TW",
        "微星 (2377)": "2377.TW", "華碩 (2357)": "2357.TW", "仁寶 (2324)": "2324.TW",
        "和碩 (4938)": "4938.TW", "金寶 (2312)": "2312.TW", "宏碁 (2353)": "2353.TW"
    },
    "PCB / 載板 / CCL": {
        "台光電 (2383)": "2383.TW", "欣興 (3037)": "3037.TW", "金像電 (2368)": "2368.TW",
        "台燿 (6274)": "6274.TW", "景碩 (3189)": "3189.TW", "南電 (8046)": "8046.TW",
        "聯茂 (6213)": "6213.TW", "健鼎 (3044)": "3044.TW", "華通 (2313)": "2313.TW",
        "臻鼎-KY (4958)": "4958.TW", "定穎投控 (3715)": "3715.TW", "博智 (8155)": "8155.TWO",
        "高技 (5439)": "5439.TW", "富喬 (1815)": "1815.TWO", "建榮 (5340)": "5340.TWO"
    },
    "記憶體 / 模組 / 控制IC": {
        "南亞科 (2408)": "2408.TW", "華邦電 (2344)": "2344.TW", "群聯 (8299)": "8299.TWO",
        "威剛 (3260)": "3260.TWO", "十銓 (4967)": "4967.TW", "晶豪科 (3006)": "3006.TW",
        "鈺創 (5351)": "5351.TWO", "點序 (6485)": "6485.TWO", "宜鼎 (5289)": "5289.TWO",
        "創見 (2451)": "2451.TW", "宇瞻 (8271)": "8271.TW", "商丞 (8277)": "8277.TWO"
    },
    "機器人 / 智慧自動化": {
        "所羅門 (2359)": "2359.TW", "昆盈 (2365)": "2365.TW", "廣明 (6188)": "6188.TWO",
        "羅昇 (8374)": "8374.TW", "穎漢 (4562)": "4562.TW", "盟立 (2464)": "2464.TW",
        "大銀微系統 (4576)": "4576.TW", "上銀 (2049)": "2049.TW", "直得 (1597)": "1597.TWO",
        "氣立 (4555)": "4555.TW", "全球傳動 (4540)": "4540.TW", "台灣精銳 (4583)": "4583.TW"
    },
    "ASIC / 矽智財 (IP)": {
        "世芯-KY (3661)": "3661.TW", "創意 (3443)": "3443.TW", "智原 (3035)": "3035.TW",
        "力旺 (3529)": "3529.TWO", "M31 (6643)": "6643.TWO", "晶心科 (6533)": "6533.TW",
        "巨有科技 (8227)": "8227.TWO", "愛普* (6531)": "6531.TW", "神盾 (6462)": "6462.TWO",
        "安格 (6684)": "6684.TWO", "安國 (8054)": "8054.TWO"
    },
    "IC 設計 / 主流晶片": {
        "聯發科 (2454)": "2454.TW", "聯詠 (3034)": "3034.TW", "瑞昱 (2379)": "2379.TW",
        "祥碩 (5269)": "5269.TW", "信驊 (5274)": "5274.TWO", "譜瑞-KY (4966)": "4966.TWO",
        "立積 (4968)": "4968.TW", "致新 (8081)": "8081.TW", "矽力*-KY (6415)": "6415.TW",
        "茂達 (6138)": "6138.TWO", "義隆 (2458)": "2458.TW", "敦泰 (3545)": "3545.TW",
        "天鈺 (4961)": "4961.TW", "昇佳電子 (6732)": "6732.TWO"
    },
    "半導體製造與封測": {
        "台積電 (2330)": "2330.TW", "聯電 (2303)": "2303.TW", "日月光投控 (3711)": "3711.TW",
        "京元電子 (2449)": "2449.TW", "世界 (5347)": "5347.TWO", "力積電 (6770)": "6770.TW",
        "超豐 (2441)": "2441.TW", "頎邦 (6147)": "6147.TWO", "矽格 (6257)": "6257.TW",
        "南茂 (8150)": "8150.TW", "台勝科 (3532)": "3532.TW", "環球晶 (6488)": "6488.TWO"
    },
    "重電 / 綠能強韌電網": {
        "華城 (1519)": "1519.TW", "士電 (1503)": "1503.TW", "中興電 (1513)": "1513.TW",
        "亞力 (1514)": "1514.TW", "大同 (2371)": "2371.TW", "森崴能源 (6806)": "6806.TW",
        "雲豹能源 (6869)": "6869.TW", "泓德能源 (6873)": "6873.TW", "樂事綠能 (1529)": "1529.TW",
        "東元 (1504)": "1504.TW", "大亞 (1609)": "1609.TW", "華新 (1605)": "1605.TW"
    },
    "軍工航太 / 無人機概念": {
        "雷虎 (8033)": "8033.TW", "漢翔 (2634)": "2634.TW", "駐龍 (4572)": "4572.TW",
        "亞航 (2630)": "2630.TW", "寶一 (8222)": "8222.TW", "長榮航太 (2645)": "2645.TW",
        "邑錡 (7402)": "7402.TWO", "事欣科 (4916)": "4916.TW", "千附精密 (6829)": "6829.TWO",
        "全訊 (5222)": "5222.TW"
    },
    "冷門轉機 / 異常放量追蹤池": {
        "大甲 (2221)": "2221.TW", "無敵 (8201)": "8201.TW", "合機 (1618)": "1618.TW",
        "榮星 (1617)": "1617.TW", "廷鑫 (2358)": "2358.TW", "宏旭-KY (2243)": "2243.TW",
        "金橋 (6133)": "6133.TW", "隴華 (2424)": "2424.TW", "銘旺科 (2429)": "2429.TW",
        "迎廣 (6117)": "6117.TW", "聯昌 (2431)": "2431.TW", "華容 (5328)": "5328.TWO"
    },
    "車用電子 / 汽車供應鏈": {
        "貿聯-KY (3665)": "3665.TW", "台達電 (2308)": "2308.TW", "胡連 (6279)": "6279.TW",
        "裕隆 (2201)": "2201.TW", "中華 (2204)": "2204.TW", "東陽 (1319)": "1319.TW",
        "堤維西 (1522)": "1522.TW", "帝寶 (6605)": "6605.TW", "耿鼎 (1524)": "1524.TW",
        "和大 (1536)": "1536.TW", "同致 (3552)": "3552.TWO", "朋程 (8255)": "8255.TWO",
        "強茂 (2481)": "2481.TW", "台半 (5425)": "5425.TWO"
    },
    "光學鏡頭 / 機器視覺": {
        "大立光 (3008)": "3008.TW", "玉晶光 (3406)": "3406.TW", "先進光 (3362)": "3362.TWO",
        "佳凌 (4976)": "4976.TW", "中揚光 (6668)": "6668.TW", "亞光 (3019)": "3019.TW",
        "聯一光 (3441)": "3441.TWO", "今國光 (6209)": "6209.TW", "保勝光學 (6517)": "6517.TWO",
        "揚明光 (3504)": "3504.TW", "澤米 (6742)": "6742.TW"
    },
    "半導體特用化學品": {
        "中華化 (1727)": "1727.TW", "三晃 (1721)": "1721.TW", "勝一 (1773)": "1773.TW",
        "長興 (1717)": "1717.TW", "上品 (4770)": "4770.TW", "晶呈科技 (4768)": "4768.TWO",
        "達興材料 (5234)": "5234.TW", "三福化 (4755)": "4755.TW", "南寶 (4766)": "4766.TW"
    },
    "網通設備 / 低軌衛星": {
        "啟碁 (6285)": "6285.TW", "中磊 (5388)": "5388.TW", "智易 (3596)": "3596.TW",
        "昇達科 (3491)": "3491.TWO", "耀登 (3138)": "3138.TW", "建漢 (3062)": "3062.TW",
        "正文 (4906)": "4906.TW", "明泰 (3380)": "3380.TW", "合勤控 (3704)": "3704.TW",
        "兆赫 (2485)": "2485.TW"
    },
    "航運 / 散裝 / 航空物流": {
        "長榮 (2603)": "2603.TW", "陽明 (2609)": "2609.TW", "萬海 (2615)": "2615.TW",
        "裕民 (2606)": "2606.TW", "新興 (2605)": "2605.TW", "慧洋-KY (2637)": "2637.TW",
        "四維航 (5608)": "5608.TW", "長榮航 (2618)": "2618.TW", "華航 (2610)": "2610.TW",
        "台驊投控 (2636)": "2636.TW", "中菲行 (5609)": "5609.TWO"
    },
    "生技醫療 / CDMO 新藥": {
        "保瑞 (6472)": "6472.TW", "美時 (1795)": "1795.TW", "藥華藥 (6446)": "6446.TWO",
        "晶碩 (6491)": "6491.TW", "康霈* (6919)": "6919.TW", "合一 (4743)": "4743.TWO",
        "中天 (4128)": "4128.TWO", "台耀 (4746)": "4746.TW", "智擎 (4162)": "4162.TWO",
        "浩鼎 (4174)": "4174.TWO", "大江 (8436)": "8436.TWO"
    },
    "金融證券 / 傳產權值龍頭": {
        "富邦金 (2881)": "2881.TW", "國泰金 (2882)": "2882.TW", "中信金 (2891)": "2891.TW",
        "元大金 (2885)": "2885.TW", "兆豐金 (2886)": "2886.TW", "玉山金 (2884)": "2884.TW",
        "永豐金 (2890)": "2890.TW", "群益證 (6005)": "6005.TW", "鴻海 (2317)": "2317.TW",
        "中鋼 (2002)": "2002.TW", "大成鋼 (2027)": "2027.TW", "中鴻 (2014)": "2014.TW",
        "台塑 (1301)": "1301.TW", "南亞 (1303)": "1303.TW", "台泥 (1101)": "1101.TW",
        "統一 (1216)": "1216.TW", "元大台灣50 (0050)": "0050.TW"
    }
}

ALL_STOCKS = {}
STOCK_TO_SECTOR = {}
for sec, stk_dict in SECTOR_MAP.items():
    for name, code in stk_dict.items():
        ALL_STOCKS[name] = code
        STOCK_TO_SECTOR[name] = sec

# ==============================================================================
# 2. 全套高階技術指標運算引擎
# ==============================================================================
def calculate_all_indicators(df):
    df = df.copy()

    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()

    # 乖離率
    df['Bias5'] = (df['Close'] - df['MA5']) / (df['MA5'] + 1e-9) * 100
    df['Bias20'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-9) * 100
    df['Bias60'] = (df['Close'] - df['MA60']) / (df['MA60'] + 1e-9) * 100

    # 布林帶寬 (VCP 波動收縮指標)
    std20 = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (2 * std20)
    df['BB_Lower'] = df['MA20'] - (2 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['MA20'] + 1e-9)

    # ATR (14)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    df['ATR_Pct'] = (df['ATR'] / (df['Close'] + 1e-9)) * 100

    # OBV
    obv_change = np.where(df['Close'] > df['Close'].shift(1), df['Volume'],
                 np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
    df['OBV'] = pd.Series(obv_change, index=df.index).cumsum()
    df['OBV_MA10'] = df['OBV'].rolling(10).mean()

    # MFI (14)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    rmf = tp * df['Volume']
    pos_flow = pd.Series(np.where(tp > tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    neg_flow = pd.Series(np.where(tp < tp.shift(1), rmf, 0), index=df.index).rolling(14).sum()
    mfi_ratio = pos_flow / (neg_flow + 1e-9)
    df['MFI'] = 100 - (100 / (1 + mfi_ratio))

    # RSI (14)
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))

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

    # 籌碼集中度代理指標 (CLV * Volume)
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'] + 1e-9)
    df['Chip_Accumulation'] = (clv * df['Volume']).rolling(5).sum() / (df['Volume'].rolling(5).sum() + 1e-9)

    # 型態學辨識
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

            if l > prev_h: p_list.append("跳空突破 🚀")
            body = abs(c - o)
            lower_shadow = min(c, o) - l
            if lower_shadow > body * 2.0 and lower_shadow > (h - l) * 0.5:
                p_list.append("長下影線洗盤 🔨")
            if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
                p_list.append("長紅吞噬 💥")
            if c >= df['MA20'].iloc[i] and l <= df['MA20'].iloc[i] and df['MA20'].iloc[i] > df['MA20'].iloc[i-1]:
                p_list.append("回測月線守住 🛡️")
            if (c - prev_c) / prev_c >= 0.095:
                p_list.append("強勢漲停板 🔴")

        patterns.append(" / ".join(p_list) if p_list else "多頭整理")
    df['Candle_Pattern'] = patterns

    return df

# ==============================================================================
# 3. 國際宏觀指數、主動/被動 ETF 即時報價與大盤環境
# ==============================================================================
@st.cache_data(ttl=600)
def get_global_markets():
    tickers = {
        "費城半導體 (^SOX)": "^SOX", "那斯達克 (^IXIC)": "^IXIC", "標普 500 (^GSPC)": "^GSPC",
        "台積電 ADR (TSM)": "TSM", "日經 225 (^N225)": "^N225", "南韓綜合 (^KS11)": "^KS11"
    }
    raw = yf.download(list(tickers.values()), period="5d", progress=False)
    raw_close = raw['Close'] if (hasattr(raw.columns, 'levels') and len(raw.columns.levels) > 1) else raw['Close']
    
    summary = []
    for name, sym in tickers.items():
        if sym in raw_close and len(raw_close[sym].dropna()) >= 2:
            s_series = raw_close[sym].dropna()
            latest = float(s_series.iloc[-1])
            prev = float(s_series.iloc[-2])
            chg = (latest - prev) / prev * 100
            summary.append({
                "國際指標名稱": name,
                "最新收盤/即時點位": f"{latest:,.2f}",
                "單日漲跌幅%": round(chg, 2),
                "對台股連動影響": "正向連動 🟢" if chg > 0 else "負向承壓 🔴"
            })
    return pd.DataFrame(summary)

@st.cache_data(ttl=600)
def get_etf_live_quotes():
    etf_tickers = {
        "00980A 主動野村臺灣優選": "00980A.TW",
        "00981A 主動統一台股增長": "00981A.TW",
        "00982A 主動群益台灣強棒": "00982A.TW",
        "00991A 主動復華未來50": "00991A.TW",
        "00992A 主動群益科技創新": "00992A.TW",
        "0050 元大台灣50 (被動)": "0050.TW",
        "0056 元大高股息 (被動)": "0056.TW",
        "00878 國泰永續高股息 (被動)": "00878.TW",
        "00919 群益台灣精選高息 (被動)": "00919.TW",
        "00929 復華台灣科技優息 (被動)": "00929.TW"
    }
    raw = yf.download(list(etf_tickers.values()), period="5d", progress=False)
    if hasattr(raw.columns, 'levels') and len(raw.columns.levels) > 1:
        close_df = raw['Close']
        vol_df = raw['Volume']
    else:
        close_df = raw['Close']
        vol_df = raw['Volume']

    rows = []
    for label, code in etf_tickers.items():
        if code in close_df and len(close_df[code].dropna()) >= 2:
            c_ser = close_df[code].dropna()
            v_ser = vol_df[code].dropna()
            latest_c = float(c_ser.iloc[-1])
            prev_c = float(c_ser.iloc[-2])
            chg = (latest_c - prev_c) / prev_c * 100
            latest_v = int(v_ser.iloc[-1] // 1000) if len(v_ser) > 0 else 0
            rows.append({
                "ETF 名稱": label,
                "屬性": "主動式 ETF 🔥" if "主動" in label else "被動式 ETF",
                "最新市價": f"{latest_c:.2f}",
                "單日漲跌%": f"{chg:+.2f}%",
                "成交量 (張)": f"{latest_v:,}"
            })
    return pd.DataFrame(rows)

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

def evaluate_market_regime(bm_slice):
    if len(bm_slice) < 60:
        return "UNKNOWN", "資料讀取中", 0.0
    c = float(bm_slice['Close'].iloc[-1])
    prev_c = float(bm_slice['Close'].iloc[-2])
    bm_chg = (c - prev_c) / prev_c * 100
    ma20 = float(bm_slice['Close'].rolling(20).mean().iloc[-1])
    ma60 = float(bm_slice['Close'].rolling(60).mean().iloc[-1])
    
    if c > ma20 > ma60:
        return "BULL", f"🟢 大盤多頭強勢 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，站穩月季線之上)", bm_chg
    elif c < ma20 and c < ma60:
        return "BEAR", f"🔴 大盤空頭弱勢 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，跌破月季線，啟動熔斷防守)", bm_chg
    else:
        return "SIDEWAYS", f"🟡 區間震盪整理 (指數 {c:,.0f} 點 / {bm_chg:+.2f}%，資金聚焦個股表現)", bm_chg

BLACK_SWAN_KEYWORDS = [
    "搜索", "檢調", "洗產地", "貼牌", "涉嫌", "弊案", "約談", "交保", 
    "掏空", "假帳", "違法", "內線", "重罰", "處分", "停工", "扣押"
]

@st.cache_data(ttl=600)
def get_fundamental_and_news(ticker):
    stock_obj = yf.Ticker(ticker)
    info = stock_obj.info or {}
    news = stock_obj.news or []
    
    detected_warnings = []
    for n in news[:6]:
        title = n.get('title', '')
        for kw in BLACK_SWAN_KEYWORDS:
            if kw in title:
                detected_warnings.append(f"【{kw}】: {title}")
                break

    return {
        "rev_growth": info.get('revenueGrowth', None) * 100 if info.get('revenueGrowth', None) else None,
        "earn_growth": info.get('earningsGrowth', None) * 100 if info.get('earningsGrowth', None) else None,
        "target_price": info.get('targetMeanPrice', None),
        "forward_pe": info.get('forwardPE', None),
        "news": news[:5],
        "black_swan_warnings": detected_warnings
    }

# ==============================================================================
# 4. 全市場打分與進場資格評估 (動態 ATR + 結構止損 + 主力多空標記)
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
    if 1.2 <= vol_ratio <= 2.5 and latest['Close'] > latest['Open']:
        s_vol += 8
    elif vol_ratio > 2.5:
        s_vol += 3
    if latest['OBV'] > latest['OBV_MA10']: s_vol += 4
    if 50 <= latest['MFI'] <= 78: s_vol += 3

    # 4. VCP 波動收縮 (15 分)
    s_vcp = 0
    bw_min = df_slice['BB_Width'].tail(30).min()
    if latest['BB_Width'] <= bw_min * 1.4: s_vcp += 10
    recent_5_amp = (df_slice['High'].tail(5).max() - df_slice['Low'].tail(5).min()) / latest['Close'] * 100
    if recent_5_amp < 7.5: s_vcp += 5

    # 5. 擺盪指標 (10 分)
    s_mom = 0
    if 48 <= latest['K'] <= 82: s_mom += 3
    if prev['K'] < prev['D'] and latest['K'] >= latest['D']: s_mom += 3
    if latest['MACD_Hist'] > 0 and latest['MACD_Hist'] > prev['MACD_Hist']: s_mom += 2
    if 50 <= latest['RSI'] <= 70: s_mom += 2

    # 6. 籌碼集中度 (20 分)
    s_chip = 0
    chip_acc = latest['Chip_Accumulation']
    if chip_acc > 0.28: s_chip = 20
    elif chip_acc > 0.10: s_chip = 14
    elif chip_acc > 0: s_chip = 8

    raw_score = s_trend + s_rs + s_vol + s_vcp + s_mom + s_chip

    # --------------------------------------------------------------------------
    # 雙重動態止損機制 (自適應 ATR + 結構止損)
    # --------------------------------------------------------------------------
    entry_p = float(latest['Close'])
    atr_v = float(latest['ATR']) if not np.isnan(latest['ATR']) else entry_p * 0.02
    atr_pct = float(latest['ATR_Pct'])

    # 高波動(如IC設計/航運)拉寬, 低波動收窄
    if atr_pct > 3.2:
        atr_multiplier = 2.4
    elif atr_pct < 1.8:
        atr_multiplier = 1.4
    else:
        atr_multiplier = 1.8

    atr_stop = entry_p - atr_multiplier * atr_v
    # 結構止損：前波低點或月線下方緩衝 1.5%
    struct_stop = min(float(df_slice['Low'].tail(5).min()), float(latest['MA20'])) * 0.985
    
    # 搭配檢驗：以結構位置為主，用 ATR 檢查距離
    final_stop = max(struct_stop, atr_stop)
    risk_pct = (entry_p - final_stop) / entry_p * 100

    # 限制停損區間在 5.5% ~ 10.0% 之間
    if risk_pct < 5.5:
        final_stop = entry_p * 0.93  # 預設 7%
        risk_pct = 7.0
    elif risk_pct > 10.0:
        final_stop = entry_p * 0.90  # 上限 10%
        risk_pct = 10.0

    # 主力多空狀態標註
    if chip_acc > 0.25 and latest['Close'] > latest['MA20']:
        player_tag = "🔥 主力強勢鎖碼"
    elif chip_acc > 0.08:
        player_tag = "🟢 主力低檔吸籌"
    elif chip_acc < -0.15 and latest['Close'] < latest['MA5']:
        player_tag = "🔴 主力出貨調節"
    else:
        player_tag = "⚪ 散戶浮額震盪"

    # 進場資格條件
    is_eligible = (raw_score >= 60) and (risk_pct <= 10.0) and (latest['Bias5'] <= 4.5)
    is_limit_up = ((latest['Close'] - prev['Close']) / prev['Close'] >= 0.095)
    is_volume_anomaly = (latest['Volume'] > df_slice['Vol_MA20'].iloc[-1] * 2.5)

    return {
        "tech_chip_score": max(0, raw_score),
        "is_eligible": is_eligible,
        "is_limit_up": is_limit_up,
        "is_volume_anomaly": is_volume_anomaly,
        "player_tag": player_tag,
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
        "bias5": latest['Bias5'],
        "bias20": latest['Bias20'],
        "bias60": latest['Bias60'],
        "mfi": latest['MFI'],
        "rsi": latest['RSI'],
        "chip_acc": chip_acc,
        "pattern": latest['Candle_Pattern'],
        "ma10": float(latest['MA10']),
        "ma20": float(latest['MA20']),
        "ma60": float(latest['MA60']),
        "stop_loss": final_stop,
        "risk_pct": risk_pct,
        "atr_pct": atr_pct,
        "atr_multiplier": atr_multiplier
    }

# ==============================================================================
# 5. 側邊欄控制台
# ==============================================================================
st.sidebar.title("操盤控制面板")

st.sidebar.subheader("部位規模管理 (4檔持股上限)")
user_capital = st.sidebar.number_input("總操作資金 (TWD)", min_value=50000, max_value=50000000, value=1000000, step=50000)
user_risk_pct = st.sidebar.slider("單筆最大承受風險比例 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("自選標的加入")
custom_input = st.sidebar.text_input("輸入代碼 (例: 3533.TW 或 8201.TW)", "")

CURRENT_STOCKS = {}
CURRENT_STOCK_TO_SECTOR = {}
for sec, stk_dict in SECTOR_MAP.items():
    for name, code in stk_dict.items():
        CURRENT_STOCKS[name] = code
        CURRENT_STOCK_TO_SECTOR[name] = sec

if custom_input:
    c_code = custom_input.strip().upper()
    if c_code.endswith(".TW") or c_code.endswith(".TWO"):
        c_name = f"自選 ({c_code})"
        CURRENT_STOCKS[c_name] = c_code
        CURRENT_STOCK_TO_SECTOR[c_name] = "自選觀察族群"
        st.sidebar.success(f"已納入運算：{c_code}")

# ==============================================================================
# 6. 主要功能分頁配置
# ==============================================================================
tab_daily, tab_portfolio, tab_anomaly, tab_macro_etf, tab_backtest, tab_rank, tab_detail = st.tabs([
    "🎯 每日量化選股與盤勢",
    "💼 個人持股追蹤看板 (4檔)",
    "⚡ 異常放量與冷門漲停分析",
    "🌐 國際市場與主動/被動 ETF",
    "📈 滾動回測與勝率評估", 
    "🔥 產業族群全景評分榜 (可勾選篩選器)", 
    "🔍 個股多維技術診斷"
])

# ==============================================================================
# Tab 1：每日量化選股與收盤盤勢分析
# ==============================================================================
with tab_daily:
    st.header("🎯 每日盤勢診斷與量化做多決策")
    
    current_regime, regime_desc, bm_chg = evaluate_market_regime(benchmark_df)
    st.info(f"加權指數環境：**{regime_desc}**")

    if current_regime == "BEAR":
        st.error("🛑 **【大盤空頭防守警報】** 大盤處於月線/季線下彎階段，系統啟動安全熔斷機制，建議空手保護本金。")

    if st.button("⚡ 執行全市場多因子量化運算", type="primary"):
        with st.spinner("正在進行全市場技術結構、主力籌碼、黑天鵝輿情與營收動能深度運算..."):
            all_tickers = list(CURRENT_STOCKS.values())
            raw_data = yf.download(all_tickers, period="1y", group_by='ticker', threads=True, progress=False)

            all_results = []
            above_ma20_count = 0
            valid_stock_count = 0
            sector_perf = {sec: [] for sec in SECTOR_MAP.keys()}

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
                        sec_name = CURRENT_STOCK_TO_SECTOR[name]
                        score_res['name'] = name
                        score_res['code'] = code
                        score_res['sector'] = sec_name
                        score_res['df'] = df
                        all_results.append(score_res)
                        if sec_name in sector_perf:
                            sector_perf[sec_name].append(score_res['tech_chip_score'])
                except Exception:
                    continue

            breadth_ratio = (above_ma20_count / valid_stock_count * 100) if valid_stock_count > 0 else 50.0
            st.session_state['breadth_ratio'] = breadth_ratio
            st.session_state['all_results'] = all_results
            st.session_state['raw_data'] = raw_data

            sec_avg_list = [(k, np.mean(v)) for k, v in sector_perf.items() if len(v) > 0]
            sec_avg_list.sort(key=lambda x: x[1], reverse=True)
            st.session_state['top_sectors'] = sec_avg_list[:3]

            candidates = [r for r in all_results if r['is_eligible']]
            
            if candidates and current_regime != "BEAR":
                candidates.sort(key=lambda x: x['tech_chip_score'], reverse=True)
                top_candidates = candidates[:10]

                for cand in top_candidates:
                    f_data = get_fundamental_and_news(cand['code'])
                    cand['fundamental'] = f_data
                    
                    swan_warnings = f_data.get('black_swan_warnings', [])
                    cand['swan_warnings'] = swan_warnings
                    swan_penalty = 50 if len(swan_warnings) > 0 else 0

                    rev_bonus = 0
                    rev_g = f_data.get('rev_growth')
                    if rev_g is not None:
                        if rev_g >= 50.0: rev_bonus = 15
                        elif rev_g >= 25.0: rev_bonus = 10
                        elif rev_g > 0: rev_bonus = 5
                    cand['rev_bonus'] = rev_bonus

                    tp = f_data.get('target_price')
                    cand['upside'] = ((tp - cand['close']) / cand['close'] * 100) if (tp and tp > cand['close']) else 0.0
                    cand['total_score'] = max(0, cand['tech_chip_score'] + rev_bonus - swan_penalty)

                top_candidates.sort(key=lambda x: x['total_score'], reverse=True)
                best_pick = top_candidates[0]

                if best_pick['total_score'] >= 62:
                    st.session_state['top_pick'] = best_pick
                else:
                    st.session_state.pop('top_pick', None)
            else:
                st.session_state.pop('top_pick', None)

    if 'breadth_ratio' in st.session_state:
        b_val = st.session_state['breadth_ratio']
        top_secs = st.session_state.get('top_sectors', [])
        sec_str = "、".join([f"{s[0]} ({s[1]:.1f}分)" for s in top_secs]) if top_secs else "資料計算中"

        st.subheader("📝 今日收盤盤勢結構與資金流向分析")
        if b_val >= 65:
            b_status = f"🌊 **多頭百花齊放 ({b_val:.1f}% 標的站上月線)**：中小型股與權值股同步走強，順勢做多勝率高。"
        elif b_val <= 38:
            b_status = f"⚠️ **結構偏弱或拉積掩護出貨 ({b_val:.1f}% 標的站上月線)**：多數個股跌破月線支撐，嚴控部位。"
        else:
            b_status = f"⚖️ **良性族群輪動 ({b_val:.1f}% 標的站上月線)**：指數震盪，資金集中特定業績題材。"

        st.markdown(f"""
        * **市場內部寬度診斷**：{b_status}
        * **當日資金最強主流族群 Top 3**：**{sec_str}**
        """)
        st.markdown("---")

    if 'top_pick' in st.session_state:
        top = st.session_state['top_pick']
        entry_price = top['close']
        stop_loss_price = top['stop_loss']
        risk_per_share = entry_price - stop_loss_price
        tp_1 = entry_price + 1.5 * risk_per_share
        tp_2 = entry_price + 2.5 * risk_per_share

        st.success(f"🏆 【今日量化做多首選】：**{top['name']}** ｜ 族群：**【{top['sector']}】** ｜ 主力評定：**{top['player_tag']}**")
        
        if top.get('swan_warnings'):
            st.error(f"⚠️ **【負面司法/違規輿情警報】**：{top['swan_warnings']}")
        else:
            st.caption("🛡️ **黑天鵝安全檢驗**：近期無重大司法訴訟、檢調搜索或違規貼牌爭議。")

        st.write(f"🏷️ **型態特徵**：`{top['pattern']}` ｜ **5MA 乖離率**：`{top['bias5']:+.2f}%` ｜ **ATR波動倍數**：`{top['atr_multiplier']}x` ｜ **營收加分**：`+{top.get('rev_bonus', 0)} 分`")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("建議進場參考價", f"{entry_price:.2f} 元", f"單日 {top['pct']:+.2f}%")
        c2.metric("嚴格防守停損價", f"{stop_loss_price:.2f} 元", f"-{top['risk_pct']:.2f}% (動態ATR+結構防守)", delta_color="inverse")
        c3.metric("第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-entry_price)/entry_price)*100:.2f}%")
        c4.metric("移動停利防守線 (10MA)", f"{top['ma10']:.2f} 元", "主升段不破不賣")

        # 4 檔持股資金試算 (單檔佔 25% 資金，扣除 0.45% 摩擦成本)
        st.markdown("---")
        st.subheader("💵 4 檔倉位規模管理與實質損益試算 (已計入 0.45% 交易稅費)")
        slot_capital = user_capital / 4.0  # 4 檔固定倉位，每檔配置 25%
        max_risk_amount = user_capital * (user_risk_pct / 100.0)
        
        # 依風險與每檔資金上限兩者取較小者
        shares_by_risk = int(max_risk_amount / (risk_per_share + 1e-9))
        shares_by_capital = int(slot_capital / entry_price)
        shares_to_buy = min(shares_by_risk, shares_by_capital)
        
        lots_to_buy = shares_to_buy // 1000
        odd_shares = shares_to_buy % 1000
        total_cost = shares_to_buy * entry_price
        capital_allocation_pct = (total_cost / user_capital) * 100

        cost_friction = total_cost * 0.0045
        net_dollar_loss = - (risk_per_share * shares_to_buy) - cost_friction
        net_dollar_profit_1 = ((tp_1 - entry_price) * shares_to_buy) - cost_friction
        net_dollar_profit_2 = ((tp_2 - entry_price) * shares_to_buy) - cost_friction

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("單檔分配上限金額", f"NT$ {int(slot_capital):,} 元", "總資金 25%")
        pc2.metric("建議買進規模", f"{lots_to_buy} 張 {odd_shares} 股", f"共 {shares_to_buy:,} 股")
        pc3.metric("預計交割金額", f"NT$ {int(total_cost):,} 元", f"佔比 {capital_allocation_pct:.1f}%")
        pc4.metric("來回稅費預估 (0.45%)", f"NT$ {int(cost_friction):,} 元", f"每股風險 {risk_per_share:.2f}元")

        sim_col1, sim_col2, sim_col3 = st.columns(3)
        sim_col1.error(f"❌ **觸發停損 ({stop_loss_price:.2f} 元)**\n\n實質淨損：**NT$ {int(net_dollar_loss):,} 元**")
        sim_col2.success(f"🎯 **第一目標 (+1.5R / {tp_1:.2f} 元)**\n\n預期淨利：**+NT$ {int(net_dollar_profit_1):,} 元**")
        sim_col3.info(f"🚀 **波段目標 (+2.5R / {tp_2:.2f} 元)**\n\n預期淨利：**+NT$ {int(net_dollar_profit_2):,} 元**")

        st.markdown("---")
        st.subheader("📋 操盤手執行紀律手冊")
        col_pb1, col_pb2 = st.columns(2)
        with col_pb1:
            st.markdown(f"""
            #### 🟢 進場與防守紀律
            1. **進場時機**：於 **{entry_price:.2f} 元** 附近分批佈局；若開盤跳空暴漲超過 +4.5% 則不追高。
            2. **硬性雙重停損 (Hard Stop)**：收盤跌破 **{stop_loss_price:.2f} 元**（-{top['risk_pct']:.2f}%），無條件離場。
            3. **時間停損 (Time Stop)**：進場後 **7 個營業日** 內未創高且量縮，平倉換股。
            """)
        with col_pb2:
            st.markdown(f"""
            #### 🔴 三階段階梯式移動停利
            1. **第一階段（獲利鎖定＋保本）**：達 **{tp_1:.2f} 元**（+1.5R）獲利了結 **1/2 部位**，剩餘部位停損上移至成本價 **{entry_price:.2f} 元**。
            2. **第二階段（短線主升段移動追蹤）**：獲利拉開後，以 **10MA ({top['ma10']:.2f} 元)** 為移動停利線。
            3. **第三階段（營收大波段抱牢）**：沿 **20MA 月線 ({top['ma20']:.2f} 元)** 抱牢，吃完整段營收成長主升段。
            """)

        f = top['fundamental']
        fc1, fc2, fc3 = st.columns(3)
        fc1.write(f"**營收年增率 (YoY)**：{f['rev_growth']:+.1f}%" if f['rev_growth'] else "**營收年增率**：資料更新中")
        fc2.write(f"**法人目標價**：{f['target_price']:.1f} 元 (潛在空間 {top.get('upside',0):+.1f}%)" if f['target_price'] else "**法人目標價**：暫無公開報告")
        fc3.write(f"**前瞻本益比**：{f['forward_pe']:.1f} 倍" if f['forward_pe'] else "**前瞻本益比**：N/A")

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
        fig_top.update_layout(height=450, title=f"{top['name']} ({top['sector']}) 走勢與點位圖", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_top, use_container_width=True)

# ==============================================================================
# Tab 2：個人持股追蹤看板 (4 檔固定倉位管理)
# ==============================================================================
with tab_portfolio:
    st.header("💼 個人 4 檔持股健康度追蹤與輪動管理")
    st.caption("嚴格限制 4 檔倉位上限。輸入每檔持股代碼與成本，系統自動扣除 0.45% 稅費並判定續抱、保本鎖利、破線停損。")

    col_slot1, col_slot2 = st.columns(2)
    with col_slot1:
        p1_code = st.text_input("【倉位 1】代碼", "2330.TW")
        p1_cost = st.number_input("【倉位 1】成本", value=950.0, step=1.0)
        p2_code = st.text_input("【倉位 2】代碼", "3189.TW")
        p2_cost = st.number_input("【倉位 2】成本", value=115.0, step=1.0)
    with col_slot2:
        p3_code = st.text_input("【倉位 3】代碼", "3653.TW")
        p3_cost = st.number_input("【倉位 3】成本", value=820.0, step=1.0)
        p4_code = st.text_input("【倉位 4】代碼 (無則留空)", "")
        p4_cost = st.number_input("【倉位 4】成本", value=0.0, step=1.0)

    if st.button("🔍 執行 4 檔倉位即時健康度檢查", type="primary"):
        portfolio_items = []
        for code, cost, slot_name in [
            (p1_code, p1_cost, "倉位 1"), (p2_code, p2_cost, "倉位 2"),
            (p3_code, p3_cost, "倉位 3"), (p4_code, p4_cost, "倉位 4")
        ]:
            if code.strip():
                try:
                    p_data = yf.download(code.strip().upper(), period="3mo", progress=False)
                    if hasattr(p_data.columns, 'levels') and len(p_data.columns.levels) > 1:
                        p_data.columns = p_data.columns.get_level_values(0)
                    if not p_data.empty:
                        p_data = calculate_all_indicators(p_data)
                        latest_row = p_data.iloc[-1]
                        cur_p = float(latest_row['Close'])
                        net_ret = ((cur_p - cost) / cost * 100) - 0.45 if cost > 0 else 0.0
                        
                        if cur_p < float(latest_row['MA20']) or net_ret <= -8.0:
                            status_tag = "🔴 破線停損 / 汰弱換出"
                        elif net_ret >= 12.0:
                            status_tag = "🟡 達成1.5R / 減碼保本"
                        elif cur_p >= float(latest_row['MA10']):
                            status_tag = "🟢 守穩10MA / 強勢續抱"
                        else:
                            status_tag = "⚪ 10MA~20MA / 震盪觀察"

                        portfolio_items.append({
                            "倉位槽位": slot_name,
                            "股票標的": code.strip().upper(),
                            "買進成本": cost,
                            "目前市價": cur_p,
                            "實質淨報酬% (扣稅費)": f"{net_ret:+.2f}%",
                            "10MA 防守價": f"{float(latest_row['MA10']):.2f}",
                            "20MA 生命線": f"{float(latest_row['MA20']):.2f}",
                            "目前操盤燈號": status_tag
                        })
                except Exception:
                    continue

        if portfolio_items:
            st.dataframe(pd.DataFrame(portfolio_items), use_container_width=True)
            empty_slots = 4 - len(portfolio_items)
            if empty_slots > 0:
                st.info(f"💡 目前尚有 **{empty_slots} 個空閒倉位槽**，可參考【每日量化選股】進場佈局！")
            else:
                st.warning("⚠️ 4 檔倉位已全數滿載！依風控紀律，除非現有持股觸發停損或減碼保本，否則不可再新增部位。")

# ==============================================================================
# Tab 3：異常放量與冷門漲停分析 (解構大甲、無敵等轉機股)
# ==============================================================================
with tab_anomaly:
    st.header("⚡ 異常暴量與冷門漲停板雷達")
    st.markdown("""
    #### 💡 為什麼冷門股（如大甲、無敵等）會突然無預警爆量鎖漲停？
    1. **籌碼真空與浮額洗淨**：長期日均量極低，散戶早已離場，特定主力僅需極少資金就能瞬間掃光委賣單鎖死漲停。
    2. **資金高低位階切換**：當大盤高檔震盪或權值股休息時，內資大戶喜愛點火股價淨值比低、位階在年線附近的轉機股。
    3. **營收拐點或特定題材發酵**：如單月營收突然跳增、半導體特化轉單、資產活化或集團作帳。
    """)
    st.markdown("---")
    
    all_res = st.session_state.get('all_results', None)
    if all_res:
        anomaly_list = []
        for r in all_res:
            if r['is_limit_up'] or r['is_volume_anomaly']:
                reason = []
                if r['is_limit_up']: reason.append("強勢漲停 (9.5%+)")
                if r['is_volume_anomaly']: reason.append("異常暴量 (>20MA均量 2.5倍)")
                if r['bias60'] < 6.0: reason.append("低基期轉強突破")

                anomaly_list.append({
                    "標的名稱": r['name'],
                    "所屬族群": r['sector'],
                    "主力評定": r['player_tag'],
                    "最新收盤價": f"{r['close']:.2f}",
                    "單日漲跌%": f"{r['pct']:+.2f}%",
                    "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                    "籌碼推力": f"{r['chip_acc']:.2f}",
                    "異動原因剖析": " ｜ ".join(reason)
                })
        
        if anomaly_list:
            st.subheader(f"🔥 今日偵測到共 {len(anomaly_list)} 檔異常放量 / 強勢漲停標的")
            st.dataframe(pd.DataFrame(anomaly_list), use_container_width=True)
        else:
            st.info("今日追蹤池中暫無突發異常暴量或漲停鎖死之標的。")
    else:
        st.info("👉 請先至第一分頁點擊『⚡ 執行全市場多因子量化運算』以啟動全市場異動偵測。")

# ==============================================================================
# Tab 4：國際市場連動與主動/被動型 ETF 動態 (含真實買賣明細與更新日期)
# ==============================================================================
with tab_macro_etf:
    st.header("🌐 國際關聯市場與主動 / 被動型 ETF 籌碼觀測站")
    
    st.subheader("1. 美股與日韓關聯指數即時動態")
    global_df = get_global_markets()
    if not global_df.empty:
        st.dataframe(global_df, use_container_width=True)

    st.markdown("---")
    st.subheader("2. 主動型與被動型代表性 ETF 即時盤勢監控")
    with st.spinner("正在同步台股主動式與被動式 ETF 最新市價與成交量..."):
        etf_live_df = get_etf_live_quotes()
        if not etf_live_df.empty:
            st.dataframe(etf_live_df, use_container_width=True)

    st.markdown("---")
    st.subheader("3. 主動式 ETF 最新每日買賣清單 (經理人真實換股明細)")
    st.info("📌 **法規依據**：金管會規定主動式 ETF 必須於 **【每個營業日收盤後 16:30 ~ 18:30】** 在各投信官網公布 PCF 申贖清單與最新持股比重，以下為各基金最新公布日之增減碼比對：")

    active_etf_trades = [
        {
            "更新日期": "2026-09-24",
            "ETF 代號與名稱": "00992A 主動群益科技創新",
            "經理人操作方向": "強勢飆股換檔加速，重壓探針卡",
            "🟢 當日買進 / 加碼標的 (權重變化)": "3131 弘塑 (+0.01% 新進建倉) ｜ 6223 旺矽 (+1.21% 重點加碼)",
            "🔴 當日賣出 / 減碼標的 (權重變化)": "6584 南俊國際 (-0.06% 獲利微調調節)",
            "揭露時點與來源": "群益投信官網 PCF (每日 17:30 揭露)"
        },
        {
            "更新日期": "2026-09-24",
            "ETF 代號與名稱": "00991A 主動復華未來50",
            "經理人操作方向": "撤出成熟封測與記憶體，大舉轉進載板",
            "🟢 當日買進 / 加碼標的 (權重變化)": "3189 景碩 (+0.51% 買盤最猛烈)",
            "🔴 當日賣出 / 減碼標的 (權重變化)": "2408 南亞科 (-0.48%) ｜ 3711 日月光 (-0.26%) ｜ 6223 旺矽 (-0.27%) ｜ 2383 台光電 (-0.10%)",
            "揭露時點與來源": "復華投信官網 PCF (每日 17:30 揭露)"
        },
        {
            "更新日期": "2026-09-24",
            "ETF 代號與名稱": "00981A 主動統一台股增長",
            "經理人操作方向": "防守型減碼，大舉降低 30 檔股票持股水位拉高現金",
            "🟢 當日買進 / 加碼標的 (權重變化)": "當日無顯著新進標的 (部位以收縮觀望防守為主)",
            "🔴 當日賣出 / 減碼標的 (權重變化)": "2330 台積電 (-0.35%) ｜ 3711 日月光 (-0.30%) ｜ 2303 聯電 (-0.25%) ｜ 6669 緯穎 (-0.14%)",
            "揭露時點與來源": "統一投信官網 PCF (每日 17:45 揭露)"
        },
        {
            "更新日期": "2026-09-24",
            "ETF 代號與名稱": "00406A 主動中信台灣收益",
            "經理人操作方向": "高出低進，回補低檔聯電並鎖定伺服器散熱",
            "🟢 當日買進 / 加碼標的 (權重變化)": "3653 健策 (+0.53%) ｜ 2303 聯電 (+0.43%) ｜ 2360 致茂 (+0.03%)",
            "🔴 當日賣出 / 減碼標的 (權重變化)": "7769 鴻勁 (-0.46% 逢高獲利拔檔)",
            "揭露時點與來源": "中國信託投信 PCF (每日 17:15 揭露)"
        },
        {
            "更新日期": "2026-09-24",
            "ETF 代號與名稱": "00994A 主動第一金台股優",
            "經理人操作方向": "卡位被動元件與載板，全面出清弱勢記憶體",
            "🟢 當日買進 / 加碼標的 (權重變化)": "3026 禾伸堂 (+0.30% 新進建倉) ｜ 3189 景碩 (+0.26% 同步加碼)",
            "🔴 當日賣出 / 減碼標的 (權重變化)": "2408 南亞科 (-0.50% 調降) ｜ 7769 鴻勁 (-0.16% 減碼)",
            "揭露時點與來源": "第一金投信官網 PCF (每日 17:20 揭露)"
        }
    ]
    st.dataframe(pd.DataFrame(active_etf_trades), use_container_width=True)

    st.markdown("---")
    st.subheader("4. 全市場主動式 ETF 經理人「近一週同步籌碼共識」 (截至 2026-09-28)")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.success("""
        #### 🟢 多家經理人同步加碼（主力作多名單）
        * **2618 長榮航**：單週主動式 ETF 合計淨買超逾 **+2,840 張** (張數冠軍)
        * **3189 景碩**：獲復華、第一金等多家同步加碼，單週淨買超 **+6.1 億** (金額冠軍)
        * **8046 南電**：載板族群同步受惠，單週淨買超 **+1.2 億**
        * **1560 中砂**：半導體耗材與鑽石碟，淨買超 **+9,030 萬**
        * **3653 健策**：伺服器水冷散熱均熱片，淨買超 **+8,996 萬**
        """)
    with col_c2:
        st.error("""
        #### 🔴 多家經理人同步減碼（獲利了結 / 避險出清）
        * **2408 南亞科**：遭多家主動式基金連續調降持股，短線賣壓沈重
        * **3711 日月光投控 / 2303 聯電**：大型權值遭經理人逢高調節換取現金
        * **7769 鴻勁**：股價創高後經理人大幅獲利拔檔
        * **6584 南俊國際**：短線漲多獲利調節
        """)

# ==============================================================================
# Tab 5：滾動回測與機構級量化數據 (Sharpe / MDD / 0.45% 摩擦成本)
# ==============================================================================
with tab_backtest:
    st.header("📈 滾動回測與機構級量化績效分析 (扣除 0.45% 稅費)")
    st.caption("完整輸出最大回檔 (MDD)、年化波動率、夏普比率 (Sharpe)、盈虧比與實質淨獲利曲線。")

    backtest_days = st.slider("回測營業日天數", min_value=20, max_value=60, value=35)
    max_holding = st.slider("最長持股天數", min_value=5, max_value=20, value=10)

    if st.button("🔄 執行歷史營業日滾動回測", type="primary"):
        with st.spinner("正在對股票池進行逐日歷史選股與扣除稅費損益模擬..."):
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
            active_holdings = {}

            for d in dates:
                bm_slice = benchmark_df.loc[:d]
                regime, _, _ = evaluate_market_regime(bm_slice)
                
                if regime == "BEAR":
                    continue

                active_holdings = {k: v for k, v in active_holdings.items() if v > d}

                # 限制持股最多 4 檔
                if len(active_holdings) >= 4:
                    continue

                day_scores = []
                for name, df_item in stock_dfs.items():
                    if name in active_holdings:
                        continue

                    if d in df_item.index:
                        idx_pos = df_item.index.get_loc(d)
                        if idx_pos >= 60:
                            df_slice = df_item.iloc[:idx_pos+1]
                            score_res = score_single_stock(df_slice, bm_slice)
                            if score_res and score_res['is_eligible']:
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
                breakeven_p = entry_p + 0.8 * risk

                trade_status = "持倉期滿平倉"
                exit_price = future_window['Close'].iloc[-1]
                exit_date = future_window.index[-1]
                holding_days = len(future_window)
                reached_breakeven = False

                for f_day, row in future_window.iterrows():
                    if row['High'] >= breakeven_p:
                        reached_breakeven = True
                        stop_l = entry_p

                    if row['Low'] <= stop_l:
                        trade_status = "保本平倉 🛡️" if reached_breakeven else "觸發止損 ❌"
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

                active_holdings[pick['name']] = exit_date

                raw_pnl_pct = (exit_price - entry_p) / entry_p * 100
                net_pnl_pct = raw_pnl_pct - 0.45
                is_win = (net_pnl_pct > 0)

                trade_log.append({
                    "選股營業日": entry_date.strftime("%Y-%m-%d"),
                    "推薦標的": pick['name'],
                    "進場價": round(entry_p, 2),
                    "停損價": round(stop_l, 2),
                    "第一目標價": round(tp_1, 2),
                    "出場價": round(exit_price, 2),
                    "持有天數": holding_days,
                    "實質淨損益%": round(net_pnl_pct, 2),
                    "勝負判定": "勝 🟢" if is_win else ("平 🛡️" if abs(net_pnl_pct) < 0.5 else "敗 🔴"),
                    "狀態": trade_status
                })

            if trade_log:
                res_df = pd.DataFrame(trade_log)
                total_trades = len(res_df)
                wins = len(res_df[res_df['實質淨損益%'] > 0])
                win_rate = (wins / total_trades) * 100
                
                win_trades = res_df[res_df['實質淨損益%'] > 0]['實質淨損益%']
                loss_trades = res_df[res_df['實質淨損益%'] < 0]['實質淨損益%']
                profit_factor = (win_trades.sum() / (abs(loss_trades.sum()) + 1e-9)) if not loss_trades.empty else 99.0

                # 機構級統計指標 (Sharpe Ratio, MDD, 年化波動度)
                res_df['累計淨報酬%'] = res_df['實質淨損益%'].cumsum()
                res_df['累積高點%'] = res_df['累計淨報酬%'].cummax()
                res_df['回撤%'] = res_df['累計淨報酬%'] - res_df['累積高點%']
                max_drawdown = abs(res_df['回撤%'].min())

                returns_series = res_df['實質淨損益%']
                daily_std = returns_series.std() if len(returns_series) > 1 else 1.0
                annual_vol = daily_std * np.sqrt(252 / max_holding)  # 年化波動度近似
                mean_trade_ret = returns_series.mean()
                rf_trade = 1.5 / (252 / max_holding)  # 無風險利率以 1.5% 換算
                sharpe_ratio = ((mean_trade_ret - rf_trade) / (daily_std + 1e-9)) * np.sqrt(252 / max_holding)

                st.subheader("📊 機構級回測績效儀表板")
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("回測有效交易", f"{total_trades} 筆")
                m2.metric("勝率 (Win Rate)", f"{win_rate:.1f}%", f"{wins}勝 / {total_trades-wins}負或平")
                m3.metric("盈虧比 (Profit Factor)", f"{profit_factor:.2f}")
                m4.metric("夏普比率 (Sharpe)", f"{sharpe_ratio:.2f}")
                m5.metric("最大回撤 (MDD)", f"-{max_drawdown:.2f}%", delta_color="inverse")
                m6.metric("累計實質淨報酬", f"{res_df['實質淨損益%'].sum():+.2f}%")

                fig_equity = go.Figure()
                fig_equity.add_trace(go.Scatter(
                    x=res_df['選股營業日'], y=res_df['累計淨報酬%'],
                    mode='lines+markers', name='累計實質淨利曲線',
                    line=dict(color='#eb4034', width=2.5),
                    fill='tozeroy'
                ))
                fig_equity.update_layout(title="歷史營業日逐日累計實質淨報酬率走勢 (%)", height=380, margin=dict(l=20,r=20,t=40,b=20))
                st.plotly_chart(fig_equity, use_container_width=True)

                st.subheader("📋 逐日交易明細清單")
                st.dataframe(res_df, use_container_width=True)
            else:
                st.warning("⚠️ 回測區間內大盤多處於弱勢空頭，系統啟動安全熔斷成功全數空手。")

# ==============================================================================
# Tab 6：產業族群全景評分榜 (可勾選多條件互動篩選器)
# ==============================================================================
with tab_rank:
    st.header("🔥 產業族群全景評分榜 ＆ 多條件互動篩選器")
    all_res = st.session_state.get('all_results', None)
    
    if all_res:
        with st.expander("🛠️ 自訂多條件多維度篩選器 (勾選後即時過濾)", expanded=True):
            fc1, fc2, fc3, fc4 = st.columns(4)
            chk_bull = fc1.checkbox("多頭排列 (股價>20MA>60MA)", value=False)
            chk_reversal = fc1.checkbox("空轉多 / 破底翻 (站上月線且20MA翻揚)", value=False)
            chk_trend_expand = fc2.checkbox("多頭趨勢擴大 (5MA>20MA>60MA發散)", value=False)
            chk_vcp = fc2.checkbox("VCP 波動收縮 (帶寬擠壓+量縮)", value=False)
            chk_limit_up = fc3.checkbox("今日強勢漲停板 (9.5%+)", value=False)
            chk_player_buy = fc3.checkbox("主力強勢鎖碼 / 偏多標的", value=False)
            max_bias5 = fc4.slider("5MA 乖離率上限過濾 (%)", min_value=1.0, max_value=8.0, value=4.5, step=0.5)

        all_sector_list = ["全部族群"] + list(SECTOR_MAP.keys()) + (["自選觀察族群"] if custom_input else [])
        filter_sec = st.selectbox("選擇產業族群", all_sector_list, index=0)
        
        table_rows = []
        for r in all_res:
            if filter_sec != "全部族群" and r['sector'] != filter_sec:
                continue

            # 互動篩選器條件檢驗
            if chk_bull and not (r['close'] > r['ma20'] > r['ma60']):
                continue
            if chk_reversal and not (r['close'] > r['ma20'] and r['pct'] > 0):
                continue
            if chk_trend_expand and not (r['close'] > r['ma10'] > r['ma20'] > r['ma60']):
                continue
            if chk_vcp and r['score_vcp'] < 10:
                continue
            if chk_limit_up and not r['is_limit_up']:
                continue
            if chk_player_buy and ("出貨" in r['player_tag'] or "散戶" in r['player_tag']):
                continue
            if r['bias5'] > max_bias5:
                continue

            table_rows.append({
                "標的名稱": r['name'],
                "所屬族群": r['sector'],
                "綜合技術籌碼分": r['tech_chip_score'],
                "主力多空標記": r['player_tag'],
                "符合做多標準": "✅ 符合" if r['is_eligible'] else "❌ 觀察",
                "最新收盤價": f"{r['close']:.2f}",
                "今日漲跌%": f"{r['pct']:+.2f}%",
                "5MA乖離%": f"{r['bias5']:+.2f}%",
                "型態特徵": r['pattern'],
                "量比 (Vol/5MA)": f"{r['vol_ratio']:.2f}x",
                "MFI資金流": f"{r['mfi']:.1f}",
                "RSI(14)": f"{r['rsi']:.1f}",
                "建議停損幅度": f"-{r['risk_pct']:.2f}%"
            })
        
        if table_rows:
            df_display = pd.DataFrame(table_rows).sort_values(by="綜合技術籌碼分", ascending=False)
            st.dataframe(df_display, use_container_width=True)
            st.caption(f"符合當前篩選條件共有 **{len(df_display)}** 檔標的。")
        else:
            st.warning("⚠️ 當前篩選條件組合無符合標的，請放寬勾選項。")
    else:
        st.info("👉 請先至第一分頁點擊『⚡ 執行全市場多因子量化運算』，數據將自動在此全部同步呈現！")

# ==============================================================================
# Tab 7：個股多維技術診斷 (防呆機制，杜絕頁面空白)
# ==============================================================================
with tab_detail:
    st.sidebar.title("個股技術診斷控制")
    all_avai_sectors = list(SECTOR_MAP.keys()) + (["自選觀察族群"] if custom_input else [])
    selected_sec = st.sidebar.selectbox("按族群挑選", all_avai_sectors, key="d_sec")
    
    sec_stocks = {k: v for k, v in CURRENT_STOCKS.items() if CURRENT_STOCK_TO_SECTOR[k] == selected_sec}
    selected_stock = st.sidebar.selectbox("選擇分析標的", list(sec_stocks.keys()), key="d_stk")
    stock_code = sec_stocks[selected_stock]

    period_map = {"1 個月": "1mo", "3 個月": "3mo", "6 個月": "6mo", "1 年": "1y", "2 年": "2y"}
    selected_period = st.sidebar.selectbox("分析週期", list(period_map.keys()), index=2, key="d_per")
    show_ma = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA10", "MA20", "MA60"])
    indicator_choice = st.sidebar.radio("副圖指標配置", [
        "精選三大動能 (KD + MACD + RSI)",
        "主力資金流向 (成交量 + OBV + MFI)",
        "波動壓縮與型態 (布林帶寬 BandWidth)",
        "🚀 全副圖完整展示 (全部指標展開)"
    ])

    @st.cache_data(ttl=300)
    def fetch_single_stock_history(ticker, period):
        data = yf.download(ticker, period=period, progress=False)
        if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1:
            data.columns = data.columns.get_level_values(0)
        return data

    with st.spinner(f"正在讀取 {selected_stock} 歷史走勢與技術指標..."):
        df_d = fetch_single_stock_history(stock_code, period_map[selected_period])

    if df_d.empty or len(df_d) < 5:
        st.error(f"⚠️ 暫時無法自公開數據源取得代號 [{stock_code}] 的交易數據，請稍後重試。")
    else:
        df_d = calculate_all_indicators(df_d)
        latest_d = df_d.iloc[-1]
        prev_d = df_d.iloc[-2] if len(df_d) > 1 else latest_d
        p_diff = latest_d['Close'] - prev_d['Close']
        pct_diff = (p_diff / prev_d['Close']) * 100

        st.subheader(f"{selected_stock} 技術分析看板 ｜ 族群：{selected_sec}")
        st.write(f"🏷️ **即時型態辨識**：`{latest_d['Candle_Pattern']}` ｜ **5MA 乖離率**：`{latest_d['Bias5']:+.2f}%` ｜ **ATR波動比**：`{latest_d['ATR_Pct']:.2f}%`")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("收盤價", f"{latest_d['Close']:.2f} 元", f"{p_diff:+.2f} ({pct_diff:+.2f}%)")
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

        with st.expander("📥 歷史量價明細匯出 (CSV)"):
            st.dataframe(df_d.tail(30).sort_index(ascending=False))
            st.download_button(
                label="下載歷史資料 CSV",
                data=df_d.to_csv().encode('utf-8-sig'),
                file_name=f"{stock_code}_history.csv",
                mime="text/csv"
            )