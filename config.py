import streamlit as st

DARK_NEON_CSS = """
<style>
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #080c14 !important;
        color: #ffffff !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background-color: #0b0f19 !important;
        border-right: 1px solid rgba(79, 172, 254, 0.25) !important;
    }
    p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        font-weight: 500;
    }
    div[data-baseweb="select"] > div {
        background-color: #0f172a !important;
        color: #ffffff !important;
        border: 1px solid #334155 !important;
    }
    div[data-baseweb="popover"], div[data-baseweb="menu"], ul[data-baseweb="menu"] {
        background-color: #0b1120 !important;
        border: 1px solid #38bdf8 !important;
    }
    li[data-baseweb="menu-item"] {
        background-color: #0b1120 !important;
        color: #ffffff !important;
    }
    li[data-baseweb="menu-item"]:hover {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
    }
    div.stButton > button {
        background: #080c14 !important;
        color: #ffffff !important;
        border: 2px solid transparent !important;
        border-radius: 9999px !important;
        padding: 0.65rem 2.4rem !important;
        font-weight: 700 !important;
        background-image: linear-gradient(#080c14, #080c14), linear-gradient(90deg, #00f2fe, #4facfe, #fa709a, #fee140) !important;
        background-origin: border-box !important;
        background-clip: padding-box, border-box !important;
        box-shadow: 0 0 18px rgba(79, 172, 254, 0.5) !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 0 28px rgba(254, 225, 64, 0.7) !important;
    }
    .stock-card {
        background-color: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.5);
    }
    .stock-card-top1 {
        background-color: #0f172a;
        border: 2px solid #38bdf8;
        border-radius: 18px;
        padding: 22px;
        margin-bottom: 22px;
        box-shadow: 0 0 25px rgba(56, 189, 248, 0.25);
    }
    .tag-badge {
        display: inline-block;
        background-color: #082f49;
        color: #38bdf8 !important;
        border: 1px solid #0284c7;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 4px;
    }
    .rating-box {
        display: flex;
        justify-content: space-around;
        background-color: #060a12;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 10px 4px;
        margin-top: 12px;
        text-align: center;
    }
</style>
"""

SECTOR_DASHBOARD_DB = {
    "重電綠能與強韌電網": [
        ("1513", "中興電", "TW", ["儲能電池", "離岸風電", "重電電纜"]),
        ("1609", "大亞", "TW", ["儲能電池", "重電電纜", "超導電網"]),
        ("1519", "華城", "TW", ["外銷變壓器", "強韌電網", "重電綠能"]),
        ("1503", "士電", "TW", ["重電設備", "車用電裝", "綠能充電"]),
        ("1514", "亞力", "TW", ["台電強韌", "半導體變配電", "綠能逆變器"]),
        ("2371", "大同", "TW", ["重電馬達", "電力電纜", "資產開發"])
    ],
    "CPO 矽光子與光通訊": [
        ("3450", "聯鈞", "TW", ["矽光子CPO", "光收發模組", "800G傳輸"]),
        ("3363", "上詮", "TWO", ["光纖熔接", "CPO封裝", "台積電生態"]),
        ("3081", "聯亞", "TWO", ["磷化銦雷射", "光通訊晶片", "矽光發射源"]),
        ("4979", "華星光", "TWO", ["連續光收發", "資料中心", "800G規格"]),
        ("6442", "光聖", "TW", ["高階光被動", "美國基建", "數據中心"]),
        ("4977", "眾達-KY", "TW", ["博通供應鏈", "CPO模組", "超高速互聯"])
    ],
    "散熱模組與水冷系統": [
        ("3017", "奇鋐", "TW", ["水冷板", "散熱模組", "伺服器散熱"]),
        ("3324", "雙鴻", "TW", ["水冷液冷", "CDU分流器", "水冷均熱板"]),
        ("3653", "健策", "TW", ["均熱片", "水冷散熱", "車用晶片散熱"]),
        ("8996", "高力", "TW", ["板式熱交換", "水冷歧管", "BloomEnergy"]),
        ("6230", "尼得科超眾", "TW", ["薄型熱導管", "伺服器水冷", "日本Nidec"]),
        ("3483", "力致", "TWO", ["水冷散熱模組", "浸沒式散熱", "風扇組件"])
    ],
    "AI 伺服器與硬體代工": [
        ("2382", "廣達", "TW", ["AI伺服器", "GB200組裝", "雲端硬體"]),
        ("3231", "緯創", "TW", ["GPU基板", "AI伺服器", "Dell/HP供應"]),
        ("2376", "技嘉", "TW", ["AI伺服器", "高效能主板", "自研水冷"]),
        ("6669", "緯穎", "TW", ["Meta供應鏈", "ASIC伺服器", "雲端IDC"]),
        ("2059", "川湖", "TW", ["伺服器滑軌", "GB200專用滑軌", "極致毛利"]),
        ("8210", "勤誠", "TW", ["伺服器機殼", "高U數機箱", "客製化結構"])
    ],
    "PCB、載板與 CCL": [
        ("2383", "台光電", "TW", ["無鹵CCL", "AI伺服器板", "交換器材料"]),
        ("3037", "欣興", "TW", ["ABF載板", "高階HDI", "CoWoS基板"]),
        ("2368", "金像電", "TW", ["高多層板", "AI伺服器PCB", "網通主板"]),
        ("6274", "台燿", "TW", ["極低損耗CCL", "800G交換器", "AI伺服器"]),
        ("3189", "景碩", "TW", ["ABF載板", "BT載板", "記憶體載板"]),
        ("8046", "南電", "TW", ["覆晶載板", "高階IC封裝", "半導體基板"])
    ],
    "記憶體模組與控制晶片": [
        ("8299", "群聯", "TWO", ["SSD控制IC", "PCIe Gen5", "NAND儲存"]),
        ("3260", "威剛", "TWO", ["DRAM模組", "電競SSD", "工控儲存"]),
        ("4967", "十銓", "TW", ["高頻超頻模組", "DDR5顆粒", "電競市場"]),
        ("2408", "南亞科", "TW", ["DRAM顆粒", "1B製程研發", "伺服器記憶體"]),
        ("2344", "華邦電", "TW", ["NOR Flash", "利基型DRAM", "先進封裝"]),
        ("3006", "晶豪科", "TW", ["利基型記憶體", "物聯網晶片", "車用DRAM"])
    ],
    "半導體製造與設備": [
        ("2330", "台積電", "TW", ["先進製程", "CoWoS封裝", "晶圓代工"]),
        ("2303", "聯電", "TW", ["成熟製程", "特殊高壓製程", "車用晶片"]),
        ("3583", "辛耘", "TW", ["先進濕製程", "設備翻新", "CoWoS關鍵"]),
        ("3131", "弘塑", "TWO", ["濕式清洗機", "單晶圓蝕刻", "封裝龍頭"]),
        ("6223", "旺矽", "TWO", ["懸臂探針卡", "垂直探針卡", "測試治具"]),
        ("1560", "中砂", "TW", ["鑽石碟", "再生晶圓", "3奈米耗材"])
    ],
    "機器人自動化與智慧工具機": [
        ("2359", "所羅門", "TW", ["機器視覺AI", "輝達黃仁勳點名", "3D視覺"]),
        ("2365", "昆盈", "TW", ["光學感測", "電腦周邊", "AI外設整合"]),
        ("6188", "廣明", "TWO", ["達明機器人", "協作型機器手臂", "智慧工廠"]),
        ("8374", "羅昇", "TW", ["智動化傳動", "機械手臂代理", "綠能控制"]),
        ("2049", "上銀", "TW", ["滾珠螺桿", "線性滑軌", "機器人關節"]),
        ("4583", "台灣精銳", "TW", ["精密減速機", "伺服驅動", "機器人核心"])
    ]
}

CODE_TO_NAME = {}
NAME_TO_CODE = {}
CODE_TO_SUFFIX = {}
TAGS_MAP = {}
CONCEPT_TO_STOCKS = {}

for sec, stk_list in SECTOR_DASHBOARD_DB.items():
    for sym, cname, sfx, tags in stk_list:
        clean_code = sym.strip()
        CODE_TO_NAME[clean_code] = cname
        NAME_TO_CODE[cname] = clean_code
        CODE_TO_SUFFIX[clean_code] = f"{clean_code}.{sfx}"
        TAGS_MAP[clean_code] = tags
        for t in tags:
            if t not in CONCEPT_TO_STOCKS: CONCEPT_TO_STOCKS[t] = []
            CONCEPT_TO_STOCKS[t].append(f"{cname} ({clean_code})")

EXPANDED_NAMES = [
    ("1558", "伸興", "TW", ["縫紉機製造", "家用機械", "全球外銷"]),
    ("2221", "大甲", "TW", ["不銹鋼焊接", "半導體管件", "潔淨管"]),
    ("8201", "無敵", "TW", ["車用電子倒車", "電子字典轉型", "雲端硬體"]),
    ("6117", "迎廣", "TW", ["伺服器水冷機殼", "機房機箱", "模組化設計"]),
    ("2358", "廷鑫", "TW", ["鋁合金棒", "皮件製造", "低基期轉機"]),
    ("2243", "宏旭-KY", "TW", ["車身模具", "電動車鈑件", "外資持股"]),
    ("6133", "金橋", "TW", ["高頻高速線纜", "5G傳輸", "天線組件"]),
    ("2424", "隴華", "TW", ["海上衛星寬頻", "網通設備", "船舶連網"]),
    ("2431", "聯昌", "TW", ["電源供應器", "東元集團", "綠能充電"]),
    ("5328", "華容", "TWO", ["塑膠薄膜電容", "被動元件", "車用濾波"]),
    ("2429", "銘旺科", "TW", ["光學面板加工", "綠能整合", "轉機概念"]),
    ("2454", "聯發科", "TW", ["天璣旗艦晶片", "邊緣AI", "手機AP"]),
    ("3661", "世芯-KY", "TW", ["ASIC晶片", "雲端晶片", "客製化設計"]),
    ("3443", "創意", "TW", ["台積電IP", "先進封裝設計", "HBM3介面"]),
    ("3529", "力旺", "TWO", ["邏輯非揮發記憶體", "純矽智財", "高毛利"]),
    ("6643", "M31", "TWO", ["基礎元件IP", "高速傳輸介面", "製程微縮"])
]
for sym, cname, sfx, tags in EXPANDED_NAMES:
    clean_code = sym.strip()
    full_code = f"{clean_code}.{sfx}"
    CODE_TO_NAME[clean_code] = cname
    NAME_TO_CODE[cname] = clean_code
    CODE_TO_SUFFIX[clean_code] = full_code
    TAGS_MAP[clean_code] = tags

for p in range(1101, 9965):
    c_str = str(p)
    if c_str not in CODE_TO_NAME:
        cname = "台股標的"
        CODE_TO_NAME[c_str] = cname
        NAME_TO_CODE[f"{cname}{c_str}"] = c_str
        CODE_TO_SUFFIX[c_str] = f"{c_str}.TWO" if (3000 <= p < 7000 and p not in [2330, 2454, 2382, 2376, 2317, 3008, 3034, 3037, 3044, 3017, 3231, 3450, 3661, 3711, 4938, 4958, 6669]) else f"{c_str}.TW"
        TAGS_MAP[c_str] = ["台股上市櫃", "全市場量化池"]
    if len(CODE_TO_NAME) >= 1260:
        break
