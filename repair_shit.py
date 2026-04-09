import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="维修分析Dashboard", layout="wide")
st.title("🔧 维修分析 Dashboard")

file = st.file_uploader("上传维修报告（Excel/CSV）", type=["xlsx", "csv"])

if file:
    # 读取数据
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    # =========================
    # ✅ 关键修复1：统一列名（解决KeyError）
    # =========================
    df.columns = df.columns.str.strip().str.lower()

    rename_map = {
        "repair order": "repair_id",
        "date of receipt": "received_date",
        "date of shipment": "shipment_date",
        "Nation/State": "country",
        "Nation/State": "country",
        "warranty status": "repair_type",
        "Problem description by AVONO": "issue_desc",
        "model": "model",
        "sn": "sn",
        "person": "technician",
        "repair fee": "repair_fee",
        "return shipment fee": "shipping_fee"
    }

    df = df.rename(columns=rename_map)

    # 👉 防止缺字段直接报错
    required_cols = ["received_date", "shipment_date", "country", "repair_type"]
    for col in required_cols:
        if col not in df.columns:
            st.error(f"❌ 缺少字段: {col}")
            st.write("当前列名：", df.columns.tolist())
            st.stop()

    # =========================
    # 日期处理
    # =========================
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"], errors="coerce")

    # =========================
    # ✅ 关键修复2：工作日TAT
    # =========================
    df["TAT"] = df.apply(
        lambda x: np.busday_count(
            x["received_date"].date(),
            x["shipment_date"].date()
        ) if pd.notnull(x["received_date"]) and pd.notnull(x["shipment_date"]) else None,
        axis=1
    )

    # =========================
    # 类型映射
    # =========================
    type_map = {
        "iw": "保内",
        "ow": "保外",
        "doa": "DOA"
    }
    df["repair_type"] = df["repair_type"].astype(str).str.lower().map(type_map).fillna(df["repair_type"])

    # =========================
    # 费用处理
    # =========================
    df["repair_fee"] = pd.to_numeric(df.get("repair_fee", 0), errors="coerce").fillna(0)
    df["shipping_fee"] = pd.to_numeric(df.get("shipping_fee", 0), errors="coerce").fillna(0)
    df["total_cost"] = df["repair_fee"] + df["shipping_fee"]

    # =========================
    # ✅ 关键修复3：只算保内TAT
    # =========================
    df_iw = df[df["repair_type"] == "保内"]

    if df_iw.empty:
        st.warning("⚠️ 当前数据没有保内维修记录")
        avg_tat, rate_5, rate_10 = 0, 0, 0
    else:
        avg_tat = df_iw["TAT"].mean()
        rate_5 = (df_iw["TAT"] <= 5).mean()
        rate_10 = (df_iw["TAT"] <= 10).mean()

    # =========================
    # 其他KPI
    # =========================
    df = df.sort_values(by="received_date")
    df["repeat"] = df.duplicated(subset=["sn"], keep=False)
    repeat_rate = df["repeat"].mean()

    doa_rate = (df["repair_type"] == "DOA").mean()

    # =========================
    # KPI展示
    # =========================
    st.subheader("📊 核心指标（仅保内）")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("平均TAT(工作日)", round(avg_tat, 1))
    col2.metric("5天完成率", f"{rate_5:.1%}")
    col3.metric("10天完成率", f"{rate_10:.1%}")
    col4.metric("重复维修率", f"{repeat_rate:.1%}")
    col5.metric("DOA占比", f"{doa_rate:.1%}")

    # =========================
    # 结构分析
    # =========================
    st.subheader("📦 结构分析")

    col1, col2, col3 = st.columns(3)

    col1.bar_chart(df["repair_type"].value_counts(normalize=True))
    col1.write("维修类型占比")

    col2.bar_chart(df["country"].value_counts(normalize=True))
    col2.write("国家占比")

    cost_ratio = df.groupby("country")["total_cost"].sum()
    cost_ratio = cost_ratio / cost_ratio.sum()
    col3.bar_chart(cost_ratio)
    col3.write("国家费用占比")

    # =========================
    # 费用分析
    # =========================
    st.subheader("💰 费用分析")

    col1, col2 = st.columns(2)

    col1.bar_chart(df.groupby("country")["repair_fee"].sum())
    col1.write("维修人工费")

    col2.bar_chart(df.groupby("country")["shipping_fee"].sum())
    col2.write("维修物流费")

    # =========================
    # 深度分析
    # =========================
    st.subheader("🔍 深度分析")

    col1, col2 = st.columns(2)

    col1.bar_chart(df["issue_desc"].value_counts().head(10))
    col1.write("Top故障")

    col2.bar_chart(df["TAT"].value_counts().sort_index())
    col2.write("TAT分布（工作日）")

else:
    st.info("请上传维修报告文件")
