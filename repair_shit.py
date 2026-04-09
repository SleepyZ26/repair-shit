import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re

st.set_page_config(page_title="维修分析Dashboard（稳健版）", layout="wide")
st.title("🔧 维修分析 Dashboard（稳健版）")

file = st.file_uploader("上传维修报告（Excel/CSV）", type=["xlsx", "csv"])

# =============================
# 工具函数（防报错核心）
# =============================

def safe_columns(df):
    df.columns = df.columns.astype(str).str.strip().str.lower()
    return df


def ensure_column(df, col, default=None):
    if col not in df.columns:
        df[col] = default
    return df


def calc_tat(row):
    try:
        if pd.isna(row["received_date"]) or pd.isna(row["shipment_date"]):
            return None
        if row["shipment_date"] < row["received_date"]:
            return None
        return np.busday_count(row["received_date"].date(), row["shipment_date"].date())
    except Exception:
        return None


def extract_sku(text):
    if pd.isna(text):
        return None
    try:
        return re.findall(r"Replaced SKU[:：]?\s*([A-Za-z0-9\-]+)", str(text))
    except Exception:
        return None

# =============================
# 主逻辑
# =============================

if file:
    # 读取
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    df = safe_columns(df)

    # 字段映射（尽量兼容）
    rename_map = {
        "repair order": "repair_id",
        "repair id": "repair_id",
        "order id": "repair_id",
        "date of receipt": "received_date",
        "received date": "received_date",
        "date of shipment": "shipment_date",
        "shipment date": "shipment_date",
        "nation/state": "country",
        "nation": "country",
        "country": "country",
        "warranty status": "repair_type",
        "problem description by avono": "issue_desc",
        "description": "issue_desc",
        "model": "model",
        "sn": "sn",
        "serial number": "sn",
        "person": "technician",
        "repair fee": "repair_fee",
        "return shipment fee": "shipping_fee"
    }

    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # 确保关键列存在（防KeyError）
    for col in ["received_date", "shipment_date", "country", "repair_type", "issue_desc", "model", "sn"]:
        df = ensure_column(df, col)

    # 日期
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"], errors="coerce")

    # TAT
    df["TAT"] = df.apply(calc_tat, axis=1)

    # 类型
    type_map = {"iw": "保内", "ow": "保外", "doa": "DOA"}
    df["repair_type"] = df["repair_type"].astype(str).str.lower().map(type_map).fillna(df["repair_type"])

    # 费用
    df["repair_fee"] = pd.to_numeric(df.get("repair_fee", 0), errors="coerce").fillna(0)
    df["shipping_fee"] = pd.to_numeric(df.get("shipping_fee", 0), errors="coerce").fillna(0)
    df["total_cost"] = df["repair_fee"] + df["shipping_fee"]

    # =============================
    # 筛选器（容错）
    # =============================
    st.sidebar.header("筛选条件")

    country_vals = df["country"].dropna().unique().tolist() if "country" in df else []
    type_vals = df["repair_type"].dropna().unique().tolist() if "repair_type" in df else []

    country_filter = st.sidebar.multiselect("国家", country_vals, default=country_vals)
    type_filter = st.sidebar.multiselect("维修类型", type_vals, default=type_vals)

    min_date = df["received_date"].min() if df["received_date"].notna().any() else pd.Timestamp.today()
    max_date = df["received_date"].max() if df["received_date"].notna().any() else pd.Timestamp.today()

    date_range = st.sidebar.date_input("日期范围", [min_date, max_date])

    # 应用筛选（全部加判断）
    if country_filter:
        df = df[df["country"].isin(country_filter)]
    if type_filter:
        df = df[df["repair_type"].isin(type_filter)]

    if isinstance(date_range, list) and len(date_range) == 2:
        df = df[
            (df["received_date"] >= pd.to_datetime(date_range[0])) &
            (df["received_date"] <= pd.to_datetime(date_range[1]))
        ]

    # =============================
    # KPI（保内）
    # =============================
    df_iw = df[df["repair_type"] == "保内"] if "repair_type" in df else pd.DataFrame()

    avg_tat = df_iw["TAT"].dropna().mean() if not df_iw.empty else 0
    rate_5 = (df_iw["TAT"] <= 5).mean() if not df_iw.empty else 0
    rate_10 = (df_iw["TAT"] <= 10).mean() if not df_iw.empty else 0

    # 重复维修
    if "sn" in df:
        df = df.sort_values(by=["sn", "received_date"]) if "received_date" in df else df
        df["repeat"] = df.duplicated(subset=["sn"], keep="first")
        repeat_rate = df["repeat"].mean()
    else:
        repeat_rate = 0

    doa_rate = (df["repair_type"] == "DOA").mean() if "repair_type" in df else 0

    st.subheader("📊 核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("平均TAT", round(avg_tat, 1) if not pd.isna(avg_tat) else 0)
    col2.metric("5天完成率", f"{rate_5:.1%}")
    col3.metric("10天完成率", f"{rate_10:.1%}")
    col4.metric("重复维修率", f"{repeat_rate:.1%}")
    col5.metric("DOA占比", f"{doa_rate:.1%}")

    # =============================
    # 趋势（不依赖repair_id）
    # =============================
    st.subheader("📈 维修趋势")

    if df["received_date"].notna().any():
        df["month"] = df["received_date"].dt.to_period("M").astype(str)
        trend = df.groupby("month").size().reset_index(name="count")

        st.altair_chart(
            alt.Chart(trend).mark_line(point=True).encode(
                x="month",
                y="count",
                tooltip=["month", "count"]
            ), use_container_width=True
        )
    else:
        st.info("无有效日期数据，无法生成趋势")

    # =============================
    # Model分析
    # =============================
    st.subheader("📦 Model分析")

    if "model" in df:
        model_count = df["model"].value_counts().head(10).reset_index()
        model_count.columns = ["model", "count"]

        st.bar_chart(model_count.set_index("model"))

    # =============================
    # SKU分析（容错）
    # =============================
    st.subheader("🔧 SKU分析 Top10")

    df["sku_list"] = df["issue_desc"].apply(extract_sku) if "issue_desc" in df else None
    sku_df = df.explode("sku_list") if "sku_list" in df else pd.DataFrame()

    if not sku_df.empty:
        sku_top = sku_df["sku_list"].dropna().value_counts().head(10)
        st.bar_chart(sku_top)
    else:
        st.info("未识别到SKU数据")

    # =============================
    # 导出
    # =============================
    st.download_button("下载数据", df.to_csv(index=False), file_name="repair_analysis.csv")

else:
    st.info("请上传维修报告文件")
