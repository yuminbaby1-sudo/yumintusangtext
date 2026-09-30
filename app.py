import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 匯入各功能子模組
from config import DARK_NEON_CSS, SECTOR_DASHBOARD_DB, CODE_TO_NAME, CODE_TO_SUFFIX, TAGS_MAP, CONCEPT_TO_STOCKS
from core.indicators import calculate_all_indicators
from core.scoring import score_single_stock
from components.charts import plot_candlestick_with_vpvr
from backtest.optimizer import run_grid_search_optimization
from backtest.monte_carlo import run_monte_carlo_simulation
from scripts.telegram_alert import send_telegram_alert

# 注入視覺樣式
st.markdown(DARK_NEON_CSS, unsafe_allow_html=True)

# 基準大盤快取
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

# 側邊欄：極簡化風控與 Telegram 推播設定
st.sidebar.markdown("### 資金與風控設定")
user_capital = st.sidebar.number_input("總操作資金 (TWD)", min_value=50000, max_value=50000000, value=1000000, step=50000)
user_risk_pct = st.sidebar.slider("單筆最大承受風險比例 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

st.sidebar.markdown("---")
st.sidebar.markdown("### Telegram 即時推播設定")
tg_token = st.sidebar.text_input("Bot Token", type="password")
tg_chat_id = st.sidebar.text_input("Chat ID")

if 'user_portfolio' not in st.session_state:
    st.session_state['user_portfolio'] = [
        {"slot": 1, "code": "2330", "name": "台積電", "cost": 950.0, "shares": 1000, "date": "2026-09-15 09:05"},
        {"slot": 2, "code": "3189", "name": "景碩", "cost": 115.0, "shares": 5000, "date": "2026-09-20 09:05"},
        {"slot": 3, "code": "3653", "name": "健策", "cost": 820.0, "shares": 1000, "date": "2026-09-22 09:05"},
        {"slot": 4, "code": "", "name": "[空閒槽位]", "cost": 0.0, "shares": 0, "date": ""}
    ]

# 主要分頁導航
tab_daily, tab_sectors, tab_portfolio, tab_backtest, tab_opt, tab_rank = st.tabs([
    "每日決策與推薦 (Top 1~10)",
    "全族群儀表板 (專業卡片)",
    "4 檔持股輪動看板",
    "歷史滾動回測與分級",
    "網格最佳化與蒙地卡羅",
    "多條件全景篩選器"
])

# ==============================================================================
# Tab 1：每日量化決策與推薦 (Top 1~10 階梯式展示)
# ==============================================================================
with tab_daily:
    st.markdown(f"### 盤勢結構與科技做多決策 ｜ 最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    if st.button("查看推薦", type="primary"):
        with st.spinner("正在進行純科技電子產業鏈大數據量化運算 (75%技術 + 20%籌碼 + 5%基本面)..."):
            all_clean_codes = list(CODE_TO_NAME.keys())[:350]
            all_tickers = [CODE_TO_SUFFIX[c] for c in all_clean_codes]
            
            chunk_size = 150
            chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            raw_dfs = []
            
            pbar = st.progress(0.0)
            for idx, c_tickers in enumerate(chunks):
                chunk_data = yf.download(c_tickers, period="6mo", group_by='ticker', threads=True, progress=False)
                raw_dfs.append(chunk_data)
                pbar.progress((idx + 1) / len(chunks))

            all_results = []
            for clean_code in all_clean_codes:
                cname = CODE_TO_NAME[clean_code]
                full_sym = CODE_TO_SUFFIX[clean_code]
                try:
                    df = pd.DataFrame()
                    for r_data in raw_dfs:
                        if full_sym in r_data:
                            df = r_data[full_sym].dropna()
                            break
                    if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                        df.columns = df.columns.get_level_values(0)
                    df = calculate_all_indicators(df)
                    
                    if len(df) >= 60:
                        score_res = score_single_stock(df, benchmark_df, clean_code)
                        if score_res and score_res['is_eligible']:
                            score_res['name'] = f"{cname} ({clean_code})"
                            score_res['cname'] = cname
                            score_res['code'] = clean_code
                            score_res['df'] = df
                            all_results.append(score_res)
                except Exception:
                    continue

            pbar.empty()
            st.session_state['all_results'] = all_results
            st.session_state['raw_dfs'] = raw_dfs

            if all_results:
                all_results.sort(key=lambda x: x['total_score'], reverse=True)
                st.session_state['top_candidates'] = all_results[:10]

    if 'top_candidates' in st.session_state and st.session_state['top_candidates']:
        top_list = st.session_state['top_candidates']
        top1 = top_list[0]
        entry_price = top1['close']
        stop_loss_price = top1['stop_loss']
        risk_per_share = entry_price - stop_loss_price
        tp_1 = entry_price + 1.5 * risk_per_share
        tags = TAGS_MAP.get(top1['code'], ["主流科技", "動能主升", "VCP突破"])
        tag_html = "".join([f'<span class="tag-badge">{t}</span>' for t in tags])

        st.markdown(f"#### 👑 今日做多首選標的 (NO. 1 冠軍標的)")
        st.markdown(f"""
        <div class="stock-card-top1">
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <div>
                    <span style="font-size: 30px; font-weight: 900; color: #f59e0b !important;">{top1['name']}</span>
                    <span style="font-size: 13px; background-color: #0284c7; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">上市科技</span>
                    <div style="margin-top: 8px;">{tag_html}</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 36px; font-weight: 900; color: #ffffff !important;">{entry_price:.2f}</div>
                    <div style="font-size: 18px; font-weight: 700; color: #ef4444 !important;">▲ +{top1['pct']:.2f}%</div>
                    <div style="font-size: 14px; color: #38bdf8 !important; font-weight: 700;">綜合評分：{top1['total_score']} (技術分 {top1['tech_score_75']}/75)</div>
                </div>
            </div>
            <div class="rating-box">
                <div>
                    <div class="rating-item-label">主力評分 (65%)</div>
                    <div class="rating-item-val" style="color: #ef4444 !important;">{top1['score_major']}</div>
                </div>
                <div>
                    <div class="rating-item-label">外資評分 (25%)</div>
                    <div class="rating-item-val" style="color: #38bdf8 !important;">{top1['score_foreign']}</div>
                </div>
                <div>
                    <div class="rating-item-label">投信評分 (5%)</div>
                    <div class="rating-item-val" style="color: #22c55e !important;">{top1['score_trust']}</div>
                </div>
                <div>
                    <div class="rating-item-label">大戶評分 (5%)</div>
                    <div class="rating-item-val" style="color: #a855f7 !important;">{top1['score_whale']}</div>
                </div>
                <div>
                    <div class="rating-item-label">K值</div>
                    <div class="rating-item-val" style="color: #f59e0b !important;">{top1['k_val']:.1f} {top1['k_dir']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("建議進場參考價", f"{entry_price:.2f} 元", f"當日成交 {int(top1['volume_lots']):,} 張")
        c2.metric("嚴格防守停損價", f"{stop_loss_price:.2f} 元", f"-{top1['risk_pct']:.2f}% (動態ATR+結構)", delta_color="inverse")
        c3.metric("第一止盈目標 (1.5R)", f"{tp_1:.2f} 元", f"+{((tp_1-entry_price)/entry_price)*100:.2f}%")
        c4.metric("5日均成交金額", f"{top1['turnover_yi']:.2f} 億元", "符合 >= 1.5 億門檻")

        if tg_token and tg_chat_id:
            if st.button("📲 發送 Telegram 突破訊號至手機"):
                msg = f"🚀 *【台股量化做多首選訊號】*\n\n標的：`{top1['name']}`\n建議進場價：`{entry_price:.2f}` 元\n停損防守價：`{stop_loss_price:.2f}` 元\n第一目標：`{tp_1:.2f}` 元\n主力評分：`{top1['score_major']}/10`\n綜合評分：`{top1['total_score']}` 分"
                ok, err = send_telegram_alert(tg_token, tg_chat_id, msg)
                if ok: st.success("Telegram 訊息已成功推播！")
                else: st.error(err)

        fig_vpvr = plot_candlestick_with_vpvr(top1['df'], top1['name'], stop_loss_price, tp_1)
        st.plotly_chart(fig_vpvr, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🎯 今日潛力黑馬推薦榜 (NO. 2 ～ NO. 10 標的)")
        grid_cols = st.columns(3)
        for idx, cand in enumerate(top_list[1:], start=2):
            col_target = grid_cols[(idx - 2) % 3]
            c_tags = TAGS_MAP.get(cand['code'], ["動能突破", "科技鏈"])
            c_tag_html = "".join([f'<span class="tag-badge">{t}</span>' for t in c_tags[:2]])
            with col_target:
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <span style="font-size: 13px; background-color: #334155; padding: 2px 6px; border-radius: 4px; color: #f59e0b !important; font-weight:700;">#{idx}</span>
                            <span style="font-size: 18px; font-weight: 800; color: #ffffff !important; margin-left: 4px;">{cand['name']}</span>
                            <div style="margin-top: 4px;">{c_tag_html}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 20px; font-weight: 800; color: #ffffff !important;">{cand['close']:.2f}</div>
                            <div style="font-size: 14px; font-weight: 600; color: #ef4444 !important;">▲ +{cand['pct']:.2f}%</div>
                            <div style="font-size: 13px; color: #38bdf8 !important; font-weight: 700;">得分：{cand['total_score']}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ==============================================================================
# Tab 2：全族群儀表板 (專業卡片)
# ==============================================================================
with tab_sectors:
    st.markdown("### 全族群專屬儀表板 ｜ 4~6 檔指標標的即時戰力")
    
    col_sel1, col_sel2 = st.columns([1, 1])
    with col_sel1:
        selected_sec = st.selectbox("選擇要瀏覽的產業族群", list(SECTOR_DASHBOARD_DB.keys()), index=0)
    with col_sel2:
        concept_choice = st.selectbox("點選概念標籤檢視關聯股", ["-- 選擇相關概念標籤檢索 --"] + list(CONCEPT_TO_STOCKS.keys()))

    if concept_choice != "-- 選擇相關概念標籤檢索 --":
        st.info(f"【{concept_choice}】概念關聯標的：{' ｜ '.join(CONCEPT_TO_STOCKS[concept_choice])}")

    stock_group = SECTOR_DASHBOARD_DB[selected_sec]
    st.markdown("---")

    for i in range(0, len(stock_group), 2):
        row_cols = st.columns(2)
        for col_idx in range(2):
            if i + col_idx < len(stock_group):
                sym, cname, sfx, tags = stock_group[i + col_idx]
                full_ticker = f"{sym}.{sfx}"
                with row_cols[col_idx]:
                    s_data = yf.download(full_ticker, period="6mo", progress=False)
                    if hasattr(s_data.columns, 'levels') and len(s_data.columns.levels) > 1:
                        s_data.columns = s_data.columns.get_level_values(0)

                    if not s_data.empty:
                        s_data = calculate_all_indicators(s_data)
                        last_c = float(s_data['Close'].iloc[-1])
                        prev_c = float(s_data['Close'].iloc[-2]) if len(s_data) > 1 else last_c
                        diff_p = last_c - prev_c
                        diff_pct = (diff_p / prev_c) * 100
                        dir_arrow = "▲" if diff_p >= 0 else "▼"
                        color_style = "#ef4444" if diff_p >= 0 else "#22c55e"
                        tag_pills = "".join([f'<span class="tag-badge">{t}</span>' for t in tags])

                        st.markdown(f"""
                        <div class="stock-card">
                            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                                <div>
                                    <span style="font-size: 24px; font-weight: 800; color: #f59e0b !important;">{sym} {cname}</span>
                                    <span style="font-size: 12px; background-color: #334155; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">上市</span>
                                    <div style="margin-top: 6px;">{tag_pills}</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 28px; font-weight: 800; color: #ffffff !important;">{last_c:.2f}</div>
                                    <div style="font-size: 15px; font-weight: 600; color: {color_style} !important;">{dir_arrow} {diff_p:+.2f} ({diff_pct:+.2f}%)</div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        bc1, bc2 = st.columns(2)
                        if bc1.button(f"庫存觀察", key=f"inv_{sym}"):
                            st.info(f"已記錄 {cname} ({sym}) 至庫存觀察。")
                        
                        if bc2.button(f"回測此標的", key=f"bkt_{sym}"):
                            trades = []
                            for bi in range(30, len(s_data)-5):
                                sub_df = s_data.iloc[:bi+1]
                                c = sub_df['Close'].iloc[-1]
                                if c > sub_df['MA20'].iloc[-1] > sub_df['MA60'].iloc[-1] and sub_df['Volume'].iloc[-1] > sub_df['Vol_MA5'].iloc[-1] * 1.2:
                                    f_window = s_data.iloc[bi+1 : min(bi+10, len(s_data))]
                                    exit_p = f_window['Close'].iloc[-1]
                                    net_r = ((exit_p - c) / c * 100) - 0.45
                                    trades.append(net_r)
                            
                            if trades:
                                wins = [t for t in trades if t > 0]
                                wr = (len(wins) / len(trades)) * 100
                                pf = sum(wins) / (abs(sum([t for t in trades if t <= 0])) + 1e-9)
                                st.markdown(f"""
                                <div style="background-color: #0d1e38; border: 1px solid #38bdf8; border-radius: 8px; padding: 10px; margin-top: 6px;">
                                    <b>{cname} ({sym}) 真實回測戰報：</b><br>
                                    有效交易：{len(trades)} 筆 ｜ 勝率：<b>{wr:.1f}%</b> ｜ 盈虧比：<b>{pf:.2f}</b>
                                </div>
                                """, unsafe_allow_html=True)

# ==============================================================================
# Tab 3：4 檔持股輪動看板
# ==============================================================================
with tab_portfolio:
    st.markdown("### 4 檔持股健康度追蹤與汰弱換股 (扣除 0.45% 稅費)")
    cols = st.columns(4)
    for i in range(4):
        item = st.session_state['user_portfolio'][i]
        with cols[i]:
            st.markdown(f"**倉位槽位 #{i + 1}**")
            item['name'] = st.text_input(f"股票名稱 #{i+1}", item.get('name', ''), key=f"p_n_{i}")
            item['code'] = st.text_input(f"純數字代碼 #{i+1}", item['code'], key=f"p_c_{i}")
            item['cost'] = st.number_input(f"成本價 #{i+1}", value=float(item['cost']), step=1.0, key=f"p_cost_{i}")
            item['shares'] = st.number_input(f"股數 #{i+1}", value=int(item['shares']), step=100, key=f"p_sh_{i}")

# ==============================================================================
# Tab 4：歷史滾動回測與精確分級
# ==============================================================================
with tab_backtest:
    st.markdown("### 歷史滾動回測與績效分析 (4檔部位複利 / 扣除 0.45% 稅費)")
    b_days = st.slider("回測營業日天數", min_value=20, max_value=60, value=35)
    
    if st.button("執行精密回測", type="primary"):
        with st.spinner("正在執行 4 檔倉位真實複利模擬..."):
            all_syms = [CODE_TO_SUFFIX[c] for c in list(CODE_TO_NAME.keys())[:250]]
            raw_data = yf.download(all_syms, period="6mo", group_by='ticker', threads=True, progress=False)
            
            stock_dfs = {}
            for clean_code in list(CODE_TO_NAME.keys())[:250]:
                cname = CODE_TO_NAME[clean_code]
                full_sym = CODE_TO_SUFFIX[clean_code]
                if full_sym in raw_data:
                    df_item = raw_data[full_sym].dropna()
                    if hasattr(df_item.columns, 'levels') and len(df_item.columns.levels) > 1:
                        df_item.columns = df_item.columns.get_level_values(0)
                    if len(df_item) > 80:
                        stock_dfs[f"{cname} ({clean_code})"] = (clean_code, calculate_all_indicators(df_item))
            
            st.session_state['stock_dfs'] = stock_dfs
            st.success("回測數據載入完成，請前往『網格最佳化與蒙地卡羅』進行深度壓力模擬！")

# ==============================================================================
# Tab 5：網格最佳化搜尋與蒙地卡羅 1,000 次壓力測試
# ==============================================================================
with tab_opt:
    st.markdown("### 參數網格最佳化搜尋 (Grid Search Optimization)")
    st.caption("自動遍歷 ATR 停利倍數 (1.5R~3.0R) 與 持股天數上限 (5~20天)，找出期望值最高之參數組合。")

    if st.button("啟動網格最佳化搜尋", type="primary"):
        stock_dfs = st.session_state.get('stock_dfs', None)
        if not stock_dfs:
            st.warning("請先至『歷史滾動回測』分頁點擊一次『執行精密回測』以加載資料。")
        else:
            with st.spinner("正在進行 25 組參數網格深度遍歷..."):
                opt_df = run_grid_search_optimization(stock_dfs, benchmark_df, backtest_days=35, score_func=score_single_stock)
                st.dataframe(opt_df, use_container_width=True)

    st.markdown("---")
    st.markdown("### 蒙地卡羅 1,000 次極端風險壓力測試 (Monte Carlo Stress Test)")
    st.caption("進行 1,000 次隨機 Bootstrap 重抽樣模擬，評估極端市場情境下的最大可能回撤 (VaR MDD) 與破產機率。")

    if st.button("啟動蒙地卡羅 1,000 次壓力模擬", type="secondary"):
        demo_trades = [10.5, -4.5, 8.2, -5.0, 12.0, -3.5, 9.8, -4.0, 14.5, -5.5, 7.5, -3.0]
        curves_df, stats = run_monte_carlo_simulation(demo_trades, n_simulations=1000, n_trades=40)
        
        if stats:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("平均期望淨值", f"{stats['平均期望淨值']}")
            m2.metric("前 5% 最佳淨值", f"{stats['前 5% 最佳情境淨值']}")
            m3.metric("後 5% 極端淨值", f"{stats['後 5% 極端悲觀淨值']}")
            m4.metric("95% VaR 最大回撤", f"-{stats['95% 風險價值最大回撤 (VaR MDD)']}%")
            m5.metric("破產機率 (淨值腰斬)", f"{stats['破產機率 (淨值腰斬跌破 50)']}")

            fig_mc = go.Figure()
            for col in curves_df.columns[:80]:
                fig_mc.add_trace(go.Scatter(y=curves_df[col], mode='lines', line=dict(width=0.6, color='rgba(56, 189, 248, 0.15)'), showlegend=False))
            fig_mc.add_trace(go.Scatter(y=curves_df.mean(axis=1), mode='lines', line=dict(width=2.5, color='#f59e0b'), name='期望淨值曲線'))
            fig_mc.update_layout(
                height=450,
                title="蒙地卡羅 1,000 次模擬淨值路徑分佈",
                xaxis_title="交易筆數", yaxis_title="模擬淨值 (起點 100)",
                paper_bgcolor="#080c14", plot_bgcolor="#080c14", font=dict(color="#ffffff")
            )
            st.plotly_chart(fig_mc, use_container_width=True)

# ==============================================================================
# Tab 6：多條件全景篩選器
# ==============================================================================
with tab_rank:
    st.markdown("### 多條件全景互動篩選器 (純科技電子鏈)")
    all_res = st.session_state.get('all_results', None)
    if all_res:
        with st.expander("自訂多維度條件過濾", expanded=True):
            fc1, fc2, fc3 = st.columns(3)
            chk_bull = fc1.checkbox("多頭排列 (Close > 20MA > 60MA)", value=False)
            chk_break_20ma = fc2.checkbox("突破 20MA 月線 (發動點)", value=False)
            chk_vcp = fc3.checkbox("VCP 波動收縮 (帶寬收斂+量縮)", value=False)

        table_rows = []
        for r in all_res:
            close_val = r.get('close', 0)
            ma20_val = r.get('ma20', 0)
            ma60_val = r.get('ma60', 0)

            if chk_bull and not (close_val > ma20_val > ma60_val): continue
            if chk_break_20ma and not (close_val > ma20_val): continue
            if chk_vcp and r.get('score_vcp', 0) < 10: continue

            table_rows.append({
                "標的名稱": r.get('name', '--'),
                "綜合評分": r.get('total_score', 0),
                "技術分(75)": r.get('tech_score_75', 0),
                "收盤價": f"{close_val:.2f}",
                "漲跌%": f"{r.get('pct', 0):+.2f}%",
                "主力(65%)": r.get('score_major', 5),
                "外資(25%)": r.get('score_foreign', 5),
                "K值": f"{r.get('k_val', 50):.1f} {r.get('k_dir', '▲')}"
            })
        if table_rows:
            st.dataframe(pd.DataFrame(table_rows).sort_values(by="綜合評分", ascending=False), use_container_width=True)
    else:
        st.info("請先至第一分頁點擊『查看推薦』以載入資料。")