import streamlit as st
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="台股看盤系統", layout="wide")
st.title("📈 台股即時/歷史看盤儀表板")

# 側邊欄輸入
stock_id = st.sidebar.text_input("輸入台股代號（例：2330.TW / 0050.TW）", value="2330.TW")
period = st.sidebar.selectbox("選擇時間區間", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)

if stock_id:
    data = yf.download(stock_id, period=period)
    
    if not data.empty:
        # 處理多層欄位名稱
        if hasattr(data.columns, 'levels') and len(data.columns.levels) > 1:
            data.columns = data.columns.get_level_values(0)

        st.subheader(f"{stock_id} K 線圖")
        
        # 繪製 K 線圖
        fig = go.Figure(data=[go.Candlestick(
            x=data.index,
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            name="K線"
        )])
        fig.update_layout(xaxis_rangeslider_visible=False, height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("最新收盤價：", round(float(data['Close'].iloc[-1]), 2))
    else:
        st.error("查無此股票代號資料，請確認格式（上市請加 .TW，上櫃請加 .TWO）")
