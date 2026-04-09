import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re

st.set_page_config(page_title="维修分析Dashboard（稳健增强版）", layout="wide")
st.title("🔧 维修分析 Dashboard（稳健增强版）")

file = st.file_uploader("上传维修报告（Excel/CSV）", type=["xlsx", "csv"])

# =============================
# 工具函数
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
        matches = re.findall(r"Replaced SKU[:：]?\s*([A-Za-z0-9\-]+)", str(text), flags=re.IGNORECASE)
        return matches if matches else None
    except Exception:
        return None


def safe_ratio(series):
    total = series.sum()
    if total == 0 or pd.isna(total):
        return series * 0
    return series / total


# =============================
# 主逻辑
# =============================
if file:
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    df = safe_columns(df)

    # 字段映射（兼容不同列名）
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

    # 确保关键列存在
    for col in [
        "received_date", "shipment_date", "country", "repair_type",
        "issue_desc", "model", "sn", "technician"
    ]:
        df = ensure_column(df, col)

    # 日期处理
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"], errors="coerce")

    # TAT
    df["TAT"] = df.apply(calc_tat, axis=1)

    # 类型映射
    type_map = {"iw": "保内", "ow": "保外", "doa": "DOA"}
    df["repair_type"] = (
        df["repair_type"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(type_map)
        .fillna(df["repair_type"])
    )

    # 费用
    df["repair_fee"] = pd.to_numeric(df.get("repair_fee", 0), errors="coerce").fillna(0)
    df["shipping_fee"] = pd.to_numeric(df.get("shipping_fee", 0), errors="coerce").fillna(0)
    df["total_cost"] = df["repair_fee"] + df["shipping_fee"]

    # =============================
    # 筛选器
    # =============================
    st.sidebar.header("筛选条件")

    country_vals = sorted(df["country"].dropna().astype(str).unique().tolist()) if "country" in df else []
    type_vals = sorted(df["repair_type"].dropna().astype(str).unique().tolist()) if "repair_type" in df else []
    model_vals = sorted(df["model"].dropna().astype(str).unique().tolist()) if "model" in df else []

    country_filter = st.sidebar.multiselect("国家", country_vals, default=country_vals)
    type_filter = st.sidebar.multiselect("维修类型", type_vals, default=type_vals)
    model_filter = st.sidebar.multiselect("Model", model_vals, default=model_vals)

    min_date = df["received_date"].min() if df["received_date"].notna().any() else pd.Timestamp.today()
    max_date = df["received_date"].max() if df["received_date"].notna().any() else pd.Timestamp.today()
    date_range = st.sidebar.date_input("日期范围", [min_date, max_date])

    # 应用筛选
    if country_filter:
        df = df[df["country"].isin(country_filter)]
    if type_filter:
        df = df[df["repair_type"].isin(type_filter)]
    if model_filter:
        df = df[df["model"].isin(model_filter)]
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        df = df[
            (df["received_date"] >= pd.to_datetime(date_range[0])) &
            (df["received_date"] <= pd.to_datetime(date_range[1]))
        ]

    if df.empty:
        st.warning("当前筛选条件下没有数据，请调整筛选条件。")
        st.stop()

    # =============================
    # KPI
    # =============================
    df_iw = df[df["repair_type"] == "保内"] if "repair_type" in df else pd.DataFrame()

    avg_tat = df_iw["TAT"].dropna().mean() if not df_iw.empty else 0
    rate_5 = (df_iw["TAT"] <= 5).mean() if not df_iw.empty else 0
    rate_10 = (df_iw["TAT"] <= 10).mean() if not df_iw.empty else 0

    if "sn" in df.columns:
        df = df.sort_values(by=["sn", "received_date"])
        df["repeat"] = df.duplicated(subset=["sn"], keep="first")
        repeat_rate = df["repeat"].mean()
    else:
        repeat_rate = 0

    doa_rate = (df["repair_type"] == "DOA").mean() if "repair_type" in df.columns else 0

    st.subheader("📊 核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("平均TAT(保内)", round(avg_tat, 1) if not pd.isna(avg_tat) else 0)
    col2.metric("5天完成率", f"{rate_5:.1%}")
    col3.metric("10天完成率", f"{rate_10:.1%}")
    col4.metric("重复维修率", f"{repeat_rate:.1%}")
    col5.metric("DOA占比", f"{doa_rate:.1%}")

    # =============================
    # 趋势分析
    # =============================
    st.subheader("📈 维修趋势")
    if df["received_date"].notna().any():
        df["month"] = df["received_date"].dt.to_period("M").astype(str)
        trend = df.groupby("month").size().reset_index(name="count")

        trend_chart = alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("month:N", title="月份", sort=None),
            y=alt.Y("count:Q", title="维修数量"),
            tooltip=["month", "count"]
        )
        st.altair_chart(trend_chart, use_container_width=True)
    else:
        st.info("无有效日期数据，无法生成趋势图")

    # =============================
    # 结构分析
    # =============================
    st.subheader("📦 结构分析")
    col1, col2, col3 = st.columns(3)

    repair_type_dist = df["repair_type"].fillna("未知").value_counts(normalize=True).reset_index()
    repair_type_dist.columns = ["repair_type", "ratio"]
    col1.altair_chart(
        alt.Chart(repair_type_dist).mark_bar().encode(
            x=alt.X("repair_type:N", title="维修类型"),
            y=alt.Y("ratio:Q", title="占比"),
            tooltip=["repair_type", alt.Tooltip("ratio:Q", format=".1%")]
        ),
        use_container_width=True
    )
    col1.write("维修类型占比")

    country_dist = df["country"].fillna("未知").value_counts(normalize=True).reset_index()
    country_dist.columns = ["country", "ratio"]
    col2.altair_chart(
        alt.Chart(country_dist).mark_bar().encode(
            x=alt.X("country:N", title="国家"),
            y=alt.Y("ratio:Q", title="占比"),
            tooltip=["country", alt.Tooltip("ratio:Q", format=".1%")]
        ),
        use_container_width=True
    )
    col2.write("国家占比")

    cost_ratio = df.groupby("country", dropna=False)["total_cost"].sum().fillna(0)
    cost_ratio = safe_ratio(cost_ratio).reset_index()
    cost_ratio.columns = ["country", "ratio"]
    col3.altair_chart(
        alt.Chart(cost_ratio).mark_bar().encode(
            x=alt.X("country:N", title="国家"),
            y=alt.Y("ratio:Q", title="费用占比"),
            tooltip=["country", alt.Tooltip("ratio:Q", format=".1%")]
        ),
        use_container_width=True
    )
    col3.write("国家费用占比")

    # =============================
    # 费用分析
    # =============================
    st.subheader("💰 费用分析")
    col1, col2 = st.columns(2)

    repair_fee_by_country = (
        df.groupby("country", dropna=False)["repair_fee"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    col1.altair_chart(
        alt.Chart(repair_fee_by_country).mark_bar().encode(
            x=alt.X("country:N", title="国家", sort="-y"),
            y=alt.Y("repair_fee:Q", title="维修人工费"),
            tooltip=["country", "repair_fee"]
        ),
        use_container_width=True
    )
    col1.write("维修人工费")

    shipping_fee_by_country = (
        df.groupby("country", dropna=False)["shipping_fee"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    col2.altair_chart(
        alt.Chart(shipping_fee_by_country).mark_bar().encode(
            x=alt.X("country:N", title="国家", sort="-y"),
            y=alt.Y("shipping_fee:Q", title="维修物流费"),
            tooltip=["country", "shipping_fee"]
        ),
        use_container_width=True
    )
    col2.write("维修物流费")

    # =============================
    # 故障分析
    # =============================
    st.subheader("🔍 故障分析")
    col1, col2 = st.columns(2)

    issue_top = (
        df["issue_desc"]
        .fillna("未知")
        .astype(str)
        .str.strip()
        .replace("", "未知")
        .value_counts()
        .head(10)
        .reset_index()
    )
    issue_top.columns = ["issue_desc", "count"]
    col1.altair_chart(
        alt.Chart(issue_top).mark_bar().encode(
            x=alt.X("count:Q", title="数量"),
            y=alt.Y("issue_desc:N", sort="-x", title="问题描述"),
            tooltip=["issue_desc", "count"]
        ),
        use_container_width=True
    )
    col1.write("Top问题（基于 Problem description by AVONO）")

    tat_dist = (
        df["TAT"]
        .dropna()
        .astype(int)
        .value_counts()
        .sort_index()
        .reset_index()
    )
    if not tat_dist.empty:
        tat_dist.columns = ["TAT", "count"]
        col2.altair_chart(
            alt.Chart(tat_dist).mark_bar().encode(
                x=alt.X("TAT:O", title="TAT（工作日）"),
                y=alt.Y("count:Q", title="数量"),
                tooltip=["TAT", "count"]
            ),
            use_container_width=True
        )
        col2.write("TAT分布（工作日）")
    else:
        col2.info("无有效TAT数据")

    # =============================
    # Model分析
    # =============================
    st.subheader("📦 Model分析")
    col1, col2 = st.columns(2)

    model_count = (
        df["model"]
        .fillna("未知")
        .astype(str)
        .str.strip()
        .replace("", "未知")
        .value_counts()
        .head(10)
        .reset_index()
    )
    model_count.columns = ["model", "count"]
    col1.altair_chart(
        alt.Chart(model_count).mark_bar().encode(
            x=alt.X("count:Q", title="维修数量"),
            y=alt.Y("model:N", sort="-x", title="Model"),
            tooltip=["model", "count"]
        ),
        use_container_width=True
    )
    col1.write("Model维修量 Top10")

    model_tat = (
        df.groupby("model", dropna=False)["TAT"]
        .mean()
        .dropna()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )
    if not model_tat.empty:
        model_tat.columns = ["model", "avg_tat"]
        col2.altair_chart(
            alt.Chart(model_tat).mark_bar().encode(
                x=alt.X("avg_tat:Q", title="平均TAT"),
                y=alt.Y("model:N", sort="-x", title="Model"),
                tooltip=["model", alt.Tooltip("avg_tat:Q", format=".2f")]
            ),
            use_container_width=True
        )
        col2.write("Model平均TAT Top10")
    else:
        col2.info("无有效Model TAT数据")

    # =============================
    # SKU分析
    # =============================
    st.subheader("🔧 更换SKU分析 Top10")

    df["sku_list"] = df["issue_desc"].apply(extract_sku)
    sku_df = df.explode("sku_list")

    valid_sku = sku_df["sku_list"].dropna().astype(str).str.strip()
    if not valid_sku.empty:
        sku_top = valid_sku.value_counts().head(10).reset_index()
        sku_top.columns = ["SKU", "数量"]

        col1, col2 = st.columns([1, 2])
        col1.dataframe(sku_top, use_container_width=True)
        col2.altair_chart(
            alt.Chart(sku_top).mark_bar().encode(
                x=alt.X("数量:Q", title="数量"),
                y=alt.Y("SKU:N", sort="-x", title="SKU"),
                tooltip=["SKU", "数量"]
            ),
            use_container_width=True
        )
    else:
        st.info("未识别到包含 'Replaced SKU' 的数据")

    # =============================
    # 技术员分析
    # =============================
    st.subheader("👨‍🔧 技术员表现")
    tech_perf = (
        df.groupby("technician", dropna=False)
        .agg(维修量=("sn", "count"), 平均TAT=("TAT", "mean"))
        .reset_index()
        .sort_values(by="维修量", ascending=False)
    )
    st.dataframe(tech_perf, use_container_width=True)

    # =============================
    # 数据导出
    # =============================
    export_df = df.copy()
    if "sku_list" in export_df.columns:
        export_df["sku_list"] = export_df["sku_list"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )

    st.download_button(
        "下载清洗后数据",
        export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="repair_analysis.csv",
        mime="text/csv"
    )

else:
    st.info("请上传维修报告文件")
