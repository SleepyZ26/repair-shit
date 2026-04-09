import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re

st.set_page_config(page_title="维修分析Dashboard（高级版）", layout="wide")
st.title("🔧 维修分析 Dashboard（高级版）")

file = st.file_uploader("上传维修报告（Excel/CSV）", type=["xlsx", "csv"])

if file:
    # 读取数据
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    # -----------------------------
    # 清理列名
    # -----------------------------
    df.columns = df.columns.str.strip().str.lower()

    # -----------------------------
    # 字段映射
    # -----------------------------
    rename_map = {
        "repair order": "repair_id",
        "date of receipt": "received_date",
        "date of shipment": "shipment_date",
        "nation/state": "country",
        "warranty status": "repair_type",
        "problem description by avono": "issue_desc",
        "model": "model",
        "sn": "sn",
        "person": "technician",
        "repair fee": "repair_fee",
        "return shipment fee": "shipping_fee"
    }

    df = df.rename(columns=rename_map)

    # -----------------------------
    # 日期处理
    # -----------------------------
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"], errors="coerce")

    # -----------------------------
    # TAT（工作日）
    # -----------------------------
    def calc_tat(row):
        if pd.isna(row["received_date"]) or pd.isna(row["shipment_date"]):
            return None
        if row["shipment_date"] < row["received_date"]:
            return None
        return np.busday_count(row["received_date"].date(), row["shipment_date"].date())

    df["TAT"] = df.apply(calc_tat, axis=1)

    # -----------------------------
    # 类型映射
    # -----------------------------
    type_map = {"iw": "保内", "ow": "保外", "doa": "DOA"}
    df["repair_type"] = df["repair_type"].astype(str).str.lower().map(type_map).fillna(df["repair_type"])

    # -----------------------------
    # 费用处理
    # -----------------------------
    df["repair_fee"] = pd.to_numeric(df.get("repair_fee", 0), errors="coerce").fillna(0)
    df["shipping_fee"] = pd.to_numeric(df.get("shipping_fee", 0), errors="coerce").fillna(0)
    df["total_cost"] = df["repair_fee"] + df["shipping_fee"]

    # =============================
    # 筛选器
    # =============================
    st.sidebar.header("筛选条件")

    country_filter = st.sidebar.multiselect(
        "国家",
        options=df["country"].dropna().unique(),
        default=df["country"].dropna().unique()
    )

    type_filter = st.sidebar.multiselect(
        "维修类型",
        options=df["repair_type"].dropna().unique(),
        default=df["repair_type"].dropna().unique()
    )

    date_range = st.sidebar.date_input(
        "日期范围",
        [df["received_date"].min(), df["received_date"].max()]
    )

    df = df[
        (df["country"].isin(country_filter)) &
        (df["repair_type"].isin(type_filter)) &
        (df["received_date"] >= pd.to_datetime(date_range[0])) &
        (df["received_date"] <= pd.to_datetime(date_range[1]))
    ]

    # =============================
    # KPI（保内）
    # =============================
    df_iw = df[df["repair_type"] == "保内"]

    avg_tat = df_iw["TAT"].dropna().mean() if not df_iw.empty else 0
    rate_5 = (df_iw["TAT"] <= 5).mean() if not df_iw.empty else 0
    rate_10 = (df_iw["TAT"] <= 10).mean() if not df_iw.empty else 0

    # 重复维修
    df = df.sort_values(by=["sn", "received_date"])
    df["repeat"] = df.duplicated(subset=["sn"], keep="first")

    repeat_rate = df["repeat"].mean()
    doa_rate = (df["repair_type"] == "DOA").mean()

    st.subheader("📊 核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("平均TAT", round(avg_tat, 1))
    col2.metric("5天完成率", f"{rate_5:.1%}")
    col3.metric("10天完成率", f"{rate_10:.1%}")
    col4.metric("重复维修率", f"{repeat_rate:.1%}")
    col5.metric("DOA占比", f"{doa_rate:.1%}")

    # =============================
    # 趋势分析
    # =============================
    st.subheader("📈 维修趋势")

    df["month"] = df["received_date"].dt.to_period("M").astype(str)
    trend = df.groupby("month")["repair_id"].count().reset_index()

    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x="month",
            y="repair_id",
            tooltip=["month", "repair_id"]
        ), use_container_width=True
    )

    # =============================
    # Model分析
    # =============================
    st.subheader("📦 Model分析")

    model_count = df["model"].value_counts().head(10).reset_index()
    model_count.columns = ["model", "count"]

    st.altair_chart(
        alt.Chart(model_count).mark_bar().encode(
            x="model",
            y="count",
            tooltip=["model", "count"]
        ), use_container_width=True
    )

    # Model TAT
    model_tat = df.groupby("model")["TAT"].mean().dropna().sort_values(ascending=False).head(10).reset_index()

    st.altair_chart(
        alt.Chart(model_tat).mark_bar().encode(
            x="model",
            y="TAT",
            tooltip=["model", "TAT"]
        ), use_container_width=True
    )

    # =============================
    # SKU提取（Replaced SKU）
    # =============================
    st.subheader("🔧 更换SKU分析 (Top10)")

    def extract_sku(text):
        if pd.isna(text):
            return None
        match = re.findall(r"Replaced SKU[:：]?\s*([A-Za-z0-9\-]+)", str(text))
        return match if match else None

    df["sku_list"] = df["issue_desc"].apply(extract_sku)

    sku_exploded = df.explode("sku_list")

    sku_top = (
        sku_exploded["sku_list"]
        .dropna()
        .value_counts()
        .head(10)
        .reset_index()
    )

    sku_top.columns = ["SKU", "数量"]

    st.dataframe(sku_top)

    st.altair_chart(
        alt.Chart(sku_top).mark_bar().encode(
            x="SKU",
            y="数量",
            tooltip=["SKU", "数量"]
        ), use_container_width=True
    )

    # =============================
    # 成本分析
    # =============================
    st.subheader("💰 成本分析")

    cost_chart = df.groupby("country")["total_cost"].sum().reset_index()

    st.altair_chart(
        alt.Chart(cost_chart).mark_bar().encode(
            x="country",
            y="total_cost",
            tooltip=["country", "total_cost"]
        ), use_container_width=True
    )

    # =============================
    # 技术员分析
    # =============================
    st.subheader("👨‍🔧 技术员表现")

    tech_perf = df.groupby("technician").agg({
        "repair_id": "count",
        "TAT": "mean"
    }).rename(columns={
        "repair_id": "维修量",
        "TAT": "平均TAT"
    })

    st.dataframe(tech_perf.sort_values("维修量", ascending=False))

    # =============================
    # 数据导出
    # =============================
    st.download_button(
        "下载数据",
        df.to_csv(index=False),
        file_name="repair_analysis.csv"
    )

else:
    st.info("请上传维修报告文件")
