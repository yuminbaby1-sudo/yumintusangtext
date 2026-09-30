"""
台股量化操盤決策系統 v2（單檔版）
執行：pip install streamlit yfinance pandas numpy plotly requests lxml html5lib beautifulsoup4 tzdata
      streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import re
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================================
# A. 資料來源層
# ============================================================================
TZ = ZoneInfo("Asia/Taipei")
UA = {"User-Agent": "Mozilla/5.0 (compatible; tw-quant/1.0)"}
try:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
except Exception:
    pass


def now_tw() -> dt.datetime:
    return dt.datetime.now(TZ)


def _get(url: str, params: dict | None = None, timeout: int = 25) -> requests.Response:
    last = None
    for verify in (True, False):   # 部分政府網站憑證鏈在新版 Python 會驗證失敗
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout, verify=verify)
            r.raise_for_status()
            return r
        except requests.exceptions.SSLError as e:
            last = e
            continue
        except Exception as e:
            last = e
            break
    raise last  # type: ignore[misc]


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return np.nan


# ----------------------------------------------------------------------------
def load_universe():
    rows, msgs = [], []
    for mode, sfx in ((2, "TW"), (4, "TWO")):
        try:
            r = _get("https://isin.twse.com.tw/isin/C_public.jsp", params={"strMode": mode})
            tbl = pd.read_html(io.StringIO(r.content.decode("big5", errors="ignore")))[0]
            if not any("有價證券" in str(c) for c in tbl.columns):
                tbl.columns = tbl.iloc[0]
                tbl = tbl.iloc[1:]
            cols = [str(c) for c in tbl.columns]
            tbl.columns = cols
            c0 = next((c for c in cols if "有價證券代號" in c), cols[0])
            c_ind = next((c for c in cols if "產業別" in c), None)
            c_cfi = next((c for c in cols if "CFI" in c.upper()), None)
            for _, row in tbl.iterrows():
                cell = str(row[c0])
                if "\u3000" not in cell:
                    continue
                code, name = cell.split("\u3000", 1)
                code = code.strip()
                if not re.fullmatch(r"\d{4}", code):
                    continue
                if c_cfi:
                    cfi = str(row[c_cfi])
                    if cfi not in ("nan", "") and not cfi.startswith("ES"):
                        continue
                rows.append(dict(code=code, name=name.strip(), market=sfx,
                                 industry=str(row[c_ind]) if c_ind else ""))
        except Exception as e:
            msgs.append(f"股票清單（{'上市' if mode == 2 else '上櫃'}）抓取失敗：{e}")
    df = pd.DataFrame(rows).drop_duplicates("code") if rows else pd.DataFrame(columns=["code", "name", "market", "industry"])
    if not df.empty:
        msgs.append(f"股票清單：上市 {int((df.market == 'TW').sum())} 檔、上櫃 {int((df.market == 'TWO').sum())} 檔")
    return df, msgs


def load_daily_turnover():
    out, msgs = {}, []
    try:
        js = _get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL").json()
        for r in js:
            out[str(r.get("Code", "")).strip()] = _num(r.get("TradeValue"))
        msgs.append(f"上市當日成交值：{len(js)} 檔")
    except Exception as e:
        msgs.append(f"上市當日成交值抓取失敗：{e}")
    try:
        js = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes").json()
        n = 0
        for r in js:
            ck = next((k for k in r if "Code" in k), None)
            ak = next((k for k in r if "Amount" in k), None)
            if ck and ak:
                out[str(r[ck]).strip()] = _num(r[ak])
                n += 1
        msgs.append(f"上櫃當日成交值：{n} 檔")
    except Exception as e:
        msgs.append(f"上櫃當日成交值抓取失敗：{e}")
    return pd.Series(out, dtype=float).dropna(), msgs


def load_institutional(n_days: int = 5):
    """上市三大法人近 n 個交易日買賣超股數（加總）。上櫃暫無來源，UI 會顯示『無資料』。"""
    msgs, frames, used = [], [], []
    day = now_tw().date()
    attempts = 0
    while len(used) < n_days and attempts < 16:
        attempts += 1
        if day.weekday() < 5:
            try:
                js = _get("https://www.twse.com.tw/rwd/zh/fund/T86",
                          params={"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"}).json()
                if js.get("stat") == "OK" and js.get("data"):
                    f = js["fields"]
                    i_code = next(i for i, x in enumerate(f) if "證券代號" in x)
                    i_for = next(i for i, x in enumerate(f) if x.startswith("外陸資買賣超") or ("外資" in x and "買賣超" in x))
                    i_trust = next(i for i, x in enumerate(f) if x.startswith("投信買賣超"))
                    i_tot = next(i for i, x in enumerate(f) if x.startswith("三大法人買賣超"))
                    df = pd.DataFrame([[r[i_code].strip(), _num(r[i_for]), _num(r[i_trust]), _num(r[i_tot])]
                                       for r in js["data"]], columns=["code", "foreign", "trust", "total"])
                    frames.append(df)
                    used.append(day)
                time.sleep(0.5)
            except Exception as e:
                msgs.append(f"T86 {day} 失敗：{e}")
        day -= dt.timedelta(days=1)
    if not frames:
        msgs.append("三大法人資料抓取失敗，籌碼欄位將顯示『無資料』。")
        return pd.DataFrame(columns=["foreign", "trust", "total"]), [], msgs
    out = pd.concat(frames).groupby("code")[["foreign", "trust", "total"]].sum()
    msgs.append(f"三大法人（上市）：{len(used)} 個交易日 {min(used)}~{max(used)}")
    return out, used, msgs


def load_revenue_yoy():
    out, msgs = {}, []
    urls = ["https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"]
    for u in urls:
        try:
            js = _get(u).json()
            n = 0
            for r in js:
                ck = next((k for k in r if "公司代號" in k or k.lower().endswith("code")), None)
                yk = next((k for k in r if "去年同月增減" in k), None)
                if ck and yk:
                    out[str(r[ck]).strip()] = _num(r[yk])
                    n += 1
            msgs.append(f"月營收 YoY：{n} 檔（{'上市' if 'twse' in u else '上櫃'}）")
        except Exception as e:
            msgs.append(f"月營收抓取失敗（{'上市' if 'twse' in u else '上櫃'}）：{e}")
    return pd.Series(out, dtype=float), msgs


def load_flags():
    punish, notice, msgs = set(), set(), []
    for name, url, bucket in (("處置股", "https://openapi.twse.com.tw/v1/announcement/punish", punish),
                              ("注意股", "https://openapi.twse.com.tw/v1/announcement/notice", notice)):
        try:
            for r in _get(url).json():
                ck = next((k for k in r if k.lower().endswith("code") or "代號" in k), None)
                if ck:
                    bucket.add(str(r[ck]).strip())
            msgs.append(f"{name}（上市）：{len(bucket)} 檔")
        except Exception as e:
            msgs.append(f"{name}抓取失敗：{e}")
    return punish, notice, msgs


# ----------------------------------------------------------------------------
def download_prices(tickers: list[str], period: str = "3y", chunk: int = 100) -> dict:
    import yfinance as yf

    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            raw = yf.download(part, period=period, group_by="ticker", auto_adjust=True,
                              threads=True, progress=False)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = set(raw.columns.get_level_values(0))
            if "Close" in lvl0 and len(part) == 1:          # 單檔時層級可能反過來
                frames = {part[0]: raw.copy()}
                frames[part[0]].columns = frames[part[0]].columns.get_level_values(0)
            else:
                frames = {t: raw[t] for t in part if t in lvl0}
        else:
            frames = {part[0]: raw}
        for t, df in frames.items():
            try:
                df = df.dropna(how="all")
                df = df[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]]
                if df.shape[1] < 5 or len(df) < 120:
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                out[t] = df[~df.index.duplicated(keep="last")].sort_index()
            except Exception:
                continue
    return out


def links(code: str, market: str = "TW") -> dict:
    tv = "TPEX" if market == "TWO" else "TWSE"
    return {
        "Yahoo 股市": f"https://tw.stock.yahoo.com/quote/{code}",
        "Goodinfo": f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={code}",
        "玩股網": f"https://www.wantgoo.com/stock/{code}",
        "TradingView": f"https://tw.tradingview.com/chart/?symbol={tv}%3A{code}",
        "公開資訊觀測站": f"https://mops.twse.com.tw/mops/web/t05st01?co_id={code}",
    }


# ============================================================================
# B. 量化引擎
# ============================================================================
TRADING_DAYS = 252


# ----------------------------------------------------------------------------
# 台股升降單位
# ----------------------------------------------------------------------------
def tick_size(p: float) -> float:
    if p < 10:
        return 0.01
    if p < 50:
        return 0.05
    if p < 100:
        return 0.1
    if p < 500:
        return 0.5
    if p < 1000:
        return 1.0
    return 5.0


def tick_round(p: float, mode: str = "nearest") -> float:
    t = tick_size(p)
    n = p / t
    if mode == "down":
        n = np.floor(n + 1e-9)
    elif mode == "up":
        n = np.ceil(n - 1e-9)
    else:
        n = np.round(n)
    return round(float(n * t), 2)


# ----------------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Costs:
    fee_rate: float = 0.001425   # 公定手續費
    fee_disc: float = 0.6        # 券商折扣（0.6 = 6 折）
    tax: float = 0.003           # 證交稅（賣出）
    slip: float = 0.001          # 單邊滑價

    @property
    def fee(self) -> float:
        return self.fee_rate * self.fee_disc

    @property
    def round_trip(self) -> float:
        return 2 * self.fee + self.tax + 2 * self.slip


@dataclass(frozen=True)
class Filters:
    min_price: float = 35.0
    min_turnover: float = 1.5e8   # 5 日均成交值 (TWD)
    min_amp: float = 8.0          # 20 日振幅 %
    bias5_max: float = 3.5
    bias20_max: float = 10.0


@dataclass(frozen=True)
class Params:
    preset: str = "均衡"
    min_score: float = 65.0
    stop_atr: float = 2.0
    tp_r: float = 2.0
    hold: int = 10

    def label(self) -> str:
        return (f"{self.preset}｜門檻{self.min_score:.0f}｜停損{self.stop_atr}ATR｜"
                f"停利{self.tp_r}R｜持股≤{self.hold}日")


# 四大類特徵的權重預設（不再是拍腦袋固定 75/20/5，而是交給 walk-forward 選）
PRESETS = {
    "均衡":     {"trend": 0.30, "compress": 0.20, "mom": 0.20, "rs": 0.30},
    "趨勢型":   {"trend": 0.40, "compress": 0.15, "mom": 0.20, "rs": 0.25},
    "強勢動能": {"trend": 0.20, "compress": 0.10, "mom": 0.30, "rs": 0.40},
}
DEFAULT_GRID = dict(
    preset=list(PRESETS),
    min_score=[55, 65, 75],
    stop_atr=[1.5, 2.0, 2.5],
    tp_r=[1.5, 2.0, 3.0],
    hold=[10, 15],
)


# ----------------------------------------------------------------------------
# 指標（單一標的）
# ----------------------------------------------------------------------------
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    d["Volume"] = d["Volume"].fillna(0.0)
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]

    for n in (5, 10, 20, 60):
        d[f"MA{n}"] = c.rolling(n).mean()
    d["MA20_slope5"] = d["MA20"] / d["MA20"].shift(5) - 1
    d["EMA10"] = c.ewm(span=10, adjust=False).mean()
    d["Vol_MA5"] = v.rolling(5).mean()
    d["Vol_MA20"] = v.rolling(20).mean()
    d["Turnover_MA5"] = (c * v).rolling(5).mean()
    d["Amp20"] = (h.rolling(20).max() / l.rolling(20).min() - 1) * 100
    for n in (5, 20, 60):
        d[f"Bias{n}"] = (c / d[f"MA{n}"] - 1) * 100

    std20 = c.rolling(20).std()
    d["BB_Width"] = 4 * std20 / d["MA20"]
    d["BB_Pct"] = d["BB_Width"].rolling(60).rank(pct=True)  # 帶寬在近60日的分位，越低越收斂

    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()  # Wilder

    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    d["RSI"] = 100 - 100 / (1 + ag / (al + 1e-12))

    rng9 = h.rolling(9).max() - l.rolling(9).min()
    rsv = ((c - l.rolling(9).min()) / (rng9 + 1e-9) * 100).fillna(50)
    d["K"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d["D"] = d["K"].ewm(alpha=1 / 3, adjust=False).mean()

    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["MACD_Hist"] = dif - dif.ewm(span=9, adjust=False).mean()

    clv = ((c - l) - (h - c)) / (h - l + 1e-9)
    d["CLV5"] = (clv * v).rolling(5).sum() / (v.rolling(5).sum() + 1e-9)  # 量價代理，非真實籌碼

    tp = (h + l + c) / 3
    rmf = tp * v
    pos = rmf.where(tp > tp.shift(1), 0.0).rolling(14).sum()
    neg = rmf.where(tp < tp.shift(1), 0.0).rolling(14).sum()
    d["MFI"] = 100 - 100 / (1 + pos / (neg + 1e-9))

    d["Range5"] = (h.rolling(5).max() - l.rolling(5).min()) / c * 100
    d["Low5"] = l.rolling(5).min()
    d["High20_prev"] = h.rolling(20).max().shift(1)
    d["pct"] = c.pct_change() * 100
    return d


PANEL_FIELDS = [
    "Open", "High", "Low", "Close", "Volume", "MA5", "MA10", "MA20", "MA60",
    "MA20_slope5", "EMA10", "Vol_MA5", "Vol_MA20", "Turnover_MA5", "Amp20",
    "Bias5", "Bias20", "BB_Pct", "ATR", "RSI",
    "K", "D", "MACD_Hist", "MFI", "CLV5", "Range5", "Low5", "High20_prev", "pct",
]


def build_panel(stock_dfs: dict) -> dict:
    """code -> indicator df  ==>  field -> DataFrame(date x code)"""
    P = {}
    for f in PANEL_FIELDS:
        P[f] = pd.concat({code: df[f] for code, df in stock_dfs.items()}, axis=1).sort_index()
    return P


# ----------------------------------------------------------------------------
# 特徵 / 分數 / 過濾
# ----------------------------------------------------------------------------
def compute_features(P: dict, bench_close: pd.Series) -> dict:
    C = P["Close"]
    Cf = C.ffill()
    b = bench_close.reindex(C.index).ffill()
    rs20 = (Cf / Cf.shift(20) - 1).sub(b / b.shift(20) - 1, axis=0)
    rs60 = (Cf / Cf.shift(60) - 1).sub(b / b.shift(60) - 1, axis=0)

    f = {}
    f["trend"] = 0.25 * ((C > P["MA20"]).astype(float) + (P["MA20"] > P["MA60"]).astype(float)
                         + (P["MA20_slope5"] > 0).astype(float) + (P["EMA10"] > P["MA20"]).astype(float))
    f["compress"] = 0.6 * (1 - P["BB_Pct"]) + 0.4 * (P["Range5"] < 6).astype(float)
    vol_up = ((P["Volume"] > P["Vol_MA5"] * 1.2) & (C > P["Open"])).astype(float)
    f["mom"] = (0.3 * ((P["RSI"] >= 50) & (P["RSI"] <= 70)).astype(float)
                + 0.3 * (P["MACD_Hist"] > 0).astype(float)
                + 0.2 * ((P["K"] > P["D"]) & (P["K"] >= 50) & (P["K"] <= 82)).astype(float)
                + 0.2 * vol_up)
    rs = 0.6 * rs20 + 0.4 * rs60
    f["rs"] = (rs / 0.2).clip(-1, 1) * 0.5 + 0.5
    return f


def composite_score(feats: dict, preset: str) -> pd.DataFrame:
    w = PRESETS[preset]
    tot = sum(w.values())
    return sum(feats[k] * v for k, v in w.items()) / tot * 100


def universe_masks(P: dict, flt: Filters):
    C = P["Close"]
    liquid = ((C > flt.min_price) & (P["Turnover_MA5"] >= flt.min_turnover) & (P["Amp20"] >= flt.min_amp)
              & (P["Volume"] > 0) & P["MA60"].notna() & P["ATR"].notna())
    trend_ok = (C > P["MA20"]) & (C > P["MA60"]) & (P["MA20_slope5"] > -0.005)
    heat_ok = (P["Bias5"] <= flt.bias5_max) & (P["Bias20"] <= flt.bias20_max)
    return liquid, liquid & trend_ok & heat_ok


def regime_array(bench_close: pd.Series, idx) -> np.ndarray:
    b = bench_close.reindex(idx).ffill()
    ma20, ma60 = b.rolling(20).mean(), b.rolling(60).mean()
    ok = (~((b < ma20) & (b < ma60))) & ma60.notna()
    return ok.to_numpy()


# ----------------------------------------------------------------------------
# 交易計畫（回測與即時推薦共用同一套邏輯）
# ----------------------------------------------------------------------------
def plan_trade(fill: float, atr: float, low5: float, stop_atr: float, tp_r: float):
    stop_raw = fill - stop_atr * atr
    struct = low5 * 0.99
    stop = max(stop_raw, struct)
    risk = float(np.clip((fill - stop) / fill, 0.03, 0.10))
    stop = tick_round(fill * (1 - risk))
    R = fill - stop
    tp = tick_round(fill + tp_r * R)
    return stop, tp, R


def size_position(capital: float, risk_pct: float, entry: float, stop: float, max_alloc: float = 0.25) -> dict:
    per_share = max(entry - stop, 1e-9)
    by_risk = int(capital * risk_pct / 100.0 / per_share)
    by_alloc = int(capital * max_alloc / entry)
    shares = max(0, min(by_risk, by_alloc))
    return dict(shares=shares, lots=shares // 1000, odd=shares % 1000, amount=shares * entry,
                pct_capital=shares * entry / capital * 100 if capital else 0.0,
                risk_amt=shares * per_share, binding="風險上限" if by_risk <= by_alloc else "單檔25%資金上限")


# ----------------------------------------------------------------------------
# 引擎：把面板、分數、遮罩與排名打包
# ----------------------------------------------------------------------------
class Engine:
    def __init__(self, P: dict, bench_close: pd.Series, flt: Filters, costs: Costs, capital: float = 1_000_000.0):
        self.P, self.flt, self.costs, self.capital = P, flt, costs, capital
        self.idx = P["Close"].index
        self.codes = list(P["Close"].columns)
        self.feats = compute_features(P, bench_close)
        self.scores = {k: composite_score(self.feats, k) for k in PRESETS}
        self.liquid, self.elig = universe_masks(P, flt)
        self.regime = regime_array(bench_close, self.idx)
        self.bench_close = bench_close
        C = P["Close"]
        self.arr = dict(O=P["Open"].to_numpy(), H=P["High"].to_numpy(), L=P["Low"].to_numpy(),
                        C=C.to_numpy(), Cf=C.ffill().to_numpy(), ATR=P["ATR"].to_numpy(),
                        LOW5=P["Low5"].to_numpy())
        self._rank_cache = {}

    def ranks(self, preset: str, min_score: float, topk: int = 6):
        key = (preset, float(min_score), topk)
        if key not in self._rank_cache:
            S = self.scores[preset].where(self.elig & (self.scores[preset] >= min_score)).to_numpy()
            filled = np.where(np.isnan(S), -np.inf, S)
            order = np.argsort(-filled, axis=1)[:, :topk]
            vals = np.take_along_axis(S, order, axis=1)
            self._rank_cache[key] = (order, vals)
        return self._rank_cache[key]


# ----------------------------------------------------------------------------
# 模擬器
# ----------------------------------------------------------------------------
def simulate(eng: Engine, params: Params, start: int, end: int, max_pos: int = 4):
    A = eng.arr
    O, H, L, C, Cf, ATR, LOW5 = A["O"], A["H"], A["L"], A["C"], A["Cf"], A["ATR"], A["LOW5"]
    order, valid = eng.ranks(params.preset, params.min_score)
    reg, costs = eng.regime, eng.costs
    fee, slip, tax = costs.fee, costs.slip, costs.tax
    init = eng.capital
    cash, pos, trades, eq_vals, eq_idx = init, [], [], [], []
    start = max(start, 1)
    end = min(end, len(eng.idx))

    def close_pos(p, d, px, reason):
        nonlocal cash
        cash += p["sh"] * px * (1 - slip - fee - tax)
        net = (px * (1 - slip - fee - tax) / (p["fill"] * (1 + fee)) - 1) * 100
        trades.append(dict(code=eng.codes[p["j"]], entry_date=eng.idx[p["d0"]], exit_date=eng.idx[d],
                           fill=p["fill"], exit=px, reason=reason, days=d - p["d0"] + 1,
                           net_pct=net, r_mult=(px - p["fill"]) / p["R"]))

    for d in range(start, end):
        # 1) 開盤進場（訊號來自前一日收盤）
        if len(pos) < max_pos and reg[d - 1]:
            held = {p["j"] for p in pos}
            for k in range(order.shape[1]):
                if np.isnan(valid[d - 1, k]):
                    break
                j = int(order[d - 1, k])
                if j in held:
                    continue
                o, pc, atr, low5 = O[d, j], C[d - 1, j], ATR[d - 1, j], LOW5[d - 1, j]
                if np.isnan(o) or np.isnan(pc) or np.isnan(atr) or np.isnan(low5):
                    continue
                if o / pc - 1 >= 0.09:      # 開盤鎖漲停，買不到
                    continue
                fill = o * (1 + slip)
                stop, tp, R = plan_trade(fill, atr, low5, params.stop_atr, params.tp_r)
                equity = cash + sum(p["sh"] * Cf[d - 1, p["j"]] for p in pos)
                alloc = min(equity / max_pos, cash)
                sh = int(alloc / (fill * (1 + fee)))
                if sh <= 0:
                    continue
                cash -= sh * fill * (1 + fee)
                pos.append(dict(j=j, d0=d, fill=fill, stop=stop, tp=tp, R=R, sh=sh))
                break

        # 2) 盤中出場（停損優先於停利；保守）
        for p in list(pos):
            j = p["j"]
            o, h, l, c = O[d, j], H[d, j], L[d, j], C[d, j]
            if np.isnan(c):
                continue
            px = reason = None
            if o <= p["stop"]:
                px, reason = o, "跳空停損"
            elif l <= p["stop"]:
                px = p["stop"]
                reason = "停損" if p["stop"] < p["fill"] else "保本出場"
            elif o >= p["tp"]:
                px, reason = o, "跳空達標"
            elif h >= p["tp"]:
                px, reason = p["tp"], "達標停利"
            elif d - p["d0"] + 1 >= params.hold:
                px, reason = c, "期滿出場"
            if px is not None:
                close_pos(p, d, px, reason)
                pos.remove(p)
            elif h >= p["fill"] + 1.2 * p["R"]:
                p["stop"] = max(p["stop"], tick_round(p["fill"] * 1.006))   # 隔日起生效

        eq_vals.append(cash + sum(p["sh"] * Cf[d, p["j"]] for p in pos))
        eq_idx.append(eng.idx[d])

    for p in list(pos):  # 視窗結束強制平倉
        close_pos(p, end - 1, Cf[end - 1, p["j"]], "視窗結束")
    if eq_vals:
        eq_vals[-1] = cash
    equity = pd.Series(eq_vals, index=eq_idx, dtype=float) / init
    return pd.DataFrame(trades), equity


# ----------------------------------------------------------------------------
# 績效統計
# ----------------------------------------------------------------------------
def _wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    ctr = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (ctr - half) * 100, (ctr + half) * 100


def summarize(trades: pd.DataFrame, equity: pd.Series | None = None) -> dict:
    s = dict(n=len(trades), win_rate=np.nan, avg_win=np.nan, avg_loss=np.nan, payoff=np.nan, expectancy=np.nan,
             profit_factor=np.nan, tstat=np.nan, wr_lo=np.nan, wr_hi=np.nan, max_consec_loss=0, avg_hold=np.nan,
             total_ret=np.nan, cagr=np.nan, mdd=np.nan, sharpe=np.nan, exp_lo=np.nan, exp_hi=np.nan)
    if len(trades):
        r = trades["net_pct"].to_numpy()
        n = len(r)
        wins, losses = r[r > 0], r[r <= 0]
        s["win_rate"] = len(wins) / n * 100
        s["avg_win"] = wins.mean() if len(wins) else 0.0
        s["avg_loss"] = losses.mean() if len(losses) else 0.0
        s["payoff"] = abs(s["avg_win"] / s["avg_loss"]) if s["avg_loss"] < 0 else np.nan
        s["expectancy"] = r.mean()
        s["profit_factor"] = wins.sum() / abs(losses.sum()) if losses.sum() < 0 else np.nan
        sd = r.std(ddof=1) if n > 1 else np.nan
        s["tstat"] = r.mean() / (sd / np.sqrt(n)) if (n > 1 and sd and sd > 0) else np.nan
        s["wr_lo"], s["wr_hi"] = _wilson(len(wins), n)
        run = best = 0
        for x in r:
            run = run + 1 if x <= 0 else 0
            best = max(best, run)
        s["max_consec_loss"] = best
        s["avg_hold"] = trades["days"].mean()
        if n >= 5:
            rng = np.random.default_rng(7)
            bs = rng.choice(r, size=(2000, n), replace=True).mean(axis=1)
            s["exp_lo"], s["exp_hi"] = np.percentile(bs, [5, 95])
    if equity is not None and len(equity) > 1:
        s["total_ret"] = (equity.iloc[-1] - 1) * 100
        s["mdd"] = abs((equity / equity.cummax() - 1).min()) * 100
        if len(equity) >= 120:
            s["cagr"] = (equity.iloc[-1] ** (TRADING_DAYS / len(equity)) - 1) * 100
        dr = equity.pct_change().dropna()
        if dr.std() > 0:
            s["sharpe"] = dr.mean() / dr.std() * np.sqrt(TRADING_DAYS)
    return s


def bench_return(bench_close: pd.Series, index) -> tuple[pd.Series, float]:
    b = bench_close.reindex(index).ffill().dropna()
    if len(b) < 2:
        return pd.Series(dtype=float), np.nan
    curve = b / b.iloc[0]
    return curve, (curve.iloc[-1] - 1) * 100


def mc_ruin(trade_rets_pct, n_sims=2000, n_trades=60, frac=0.25, block=3, ruin=0.5, seed=42) -> dict:
    """區塊自助法（保留連續虧損的群聚性）；frac≈每筆佔資金比例。"""
    r = np.asarray(trade_rets_pct, dtype=float) / 100.0
    n = len(r)
    if n < 5:
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n_trades / block))
    starts = rng.integers(0, n, size=(n_sims, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    seq = r[idx].reshape(n_sims, -1)[:, :n_trades]
    eq = np.concatenate([np.ones((n_sims, 1)), np.cumprod(1 + frac * seq, axis=1)], axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    mdd = -(eq / peak - 1).min(axis=1) * 100
    return dict(curves=eq, end_mean=eq[:, -1].mean(), end_p5=np.percentile(eq[:, -1], 5),
                mdd95=np.percentile(mdd, 95), p_ruin=(eq.min(axis=1) <= ruin).mean() * 100)


# ----------------------------------------------------------------------------
# Walk-forward
# ----------------------------------------------------------------------------
def _objective(st: dict, min_trades: int) -> float:
    if st["n"] < min_trades or np.isnan(st["tstat"]):
        return -1e9
    return st["tstat"] - max(0.0, (st["mdd"] if not np.isnan(st["mdd"]) else 0) - 20.0) / 10.0


def walk_forward(eng: Engine, grid: dict | None = None, train_days: int = 250, test_days: int = 60,
                 min_trades: int = 12, progress=None, warm: int = 70):
    grid = grid or DEFAULT_GRID
    combos = [Params(*x) for x in product(grid["preset"], grid["min_score"], grid["stop_atr"],
                                          grid["tp_r"], grid["hold"])]
    T = len(eng.idx)
    folds, a = [], warm
    while a + train_days + test_days <= T:
        folds.append((a, a + train_days, a + train_days + test_days))
        a += test_days
    if not folds:
        return None

    total = (len(folds) * 2 + 1) * len(combos)
    step = 0
    rows, oos_trades, chained = [], [], []
    level = 1.0
    sel_counter = {}

    for fi, (a, b, e) in enumerate(folds):
        tr_stats, te_stats, te_data = [], [], []
        for c in combos:
            t, q = simulate(eng, c, a, b)
            tr_stats.append(summarize(t, q))
            step += 1
            t2, q2 = simulate(eng, c, b, e)
            te_stats.append(summarize(t2, q2))
            te_data.append((t2, q2))
            step += 1
            if progress:
                progress(min(step / total, 1.0))
        objs = [_objective(s, min_trades) for s in tr_stats]
        bi = int(np.argmax(objs))
        if objs[bi] <= -1e8:
            rows.append(dict(fold=fi + 1, train=f"{eng.idx[a].date()}~{eng.idx[b-1].date()}",
                             test=f"{eng.idx[b].date()}~{eng.idx[e-1].date()}", params="訓練期交易數不足，略過",
                             train_n=0, train_exp=np.nan, test_n=0, test_exp=np.nan, test_ret=np.nan,
                             test_mdd=np.nan, rank_pct=np.nan))
            continue
        best = combos[bi]
        sel_counter[best.preset] = sel_counter.get(best.preset, 0) + 1
        t2, q2 = te_data[bi]
        exps = np.array([s["expectancy"] if s["n"] > 0 else np.nan for s in te_stats], dtype=float)
        me = te_stats[bi]["expectancy"]
        valid = ~np.isnan(exps)
        rank_pct = (np.sum(exps[valid] < me) / valid.sum() * 100) if (valid.any() and not np.isnan(me)) else np.nan
        rows.append(dict(fold=fi + 1, train=f"{eng.idx[a].date()}~{eng.idx[b-1].date()}",
                         test=f"{eng.idx[b].date()}~{eng.idx[e-1].date()}", params=best.label(),
                         train_n=tr_stats[bi]["n"], train_exp=tr_stats[bi]["expectancy"],
                         test_n=te_stats[bi]["n"], test_exp=me, test_ret=te_stats[bi]["total_ret"],
                         test_mdd=te_stats[bi]["mdd"], rank_pct=rank_pct))
        if len(t2):
            t2 = t2.copy()
            t2["fold"] = fi + 1
            oos_trades.append(t2)
        chained.append(q2 * level)
        level = chained[-1].iloc[-1]

    # 最新一個訓練視窗 → 用於「今日推薦」的參數
    a, b = T - train_days, T
    fin = []
    for c in combos:
        t, q = simulate(eng, c, a, b)
        fin.append((c, summarize(t, q)))
        step += 1
        if progress:
            progress(min(step / total, 1.0))
    fobj = [_objective(s, min_trades) for _, s in fin]
    fi_best = int(np.argmax(fobj))
    final_params, final_stats = fin[fi_best]
    final_ok = fobj[fi_best] > -1e8

    oos_tr = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame()
    oos_eq = pd.concat(chained) if chained else pd.Series(dtype=float)
    oos_stats = summarize(oos_tr, oos_eq if len(oos_eq) else None)
    fold_df = pd.DataFrame(rows)
    is_exp = fold_df["train_exp"].mean() if len(fold_df) else np.nan
    return dict(folds=fold_df, oos_trades=oos_tr, oos_equity=oos_eq, oos_stats=oos_stats,
                is_expectancy=is_exp, rank_pct_median=fold_df["rank_pct"].median() if len(fold_df) else np.nan,
                preset_selection=sel_counter, n_folds=len(folds), n_combos=len(combos),
                final_params=final_params if final_ok else Params(), final_stats=final_stats, final_ok=final_ok,
                train_days=train_days, test_days=test_days)


def verdict(wf: dict, bench_ret_pct: float | None = None):
    """由數據動態產生結論。回傳 (level, headline, bullets)；level ∈ green / yellow / red。"""
    o = wf["oos_stats"]
    bullets, level = [], "green"

    def down(new):
        nonlocal level
        order = {"green": 0, "yellow": 1, "red": 2}
        if order[new] > order[level]:
            level = new

    n = o["n"]
    if n == 0:
        return "red", "樣本外沒有任何交易，無法驗證策略。", ["請放寬篩選條件、增加股票池或拉長資料期間。"]
    if n < 30:
        down("yellow")
        bullets.append(f"樣本外僅 {n} 筆交易（<30），任何績效數字的可信度都很有限。")
    exp = o["expectancy"]
    if exp <= 0:
        down("red")
        bullets.append(f"樣本外每筆期望值 {exp:+.2f}%（扣成本後）≤ 0：策略在未見過的資料上沒有優勢。")
    else:
        bullets.append(f"樣本外每筆期望值 {exp:+.2f}%（90% 自助信賴區間 {o['exp_lo']:+.2f}% ~ {o['exp_hi']:+.2f}%）。")
        if not np.isnan(o["exp_lo"]) and o["exp_lo"] <= 0:
            down("yellow")
            bullets.append("信賴區間下緣 ≤ 0：無法排除『只是運氣』。")
    if not np.isnan(o["tstat"]) and o["tstat"] < 1.65:
        down("yellow")
        bullets.append(f"t 值 {o['tstat']:.2f} < 1.65，統計顯著性不足。")
    ise = wf.get("is_expectancy", np.nan)
    if not np.isnan(ise) and ise > 0 and not np.isnan(exp) and exp < 0.5 * ise:
        down("yellow")
        bullets.append(f"樣本外期望值（{exp:+.2f}%）不到訓練期平均（{ise:+.2f}%）的一半，疑似過擬合。")
    rp = wf.get("rank_pct_median", np.nan)
    if not np.isnan(rp):
        if rp < 55:
            down("yellow")
            bullets.append(f"訓練期選出的參數在測試期僅排在同組參數的第 {rp:.0f} 百分位（≈中位數 50），挑參數沒有增值。")
        else:
            bullets.append(f"所選參數在測試期排名第 {rp:.0f} 百分位，優於多數候選參數。")
    if not np.isnan(o["mdd"]) and o["mdd"] > 20:
        down("yellow")
        bullets.append(f"樣本外最大回撤 {o['mdd']:.1f}%，偏大。")
    if o["max_consec_loss"] >= 6:
        bullets.append(f"最大連虧 {o['max_consec_loss']} 次，需要能承受這種連續虧損的部位大小。")
    if bench_ret_pct is not None and not np.isnan(bench_ret_pct) and not np.isnan(o["total_ret"]):
        diff = o["total_ret"] - bench_ret_pct
        if diff < 0:
            down("yellow")
            bullets.append(f"同期大盤買進持有 {bench_ret_pct:+.1f}%，策略 {o['total_ret']:+.1f}%，尚未贏過指數。")
        else:
            bullets.append(f"同期大盤 {bench_ret_pct:+.1f}%，策略 {o['total_ret']:+.1f}%，超額 {diff:+.1f}%。")
    heads = {"green": "樣本外驗證：通過基本檢查（仍不保證未來獲利）。",
             "yellow": "樣本外驗證：有疑慮，建議縮小部位或僅作觀察。",
             "red": "樣本外驗證：未通過，策略目前沒有可證實的優勢。"}
    return level, heads[level], bullets


# ----------------------------------------------------------------------------
# 訊號品質（預測力檢驗）
# ----------------------------------------------------------------------------
def _fwd(eng: Engine, horizon: int) -> pd.DataFrame:
    P = eng.P
    return P["Close"].shift(-horizon) / P["Open"].shift(-1) - 1


def signal_quality(eng: Engine, preset: str, horizon: int = 10) -> dict:
    fwd, S, U = _fwd(eng, horizon), eng.scores[preset], eng.liquid
    valid = U & fwd.notna() & S.notna()
    s = S.where(valid).rank(axis=1)
    f = fwd.where(valid).rank(axis=1)
    n = valid.sum(axis=1)
    sm, fm = s.sub(s.mean(axis=1), axis=0), f.sub(f.mean(axis=1), axis=0)
    ic = (sm * fm).sum(axis=1) / np.sqrt((sm ** 2).sum(axis=1) * (fm ** 2).sum(axis=1))
    ic = ic[n >= 20].dropna()
    ic_s = ic.iloc[::horizon]   # 降採樣以減輕重疊報酬的自相關
    res = dict(horizon=horizon, days=len(ic_s), ic_mean=np.nan, ic_ir=np.nan, ic_t=np.nan, quintile=pd.DataFrame())
    if len(ic_s) >= 5:
        res["ic_mean"] = ic_s.mean()
        res["ic_ir"] = ic_s.mean() / ic_s.std() if ic_s.std() > 0 else np.nan
        res["ic_t"] = ic_s.mean() / (ic_s.std() / np.sqrt(len(ic_s))) if ic_s.std() > 0 else np.nan
    b = np.ceil(s.div(n, axis=0) * 5).clip(1, 5)
    df = pd.DataFrame({"bucket": b.stack(), "fwd": fwd.where(valid).stack()}).dropna()
    if len(df):
        q = df.groupby("bucket")["fwd"].agg(平均報酬="mean", 勝率=lambda x: (x > 0).mean(), 樣本數="size")
        q["平均報酬"] *= 100
        q["勝率"] *= 100
        q.index = [f"Q{int(i)}" + ("（最低分）" if i == 1 else "（最高分）" if i == 5 else "") for i in q.index]
        res["quintile"] = q
    return res


def score_calibration(eng: Engine, preset: str, horizon: int) -> pd.DataFrame:
    fwd, S = _fwd(eng, horizon), eng.scores[preset]
    E = eng.elig & fwd.notna() & S.notna()
    df = pd.DataFrame({"score": S.where(E).stack(), "fwd": fwd.where(E).stack()}).dropna()
    if df.empty:
        return pd.DataFrame()
    df["band"] = pd.cut(df["score"], [0, 55, 65, 75, 85, 101], right=False,
                        labels=["<55", "55-65", "65-75", "75-85", "85+"])
    out = df.groupby("band", observed=True)["fwd"].agg(平均報酬="mean", 勝率=lambda x: (x > 0).mean(), 樣本數="size")
    out["平均報酬"] *= 100
    out["勝率"] *= 100
    return out


# ----------------------------------------------------------------------------
# 即時推薦 / 快照 / 診斷
# ----------------------------------------------------------------------------
def latest_candidates(eng: Engine, params: Params, top: int = 10, exclude: set | None = None) -> list[dict]:
    S = eng.scores[params.preset].iloc[-1]
    E = eng.elig.iloc[-1]
    m = E & (S >= params.min_score)
    if exclude:
        m &= ~S.index.isin(list(exclude))
    P = eng.P
    out = []
    for code in S[m].sort_values(ascending=False).index[:top]:
        close = float(P["Close"][code].iloc[-1])
        fill = close * (1 + eng.costs.slip)
        stop, tp, R = plan_trade(fill, float(P["ATR"][code].iloc[-1]), float(P["Low5"][code].iloc[-1]),
                                 params.stop_atr, params.tp_r)
        out.append(dict(code=code, score=float(S[code]), close=close, pct=float(P["pct"][code].iloc[-1]),
                        stop=stop, tp=tp, risk_pct=(fill - stop) / fill * 100,
                        turnover_yi=float(P["Turnover_MA5"][code].iloc[-1]) / 1e8,
                        volume_lots=float(P["Volume"][code].iloc[-1]) / 1000,
                        bias5=float(P["Bias5"][code].iloc[-1]), bias20=float(P["Bias20"][code].iloc[-1]),
                        k=float(P["K"][code].iloc[-1]), rsi=float(P["RSI"][code].iloc[-1]),
                        sub={k: float(eng.feats[k][code].iloc[-1]) * 100 for k in ("trend", "compress", "mom", "rs")}))
    return out


SCREEN_FLAGS = [
    "多頭排列 (收盤>20MA>60MA)", "空轉多 (3日內站上月線)", "多頭擴大 (5>10>20>60MA)", "今日強勢漲停 (≥9.5%)",
    "突破週線 (3日內站上5MA)", "突破月線 (3日內站上20MA)", "突破季線 (3日內站上60MA)", "創20日新高",
    "VCP 收斂 (帶寬低檔+5日振幅<6%)", "窒息量縮 (量<20日均量60%)", "爆量攻擊 (量>5日均量1.5倍)",
    "量價鎖碼 (CLV推力>0.15)", "MACD 紅柱", "RSI 50–70 健康動能", "KD 黃金交叉 (K>D 且 K<80)",
]


def snapshot(eng: Engine, preset: str) -> pd.DataFrame:
    P = eng.P
    C = P["Close"]

    def cross(a, b, k=3):
        x = ((a > b) & (a.shift(1) <= b.shift(1))).astype(float)
        return x.rolling(k).max().iloc[-1] > 0

    last = lambda df: df.iloc[-1]
    flags = {
        SCREEN_FLAGS[0]: last((C > P["MA20"]) & (P["MA20"] > P["MA60"])),
        SCREEN_FLAGS[1]: cross(C, P["MA20"]),
        SCREEN_FLAGS[2]: last((P["MA5"] > P["MA10"]) & (P["MA10"] > P["MA20"]) & (P["MA20"] > P["MA60"])),
        SCREEN_FLAGS[3]: last(P["pct"]) >= 9.5,
        SCREEN_FLAGS[4]: cross(C, P["MA5"]),
        SCREEN_FLAGS[5]: cross(C, P["MA20"]),
        SCREEN_FLAGS[6]: cross(C, P["MA60"]),
        SCREEN_FLAGS[7]: last(C > P["High20_prev"]),
        SCREEN_FLAGS[8]: last((P["BB_Pct"] <= 0.25) & (P["Range5"] < 6)),
        SCREEN_FLAGS[9]: last(P["Volume"] < P["Vol_MA20"] * 0.6),
        SCREEN_FLAGS[10]: last(P["Volume"] > P["Vol_MA5"] * 1.5),
        SCREEN_FLAGS[11]: last(P["CLV5"] > 0.15),
        SCREEN_FLAGS[12]: last(P["MACD_Hist"] > 0),
        SCREEN_FLAGS[13]: last((P["RSI"] >= 50) & (P["RSI"] <= 70)),
        SCREEN_FLAGS[14]: last((P["K"] > P["D"]) & (P["K"] < 80)),
    }
    out = pd.DataFrame({
        "close": last(C), "pct": last(P["pct"]), "volume_lots": last(P["Volume"]) / 1000,
        "turnover_yi": last(P["Turnover_MA5"]) / 1e8, "bias5": last(P["Bias5"]), "bias20": last(P["Bias20"]),
        "K": last(P["K"]), "RSI": last(P["RSI"]), "score": last(eng.scores[preset]),
        "liquid": last(eng.liquid), "eligible": last(eng.elig),
    })
    for k, v in flags.items():
        out[k] = v.astype(bool)
    return out


def bull_bear_checks(d: pd.DataFrame, chip: dict | None = None, rev_yoy: float | None = None) -> dict:
    """只列出『真的算得出來』的多空項目；沒資料就不顯示，不再寫死。"""
    bull, bear = [], []
    x, p = d.iloc[-1], d.iloc[-2]
    c = x["Close"]
    if c > x["MA5"]: bull.append("站上週線 5MA")
    if c > x["MA20"]: bull.append("站上月線 20MA")
    if c > x["MA60"]: bull.append("站上季線 60MA")
    if (d["Close"].tail(5) > d["MA20"].tail(5)).all(): bull.append("連5日站穩月線")
    if x["MA5"] > x["MA10"] > x["MA20"]: bull.append("短線多頭排列")
    if x["MA10"] > x["MA20"] > x["MA60"]: bull.append("長線多頭排列")
    if 50 <= x["K"] <= 80 and x["K"] > x["D"]: bull.append("KD 多方強勢")
    if x["MACD_Hist"] > 0: bull.append("MACD 紅柱")
    if 50 <= x["RSI"] <= 70: bull.append("RSI 健康動能")
    if x["Volume"] > x["Vol_MA5"] * 1.3 and c > p["Close"]: bull.append("價漲量增")
    if c < x["MA20"]: bear.append("跌破月線")
    if c < x["MA60"]: bear.append("跌破季線")
    if x["MA20"] < x["MA60"] and c < x["MA20"]: bear.append("均線空頭排列")
    if x["Bias5"] > 3.5: bear.append("短線乖離過大")
    if x["Bias20"] > 12: bear.append("月線乖離過熱")
    if x["RSI"] > 75: bear.append("RSI 過熱")
    if x["MACD_Hist"] < 0: bear.append("MACD 綠柱")
    if x["Volume"] > x["Vol_MA5"] * 1.3 and c < p["Close"]: bear.append("價跌量增")
    if chip:
        if chip.get("foreign", 0) > 0: bull.append("外資近5日買超")
        elif chip.get("foreign", 0) < 0: bear.append("外資近5日賣超")
        if chip.get("trust", 0) > 0: bull.append("投信近5日買超")
        elif chip.get("trust", 0) < 0: bear.append("投信近5日賣超")
    if rev_yoy is not None and not np.isnan(rev_yoy):
        if rev_yoy >= 20: bull.append(f"月營收年增 {rev_yoy:.0f}%")
        elif rev_yoy > 0: bull.append(f"月營收年增 {rev_yoy:.0f}%")
        else: bear.append(f"月營收年減 {rev_yoy:.0f}%")
    return dict(bull=bull, bear=bear)


def holding_health(d: pd.DataFrame, params: Params) -> dict:
    x, p = d.iloc[-1], d.iloc[-2]
    close = float(x["Close"])
    stop, tp, R = plan_trade(close, float(x["ATR"]), float(x["Low5"]), params.stop_atr, params.tp_r)
    flags, weak = [], 0
    if close < x["MA20"]: flags.append("跌破月線"); weak += 2
    if x["MA20_slope5"] < 0: flags.append("月線下彎"); weak += 1
    if close < x["MA60"]: flags.append("跌破季線"); weak += 2
    if x["RSI"] < 45: flags.append("RSI<45 動能轉弱"); weak += 1
    if close <= stop: flags.append("觸及防守價"); weak += 3
    return dict(close=close, stop=stop, tp=tp, weak=weak, flags=flags,
                ret20=float(close / d["Close"].iloc[-21] - 1) * 100 if len(d) > 21 else np.nan)


# ============================================================================
# C. 介面
# ============================================================================
st.set_page_config(page_title="台股量化操盤決策系統", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .stApp {background:#080c14 !important; color:#fff !important;}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {background:#0b0f19 !important; border-right:1px solid rgba(79,172,254,.25) !important;}
p, span, label, h1, h2, h3, h4, h5, h6, li {color:#fff !important;}
a {color:#38bdf8 !important;}
div[data-baseweb="select"] > div {background:#0f172a !important; border:1px solid #334155 !important; border-radius:8px !important;}
div[data-baseweb="popover"], div[data-baseweb="menu"], ul[data-baseweb="menu"] {background:#0b1120 !important; border:1px solid #38bdf8 !important;}
li[data-baseweb="menu-item"] {background:#0b1120 !important; color:#fff !important;}
li[data-baseweb="menu-item"]:hover {background:#1e293b !important; color:#38bdf8 !important;}
div.stButton > button {background:#080c14 !important; color:#fff !important; border:2px solid transparent !important; border-radius:9999px !important;
  padding:.6rem 2rem !important; font-weight:700 !important;
  background-image:linear-gradient(#080c14,#080c14),linear-gradient(90deg,#00f2fe,#4facfe,#fa709a,#fee140) !important;
  background-origin:border-box !important; background-clip:padding-box,border-box !important;
  box-shadow:0 0 16px rgba(79,172,254,.45) !important; transition:all .25s ease-in-out !important;}
div.stButton > button:hover {transform:translateY(-2px) !important; box-shadow:0 0 26px rgba(250,112,154,.6) !important;}
div[data-testid="stMetric"] {background:#0f172a !important; border:1px solid #1e293b !important; border-radius:12px !important; padding:12px 16px !important;}
div[data-testid="stMetricLabel"] {color:#94a3b8 !important;}
.stock-card {background:#0b1120; border:1px solid #1e293b; border-radius:16px; padding:16px; margin-bottom:14px;}
.stock-card-top1 {background:#0f172a; border:2px solid #38bdf8; border-radius:18px; padding:20px; margin-bottom:18px; box-shadow:0 0 25px rgba(56,189,248,.25);}
.tag-badge {display:inline-block; background:#082f49; color:#38bdf8 !important; border:1px solid #0284c7; padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; margin:0 4px 4px 0;}
.rating-box {display:flex; justify-content:space-around; background:#060a12; border:1px solid #1e293b; border-radius:10px; padding:10px 4px; margin-top:12px; text-align:center;}
.rl {font-size:12px; color:#94a3b8 !important;} .rv {font-size:17px; font-weight:700;}
.bb-bg {width:100%; height:10px; background:#22c55e; border-radius:9999px; overflow:hidden; margin:8px 0;}
.bb-fill {height:100%; background:#ef4444;}
.chk-bull {background:#450a0a; border:1px solid #b91c1c; color:#fca5a5 !important; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block; margin:3px 4px 3px 0;}
.chk-bear {background:#052e16; border:1px solid #15803d; color:#86efac !important; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block; margin:3px 4px 3px 0;}
.lnk {font-size:12px; margin-right:10px;}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 題材資料庫：只保留「代碼/名稱/題材標籤」。市場別(上市/上櫃)由官方清單即時判斷；
# 原版的公司簡介含未經查證的說法，已移除，請用卡片上的連結查看最新公司資料。
# ============================================================================
SECTORS = {
    "重電綠能與強韌電網": [("1513", "中興電", ["儲能", "離岸風電", "GIS"]), ("1609", "大亞", ["電纜", "儲能"]),
                          ("1519", "華城", ["變壓器", "外銷"]), ("1503", "士電", ["重電", "車用電裝"]),
                          ("1514", "亞力", ["變配電", "半導體廠務"]), ("2371", "大同", ["重電", "資產開發"])],
    "CPO 矽光子與光通訊": [("3450", "聯鈞", ["光收發", "CPO"]), ("3363", "上詮", ["光纖陣列", "CPO"]),
                          ("3081", "聯亞", ["磊晶", "InP"]), ("4979", "華星光", ["AOC", "光模組"]),
                          ("6442", "光聖", ["光被動"]), ("4977", "眾達-KY", ["CPO", "光模組"])],
    "散熱模組與水冷系統": [("3017", "奇鋐", ["水冷板", "散熱模組"]), ("3324", "雙鴻", ["液冷", "CDU"]),
                          ("3653", "健策", ["均熱片"]), ("8996", "高力", ["熱交換器"]),
                          ("6230", "尼得科超眾", ["熱導管"]), ("3483", "力致", ["散熱模組"])],
    "AI 伺服器與硬體代工": [("2382", "廣達", ["AI伺服器"]), ("3231", "緯創", ["GPU基板"]), ("2376", "技嘉", ["AI伺服器"]),
                           ("6669", "緯穎", ["雲端ODM"]), ("2059", "川湖", ["伺服器滑軌"]), ("8210", "勤誠", ["伺服器機殼"])],
    "PCB、載板與 CCL": [("2383", "台光電", ["CCL"]), ("3037", "欣興", ["ABF載板"]), ("2368", "金像電", ["高層PCB"]),
                       ("6274", "台燿", ["CCL"]), ("3189", "景碩", ["載板"]), ("8046", "南電", ["載板"])],
    "記憶體模組與控制晶片": [("8299", "群聯", ["NAND控制IC"]), ("3260", "威剛", ["記憶體模組"]), ("4967", "十銓", ["記憶體模組"]),
                            ("2408", "南亞科", ["DRAM"]), ("2344", "華邦電", ["NOR/利基DRAM"]), ("3006", "晶豪科", ["利基DRAM"])],
    "半導體製造與設備": [("2330", "台積電", ["晶圓代工"]), ("2303", "聯電", ["成熟製程"]), ("3583", "辛耘", ["濕製程設備"]),
                        ("3131", "弘塑", ["濕製程設備"]), ("6223", "旺矽", ["探針卡"]), ("1560", "中砂", ["鑽石碟"])],
    "機器人自動化與智慧工具機": [("2359", "所羅門", ["機器視覺"]), ("2365", "昆盈", ["感測"]), ("6188", "廣明", ["協作機器人"]),
                                ("8374", "羅昇", ["傳動控制"]), ("2049", "上銀", ["滾珠螺桿"]), ("4583", "台灣精銳", ["精密減速機"])],
    "AI 晶片與 IP": [("2454", "聯發科", ["手機AP", "ASIC"]), ("3661", "世芯-KY", ["ASIC"]), ("3443", "創意", ["ASIC", "IP"]),
                    ("3529", "力旺", ["矽智財"]), ("6117", "迎廣", ["機殼", "水冷"])],
}
NAME_MAP = {c: n for v in SECTORS.values() for c, n, _ in v}
TAG_MAP = {c: t for v in SECTORS.values() for c, _, t in v}

PORTFOLIO_FILE = Path("portfolio.json")
DEFAULT_PORTFOLIO = [
    {"code": "2330", "cost": 950.0, "shares": 1000, "date": "2026-09-15"},
    {"code": "3189", "cost": 115.0, "shares": 5000, "date": "2026-09-20"},
    {"code": "3653", "cost": 820.0, "shares": 1000, "date": "2026-09-22"},
    {"code": "1513", "cost": 165.0, "shares": 6000, "date": "2026-09-25"},
]


def load_portfolio() -> list:
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [dict(x) for x in DEFAULT_PORTFOLIO]


def save_portfolio(rows: list):
    PORTFOLIO_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================================
# 側邊欄
# ============================================================================
sb = st.sidebar
sb.markdown("### 資金與風控")
capital = sb.number_input("總操作資金 (TWD)", 50_000, 50_000_000, 1_000_000, 50_000)
risk_pct = sb.slider("單筆最大承受風險 (%)", 0.5, 5.0, 1.5, 0.1)
sb.markdown("### 股票池與過濾")
n_universe = sb.select_slider("分析股票池（當日成交值前 N 檔）", [100, 150, 200, 250, 300, 400], value=200)
excl = sb.multiselect("排除產業", ["金融保險業", "航運業", "水泥工業", "食品工業", "貿易百貨業", "觀光餐旅", "塑膠工業", "造紙工業"],
                      default=["金融保險業", "航運業", "水泥工業"])
min_price = sb.number_input("最低股價", 1.0, 500.0, 35.0, 1.0)
min_turn_yi = sb.number_input("5日均成交值下限（億）", 0.1, 20.0, 1.5, 0.1)
min_amp = sb.number_input("20日振幅下限 (%)", 0.0, 30.0, 8.0, 0.5)
bias5_max = sb.slider("5MA 乖離上限 (%)", 1.0, 8.0, 3.5, 0.5)
bias20_max = sb.slider("20MA 乖離上限 (%)", 3.0, 20.0, 10.0, 1.0)
sb.markdown("### 交易成本")
fee_disc = sb.slider("手續費折扣（0.6 = 6折）", 0.2, 1.0, 0.6, 0.02)
slip_pct = sb.slider("單邊滑價 (%)", 0.0, 0.5, 0.10, 0.05)
sb.markdown("### Walk-forward")
train_days = sb.slider("訓練視窗（交易日）", 150, 400, 250, 10)
test_days = sb.slider("測試視窗（交易日）", 40, 120, 60, 10)
if sb.button("🔄 重新抓取最新資料"):
    st.cache_data.clear()
    st.cache_resource.clear()
    for k in ("wf", "final_params"):
        st.session_state.pop(k, None)
    st.rerun()

# ============================================================================
# 資料載入（快取）
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_meta(day_key: str):
    uni, m1 = load_universe()
    turn, m2 = load_daily_turnover()
    chips, chip_days, m3 = load_institutional(5)
    rev, m4 = load_revenue_yoy()
    punish, notice, m5 = load_flags()
    return dict(uni=uni, turn=turn, chips=chips, chip_days=chip_days, rev=rev, punish=punish, notice=notice,
                msgs=m1 + m2 + m3 + m4 + m5)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_prices(tickers: tuple, period: str = "3y"):
    return download_prices(list(tickers), period=period)


@st.cache_resource(ttl=3600, show_spinner=False)
def build_engine(day_key, n, excl_t, min_price, min_turn_yi, min_amp, b5, b20, fee_disc, slip_pct):
    meta = load_meta(day_key)
    uni = meta["uni"].copy()
    notes = []
    if not uni.empty:
        if excl_t:
            uni = uni[~uni["industry"].isin(excl_t)]
        if len(meta["turn"]):
            uni["turn"] = uni["code"].map(meta["turn"])
            uni = uni.dropna(subset=["turn"]).sort_values("turn", ascending=False).head(n)
        else:
            notes.append("無法取得成交值排名，改用題材清單內的股票。")
            uni = uni[uni["code"].isin(NAME_MAP)]
    else:
        notes.append("官方股票清單抓取失敗，改用題材清單並猜測市場別（可能有誤）。")
        uni = pd.DataFrame([dict(code=c, name=NAME_MAP[c], market="TW", industry="") for c in NAME_MAP])
    tickers = [f"{r.code}.{r.market}" for r in uni.itertuples()]
    prices = cached_prices(tuple(tickers + ["^TWII"]))
    bench = prices.pop("^TWII", None)
    if bench is None or not prices:
        raise RuntimeError("價格資料下載失敗（yfinance）。請稍後重試或檢查網路。")
    dfs = {}
    for t, df in prices.items():
        try:
            dfs[t.split(".")[0]] = add_indicators(df)
        except Exception:
            continue
    P = build_panel(dfs)
    flt = Filters(min_price, min_turn_yi * 1e8, min_amp, b5, b20)
    eng = Engine(P, bench["Close"], flt, Costs(fee_disc=fee_disc, slip=slip_pct / 100.0))
    market = dict(zip(uni["code"], uni["market"]))
    names = dict(zip(uni["code"], uni["name"]))
    return eng, bench, market, names, notes


day_key = now_tw().strftime("%Y-%m-%d-%H")
try:
    with st.spinner("下載官方清單與 3 年價格資料（首次約 30~90 秒）…"):
        eng, bench_df, MARKET, NAMES, eng_notes = build_engine(
            day_key, n_universe, tuple(excl), min_price, min_turn_yi, min_amp, bias5_max, bias20_max, fee_disc, slip_pct)
except Exception as e:
    st.error(f"資料載入失敗：{e}")
    st.stop()
meta = load_meta(day_key)
NAMES = {**NAME_MAP, **NAMES}


def label(code: str) -> str:
    return f"{NAMES.get(code, code)} ({code})"


def chip_of(code: str):
    ch = meta["chips"]
    if code in ch.index:
        r = ch.loc[code]
        return dict(foreign=float(r["foreign"]), trust=float(r["trust"]), total=float(r["total"]))
    return None


def link_html(code: str) -> str:
    return "".join(f'<a class="lnk" href="{u}" target="_blank">{n}</a>' for n, u in links(code, MARKET.get(code, "TW")).items())


wf = st.session_state.get("wf")
params = st.session_state.get("final_params") or Params()
data_date = eng.idx[-1].strftime("%Y-%m-%d")
bench_last = float(bench_df["Close"].iloc[-1])

with st.expander("📡 資料狀態（來源、日期、抓取失敗訊息）"):
    st.write(f"價格資料最新日期：**{data_date}**　｜　股票池：**{len(eng.codes)}** 檔　｜　系統時間：{now_tw():%Y-%m-%d %H:%M} (台北)")
    for m in eng_notes + meta["msgs"]:
        st.caption("• " + m)
    st.caption("• 籌碼（三大法人）目前只接上市；上櫃顯示『無資料』。籌碼與營收不在回測內（歷史資料尚未接入），僅作為輔助參考。")

tab_daily, tab_port, tab_sec, tab_val, tab_scr = st.tabs([
    "🎯 每日決策與推薦", "💼 持股健檢與換股", "🌐 族群多空儀表板", "🧪 Walk-Forward 驗證與風險", "🛠️ 15 項全景篩選器"])


# ----------------------------------------------------------------------------
def candle_fig(df: pd.DataFrame, n: int, stop=None, tp=None, height=380, title=""):
    d = df.tail(n)
    cats = d.index.strftime("%m/%d").tolist()
    fig = go.Figure(go.Candlestick(x=cats, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                   increasing_line_color="#ef4444", decreasing_line_color="#22c55e", name="K"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA20"], line=dict(color="#3b82f6", width=1.4), name="20MA"))
    fig.add_trace(go.Scatter(x=cats, y=d["MA60"], line=dict(color="#f59e0b", width=1.4), name="60MA"))
    if stop:
        fig.add_hline(y=stop, line_dash="dash", line_color="#22c55e", annotation_text=f"停損 {stop:.2f}")
    if tp:
        fig.add_hline(y=tp, line_dash="dash", line_color="#ef4444", annotation_text=f"目標 {tp:.2f}")
    fig.update_layout(height=height, title=title, xaxis=dict(type="category", rangeslider=dict(visible=False)),
                      margin=dict(l=5, r=5, t=40 if title else 10, b=5), paper_bgcolor="#080c14",
                      plot_bgcolor="#080c14", font=dict(color="#fff"), showlegend=False)
    return fig


def ind_df(code: str) -> pd.DataFrame:
    P = eng.P
    d = pd.DataFrame({f: P[f][code] for f in ("Open", "High", "Low", "Close", "MA20", "MA60")})
    return d.dropna(subset=["Close"])


def verdict_banner(level, head, bullets):
    fn = {"green": st.success, "yellow": st.warning, "red": st.error}[level]
    fn(head + "\n\n" + "\n".join("- " + b for b in bullets))


# ============================================================================
# Tab 1
# ============================================================================
with tab_daily:
    st.markdown(f"### 盤勢與做多決策 ｜ 資料日期 {data_date}")
    regime_ok = bool(eng.regime[-1])
    if regime_ok:
        st.info(f"大盤環境：🟢 加權指數 {bench_last:,.0f}，未同時跌破月線與季線（允許新進場）")
    else:
        st.warning(f"大盤環境：🔴 加權指數 {bench_last:,.0f} 同時位於月線與季線之下。回測規則此時**不新進場**，以下僅供觀察。")

    if wf:
        _, bh = bench_return(eng.bench_close, wf["oos_equity"].index) if len(wf["oos_equity"]) else (None, np.nan)
        lv, hd, bl = verdict(wf, bh)
        verdict_banner(lv, hd, bl)
        st.caption(f"目前使用的參數（取自最近 {wf['train_days']} 日訓練視窗）：{params.label()}"
                   + ("" if wf["final_ok"] else "　⚠ 最近視窗交易數不足，改用預設參數"))
    else:
        st.warning("尚未執行 Walk-Forward 驗證，目前使用預設參數，**績效未經樣本外檢驗**。請先到「🧪 Walk-Forward 驗證」分頁執行。")

    cands = latest_candidates(eng, params, top=10, exclude=meta["punish"])
    if not cands:
        st.warning("今日沒有標的同時通過流動性、趨勢、乖離與分數門檻。空手也是一種部位。")
    else:
        calib_key = f"calib_{params.preset}_{params.hold}"
        if calib_key not in st.session_state:
            st.session_state[calib_key] = score_calibration(eng, params.preset, params.hold)
        calib = st.session_state[calib_key]

        t1 = cands[0]
        code = t1["code"]
        ck = chip_of(code)
        ry = meta["rev"].get(code, np.nan)
        tags = "".join(f'<span class="tag-badge">{html.escape(t)}</span>' for t in TAG_MAP.get(code, []))
        flag_txt = "　⚠ 注意股" if code in meta["notice"] else ""
        subs = t1["sub"]
        st.markdown("#### 👑 今日首選")
        st.markdown(f"""
        <div class="stock-card-top1">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <div><span style="font-size:30px;font-weight:900;color:#f59e0b !important;">{html.escape(label(code))}</span>{flag_txt}
              <div style="margin-top:8px;">{tags}</div><div style="margin-top:6px;">{link_html(code)}</div></div>
            <div style="text-align:right;">
              <div style="font-size:34px;font-weight:900;">{t1['close']:.2f}</div>
              <div style="font-size:17px;font-weight:700;color:{'#ef4444' if t1['pct']>=0 else '#22c55e'} !important;">{'▲' if t1['pct']>=0 else '▼'} {t1['pct']:+.2f}%</div>
              <div style="font-size:14px;color:#38bdf8 !important;font-weight:700;">綜合分數 {t1['score']:.1f}（{params.preset}）</div></div></div>
          <div class="rating-box">
            <div><div class="rl">趨勢</div><div class="rv">{subs['trend']:.0f}</div></div>
            <div><div class="rl">波動收斂</div><div class="rv">{subs['compress']:.0f}</div></div>
            <div><div class="rl">動能</div><div class="rv">{subs['mom']:.0f}</div></div>
            <div><div class="rl">相對強度</div><div class="rv">{subs['rs']:.0f}</div></div>
            <div><div class="rl">K / RSI</div><div class="rv">{t1['k']:.0f} / {t1['rsi']:.0f}</div></div></div></div>
        """, unsafe_allow_html=True)

        size = size_position(capital, risk_pct, t1["close"], t1["stop"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("參考進場（隔日開盤附近）", f"{t1['close']:.2f}", f"成交 {int(t1['volume_lots']):,} 張")
        c2.metric("防守停損（已對齊升降單位）", f"{t1['stop']:.2f}", f"-{t1['risk_pct']:.2f}%", delta_color="inverse")
        c3.metric(f"停利目標 ({params.tp_r}R)", f"{t1['tp']:.2f}", f"+{(t1['tp']/t1['close']-1)*100:.2f}%")
        c4.metric("5日均成交值", f"{t1['turnover_yi']:.2f} 億")

        s1, s2, s3 = st.columns(3)
        s1.metric("建議張數", f"{size['lots']} 張 + {size['odd']} 股", f"依{size['binding']}")
        s2.metric("投入金額", f"{size['amount']:,.0f} 元", f"{size['pct_capital']:.1f}% 資金")
        s3.metric("停損時預估虧損", f"{size['risk_amt']:,.0f} 元", f"{size['risk_amt']/capital*100:.2f}% 資金", delta_color="inverse")

        extra = []
        if ck:
            extra.append(f"上市三大法人近5日：外資 {ck['foreign']/1000:+,.0f} 張、投信 {ck['trust']/1000:+,.0f} 張、合計 {ck['total']/1000:+,.0f} 張")
        else:
            extra.append("三大法人：無資料")
        extra.append(f"月營收年增率：{ry:+.1f}%" if not np.isnan(ry) else "月營收年增率：無資料")
        st.caption("　｜　".join(extra))
        if len(calib):
            band = pd.cut([t1["score"]], [0, 55, 65, 75, 85, 101], right=False, labels=["<55", "55-65", "65-75", "75-85", "85+"])[0]
            if band in calib.index:
                r = calib.loc[band]
                st.caption(f"📊 歷史校準：過去股票池內分數落在 {band} 且通過過濾的訊號共 {int(r['樣本數']):,} 次，"
                           f"隔日開盤買進持有 {params.hold} 日，勝率 {r['勝率']:.1f}%、平均報酬 {r['平均報酬']:+.2f}%（未扣成本，訊號彼此高度重疊，僅供參考）。")
        st.plotly_chart(candle_fig(ind_df(code), 60, t1["stop"], t1["tp"], title=f"{label(code)} 日K（連續交易日）"),
                        use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🎯 第 2～10 名")
        rows = []
        for i, c in enumerate(cands[1:], start=2):
            ckc = chip_of(c["code"])
            rows.append({"名次": i, "標的": label(c["code"]), "分數": round(c["score"], 1), "收盤": c["close"],
                         "漲跌%": round(c["pct"], 2), "停損": c["stop"], "停利": c["tp"], "風險%": round(c["risk_pct"], 2),
                         "外資5日(張)": round(ckc["foreign"] / 1000) if ckc else None,
                         "投信5日(張)": round(ckc["trust"] / 1000) if ckc else None,
                         "月營收YoY%": meta["rev"].get(c["code"], np.nan),
                         "注意股": "⚠" if c["code"] in meta["notice"] else ""})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        pick = st.selectbox("查看連結與K線", [c["code"] for c in cands[1:]], format_func=label) if len(cands) > 1 else None
        if pick:
            cc = next(c for c in cands if c["code"] == pick)
            st.markdown(link_html(pick), unsafe_allow_html=True)
            st.plotly_chart(candle_fig(ind_df(pick), 60, cc["stop"], cc["tp"], height=320), use_container_width=True)
    st.caption("⚠ 以上為量化規則產出的輔助資訊，不是投資建議；實際下單前請自行確認消息面、處置/注意公告與流動性。")

# ============================================================================
# Tab 2：持股
# ============================================================================
with tab_port:
    st.markdown("### 💼 持股健檢與換股（資料存於 portfolio.json）")
    if "portfolio" not in st.session_state:
        st.session_state["portfolio"] = load_portfolio()
    edited = st.data_editor(pd.DataFrame(st.session_state["portfolio"]), num_rows="dynamic", use_container_width=True,
                            column_config={"code": "代碼", "cost": st.column_config.NumberColumn("成本", format="%.2f"),
                                           "shares": st.column_config.NumberColumn("股數", step=1000), "date": "買進日(YYYY-MM-DD)"})
    if st.button("💾 儲存持股"):
        st.session_state["portfolio"] = edited.dropna(subset=["code"]).to_dict("records")
        save_portfolio(st.session_state["portfolio"])
        st.success("已儲存。")

    hold_rows, health = [], {}
    codes_h = [str(r["code"]).strip() for r in edited.to_dict("records") if str(r.get("code", "")).strip()]
    missing = [c for c in codes_h if c not in eng.codes]
    extra_px = {}
    if missing:
        tks = [f"{c}.{MARKET.get(c, 'TW')}" for c in missing]
        extra_px = cached_prices(tuple(tks))
    for r in edited.to_dict("records"):
        c = str(r.get("code", "")).strip()
        if not c:
            continue
        try:
            if c in eng.codes:
                d = add_indicators(pd.DataFrame({f: eng.P[f][c] for f in ("Open", "High", "Low", "Close", "Volume")}).dropna(subset=["Close"]))
            else:
                key = next((k for k in extra_px if k.startswith(c + ".")), None)
                d = add_indicators(extra_px[key])
            h = holding_health(d, params)
        except Exception:
            hold_rows.append({"標的": label(c), "狀態": "無法取得資料"})
            continue
        pnl = (h["close"] / float(r["cost"]) - 1) * 100 if r.get("cost") else np.nan
        try:
            days_held = (pd.Timestamp(eng.idx[-1]) - pd.Timestamp(str(r["date"])[:10])).days
        except Exception:
            days_held = None
        health[c] = dict(h, pnl=pnl, days=days_held)
        hold_rows.append({"標的": label(c), "現價": round(h["close"], 2), "成本": r["cost"], "未實現%": round(pnl, 2),
                          "防守價(現價重算)": h["stop"], "弱勢分": h["weak"], "警訊": "、".join(h["flags"]) or "—",
                          "持有天數": days_held})
    if hold_rows:
        st.dataframe(pd.DataFrame(hold_rows), use_container_width=True, hide_index=True)

    st.markdown("#### 換股建議")
    cands_p = latest_candidates(eng, params, top=3, exclude=meta["punish"])
    if not health:
        st.info("尚無持股。")
    elif not cands_p:
        st.info("今日無合格新標的，不需要換股。")
    else:
        top = cands_p[0]
        held_codes = list(health)
        if top["code"] in held_codes:
            st.success(f"今日首選 {label(top['code'])} 已在持股中。")
        else:
            weakest = max(health.items(), key=lambda kv: (kv[1]["weak"], -kv[1]["pnl"] if not np.isnan(kv[1]["pnl"]) else 0))
            wc, wh = weakest
            rt = eng.costs.round_trip * 100
            if wh["weak"] >= 2 and regime_ok:
                st.error(f"建議評估：賣出 **{label(wc)}**（弱勢分 {wh['weak']}：{'、'.join(wh['flags'])}），"
                         f"隔日開盤換入 **{label(top['code'])}**（分數 {top['score']:.1f}）。換股來回成本約 {rt:.2f}%，"
                         "請確認新標的預期優勢大於成本。")
                if st.button(f"🔄 記錄換股：賣 {label(wc)} → 買 {label(top['code'])}"):
                    rows_p = st.session_state["portfolio"]
                    for r in rows_p:
                        if str(r["code"]).strip() == wc:
                            r["code"] = top["code"]
                            r["cost"] = round(top["close"], 2)
                            r["date"] = eng.idx[-1].strftime("%Y-%m-%d")
                    save_portfolio(rows_p)
                    st.success("已更新 portfolio.json（實際成交價請自行修正）。")
                    st.rerun()
            else:
                st.success(f"持股沒有明顯轉弱訊號（最弱：{label(wc)}，弱勢分 {wh['weak']}），"
                           f"不建議為了換股支付約 {rt:.2f}% 的來回成本。" + ("" if regime_ok else " 大盤偏弱，也不新進場。"))

# ============================================================================
# Tab 3：族群
# ============================================================================
with tab_sec:
    st.markdown("### 🌐 族群多空儀表板（全部由真實價量與官方資料計算）")
    c_a, c_b = st.columns(2)
    sec = c_a.selectbox("產業族群", list(SECTORS))
    all_tags = sorted({t for v in SECTORS.values() for _, _, ts in v for t in ts})
    tag_pick = c_b.selectbox("概念標籤（選了會覆蓋族群）", ["—"] + all_tags)
    items = ([(c, n, t) for v in SECTORS.values() for c, n, t in v if tag_pick in t] if tag_pick != "—" else SECTORS[sec])
    seen = set()
    items = [i for i in items if not (i[0] in seen or seen.add(i[0]))]
    need = [c for c, _, _ in items if c not in eng.codes]
    sec_px = cached_prices(tuple(f"{c}.{MARKET.get(c, 'TW')}" for c in need)) if need else {}
    for i in range(0, len(items), 2):
        cols = st.columns(2)
        for k in range(2):
            if i + k >= len(items):
                continue
            c, n, tg = items[i + k]
            with cols[k]:
                try:
                    if c in eng.codes:
                        raw = pd.DataFrame({f: eng.P[f][c] for f in ("Open", "High", "Low", "Close", "Volume")}).dropna(subset=["Close"])
                    else:
                        key = next(x for x in sec_px if x.startswith(c + "."))
                        raw = sec_px[key]
                    d = add_indicators(raw)
                except Exception:
                    st.warning(f"{c} {n}：無資料")
                    continue
                last, prev = float(d["Close"].iloc[-1]), float(d["Close"].iloc[-2])
                diff = last - prev
                col = "#ef4444" if diff >= 0 else "#22c55e"
                diag = bull_bear_checks(d, chip_of(c), meta["rev"].get(c, np.nan))
                nb, nr = len(diag["bull"]), max(1, len(diag["bear"]))
                pct_b = int(nb / (nb + nr) * 100)
                mk = "上櫃" if MARKET.get(c) == "TWO" else "上市"
                st.markdown(f"""
                <div class="stock-card">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div><span style="font-size:22px;font-weight:800;color:#f59e0b !important;">{c} {html.escape(n)}</span>
                      <span style="font-size:12px;background:#334155;padding:2px 6px;border-radius:4px;margin-left:6px;">{mk}</span>
                      <div style="margin-top:6px;">{''.join(f'<span class="tag-badge">{html.escape(t)}</span>' for t in tg)}</div></div>
                    <div style="text-align:right;"><div style="font-size:26px;font-weight:800;">{last:.2f}</div>
                      <div style="color:{col} !important;font-weight:600;">{'▲' if diff>=0 else '▼'} {diff:+.2f} ({diff/prev*100:+.2f}%)</div></div></div>
                  <div style="margin-top:8px;">{link_html(c)}</div></div>""", unsafe_allow_html=True)
                st.plotly_chart(candle_fig(d, 35, height=210), use_container_width=True)
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700;">
                  <span style="color:#ef4444 !important;">● 多方 {nb} 項</span><span style="color:#22c55e !important;">● 空方 {len(diag['bear'])} 項</span></div>
                <div class="bb-bg"><div class="bb-fill" style="width:{pct_b}%;"></div></div>
                <div style="font-size:12px;"><b style="color:#f87171 !important;">多方：</b>{''.join(f'<span class="chk-bull">{html.escape(x)}</span>' for x in diag['bull'][:8])}</div>
                <div style="font-size:12px;"><b style="color:#4ade80 !important;">空方：</b>{''.join(f'<span class="chk-bear">{html.escape(x)}</span>' for x in diag['bear'][:6]) or '—'}</div>
                """, unsafe_allow_html=True)

# ============================================================================
# Tab 4：驗證
# ============================================================================
with tab_val:
    st.markdown("### 🧪 Walk-Forward 驗證與風險")
    st.caption("做法：滾動視窗——用訓練期挑參數（分數權重預設、進場門檻、ATR停損倍數、停利R、持股天數），"
               "再拿『沒看過的』測試期驗證，最後把所有測試期串起來看樣本外績效。回測含手續費、證交稅、滑價；"
               "隔日開盤進場；跳空以開盤價成交；同日停損優先於停利。")
    st.caption(f"候選參數組合共 {len(list(__import__('itertools').product(*DEFAULT_GRID.values())))} 組；"
               f"資料共 {len(eng.idx)} 個交易日（{eng.idx[0]:%Y-%m-%d} ~ {eng.idx[-1]:%Y-%m-%d}）。")
    if st.button("▶ 執行 Walk-Forward 驗證"):
        bar = st.progress(0.0, text="回測中…")
        res = walk_forward(eng, train_days=train_days, test_days=test_days, progress=lambda x: bar.progress(x))
        bar.empty()
        if res is None:
            st.error("資料天數不足以切出訓練+測試視窗，請縮短視窗長度或擴大股票池。")
        else:
            st.session_state["wf"] = res
            st.session_state["final_params"] = res["final_params"]
            st.rerun()

    wf = st.session_state.get("wf")
    if wf:
        o = wf["oos_stats"]
        curve, bh = bench_return(eng.bench_close, wf["oos_equity"].index) if len(wf["oos_equity"]) else (pd.Series(dtype=float), np.nan)
        lv, hd, bl = verdict(wf, bh)
        verdict_banner(lv, hd, bl)

        def f(x, fmt="{:.2f}", na="—"):
            return na if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)

        m = st.columns(6)
        m[0].metric("樣本外交易筆數", f"{o['n']}", "n<30 不可靠" if o["n"] < 30 else "")
        m[1].metric("勝率", f(o["win_rate"], "{:.1f}%"), f"95%CI {f(o['wr_lo'], '{:.0f}')}~{f(o['wr_hi'], '{:.0f}')}%")
        m[2].metric("平均獲利 / 平均虧損", f"{f(o['avg_win'], '{:+.2f}')}% / {f(o['avg_loss'], '{:+.2f}')}%")
        m[3].metric("每筆期望值", f(o["expectancy"], "{:+.2f}%"), f"t={f(o['tstat'])}")
        m[4].metric("盈虧因子 / 賺賠比", f"{f(o['profit_factor'])} / {f(o['payoff'])}")
        m[5].metric("最大連虧", f"{o['max_consec_loss']} 次")
        m2 = st.columns(5)
        m2[0].metric("樣本外總報酬", f(o["total_ret"], "{:+.1f}%"), f"大盤 {f(bh, '{:+.1f}')}%")
        m2[1].metric("年化報酬", f(o["cagr"], "{:+.1f}%") if not np.isnan(o["cagr"]) else "期間過短")
        m2[2].metric("最大回撤", f(o["mdd"], "-{:.1f}%"))
        m2[3].metric("Sharpe", f(o["sharpe"]))
        m2[4].metric("平均持有", f(o["avg_hold"], "{:.1f} 日"))

        if len(wf["oos_equity"]):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=wf["oos_equity"].index, y=wf["oos_equity"].values, name="策略（樣本外串接）", line=dict(color="#f59e0b", width=2.2)))
            if len(curve):
                fig.add_trace(go.Scatter(x=curve.index, y=curve.values, name="加權指數買進持有", line=dict(color="#38bdf8", width=1.6)))
            fig.update_layout(height=340, title="樣本外淨值（起點=1）", paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#fff"))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### 各折明細（訓練期 vs 測試期）")
        fd = wf["folds"].copy()
        fd = fd.rename(columns={"fold": "折", "train": "訓練期", "test": "測試期", "params": "訓練期選出的參數", "train_n": "訓練筆數",
                                "train_exp": "訓練期望值%", "test_n": "測試筆數", "test_exp": "測試期望值%",
                                "test_ret": "測試報酬%", "test_mdd": "測試MDD%", "rank_pct": "測試期排名百分位"})
        st.dataframe(fd.round(2), use_container_width=True, hide_index=True)
        st.caption(f"訓練期平均期望值 {f(wf['is_expectancy'], '{:+.2f}%')} → 樣本外 {f(o['expectancy'], '{:+.2f}%')}；"
                   f"所選參數在測試期的排名中位數 {f(wf['rank_pct_median'], '{:.0f}')} 百分位（≈50 代表挑參數沒有增值）。"
                   f"各折選到的權重預設：{wf['preset_selection']}（越分散代表參數越不穩定）。")

        st.markdown("##### 🎲 蒙地卡羅（區塊自助法）— 依樣本外交易損益")
        trs = wf["oos_trades"]["net_pct"].tolist() if len(wf["oos_trades"]) else []
        mc = mc_ruin(trs)
        if not mc:
            st.info("樣本外交易少於 5 筆，無法做蒙地卡羅。")
        else:
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("60 筆後平均淨值", f"{mc['end_mean']:.2f}")
            a2.metric("5% 最差淨值", f"{mc['end_p5']:.2f}")
            a3.metric("95% 信賴最大回撤", f"-{mc['mdd95']:.1f}%")
            a4.metric("淨值腰斬機率", f"{mc['p_ruin']:.2f}%")
            fig2 = go.Figure()
            for row in mc["curves"][:60]:
                fig2.add_trace(go.Scatter(y=row, mode="lines", line=dict(width=.6, color="rgba(56,189,248,.18)"), showlegend=False))
            fig2.add_trace(go.Scatter(y=mc["curves"].mean(axis=0), line=dict(width=2.4, color="#f59e0b"), name="平均"))
            fig2.update_layout(height=320, paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#fff"),
                               xaxis_title="交易筆數", yaxis_title="淨值（起點1，每筆約25%資金）")
            st.plotly_chart(fig2, use_container_width=True)
            if len(trs) < 30:
                st.caption("⚠ 樣本少於 30 筆，蒙地卡羅只是在重複抽你手上很少的資料，低估真實風險的可能性很高。")

        st.markdown("##### 🔬 訊號預測力檢驗（整個股票池、不限於實際下單的標的）")
        hz = st.select_slider("預測期間（交易日）", [5, 10, 15, 20], value=10)
        sq = signal_quality(eng, params.preset, hz)
        q1, q2, q3 = st.columns(3)
        q1.metric("Rank IC 平均", f(sq["ic_mean"], "{:+.3f}"), "分數 vs 未來報酬的排序相關")
        q2.metric("IC t 值", f(sq["ic_t"]), "|t|>2 才算顯著")
        q3.metric("IC IR", f(sq["ic_ir"]))
        if len(sq["quintile"]):
            st.dataframe(sq["quintile"].round(2), use_container_width=True)
            qq = sq["quintile"]
            top, bot = qq["平均報酬"].iloc[-1], qq["平均報酬"].iloc[0]
            mono = qq["平均報酬"].is_monotonic_increasing
            st.caption(("高分組報酬高於低分組（{:+.2f}% vs {:+.2f}%），".format(top, bot) if top > bot else
                        "高分組報酬並未高於低分組（{:+.2f}% vs {:+.2f}%），".format(top, bot))
                       + ("且五分位單調遞增。" if mono else "五分位並非單調，分數的排序能力有限。")
                       + " 若 IC 接近 0，代表這套分數對『預測』沒有實質幫助，別被漂亮的回測曲線騙了。")
        if len(wf["oos_trades"]):
            with st.expander("樣本外逐筆交易明細"):
                t = wf["oos_trades"].copy()
                t["code"] = t["code"].map(label)
                t["entry_date"] = pd.to_datetime(t["entry_date"]).dt.strftime("%Y-%m-%d")
                t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.strftime("%Y-%m-%d")
                st.dataframe(t.rename(columns={"code": "標的", "entry_date": "進場日(開盤)", "exit_date": "出場日", "fill": "成交價",
                                               "exit": "出場價", "reason": "出場原因", "days": "持有日", "net_pct": "淨損益%",
                                               "r_mult": "R倍數", "fold": "折"}).round(2), use_container_width=True, hide_index=True)
    else:
        st.info("按上方按鈕開始驗證。第一次執行約需數十秒到數分鐘（視股票池大小）。")

# ============================================================================
# Tab 5：篩選器
# ============================================================================
with tab_scr:
    st.markdown("### 🛠️ 15 項全景篩選器（對整個流動性股票池，不受推薦過濾影響）")
    snap = snapshot(eng, params.preset)
    snap = snap[snap["liquid"]]
    chosen = []
    with st.expander("勾選條件（全部 AND）", expanded=True):
        cols = st.columns(3)
        for i, name in enumerate(SCREEN_FLAGS):
            if cols[i % 3].checkbox(name, key=f"scr_{i}"):
                chosen.append(name)
        s1, s2 = st.columns(2)
        mb5 = s1.slider("5MA 乖離上限 (%)", 1.0, 15.0, 15.0, 0.5, key="scr_b5")
        mb20 = s2.slider("20MA 乖離上限 (%)", 3.0, 40.0, 40.0, 1.0, key="scr_b20")
    res = snap.copy()
    for name in chosen:
        res = res[res[name]]
    res = res[(res["bias5"] <= mb5) & (res["bias20"] <= mb20)].sort_values("score", ascending=False)
    if res.empty:
        st.warning("沒有符合的標的，請放寬條件。")
    else:
        show = pd.DataFrame({"標的": [label(c) for c in res.index], "分數": res["score"].round(1), "收盤": res["close"].round(2),
                             "漲跌%": res["pct"].round(2), "成交(張)": res["volume_lots"].round(0).astype(int),
                             "5日均額(億)": res["turnover_yi"].round(2), "5MA乖離%": res["bias5"].round(2),
                             "20MA乖離%": res["bias20"].round(2), "K": res["K"].round(1), "RSI": res["RSI"].round(1),
                             "通過推薦過濾": np.where(res["eligible"], "✔", "")})
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(f"符合 {len(res)} 檔 / 流動性股票池 {len(snap)} 檔。")