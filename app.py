import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Demo IA – Compras e Inventario Taller", layout="wide")

st.title("IA para gestión de compras e inventario del taller")

file = st.file_uploader("Subir excel", type=["xlsx"])

def factor_estacional(categoria, mes):
    categoria = str(categoria).lower()
    if categoria == "a/c" and mes in [5,6,7]:
        return 1.3
    if categoria == "baterias" and mes in [11,12,1,2]:
        return 1.25
    if categoria == "itv" and mes in [3,9]:
        return 1.2
    return 1.0

if file:
    df = pd.read_excel(file)

    st.subheader("📄 Datos cargados")
    st.dataframe(df)

    required = ["articulo","categoria","stock_actual","stock_minimo",
                "ventas_mes_1","ventas_mes_2","ventas_mes_3","mes","precio_compra"]

    if not all(col in df.columns for col in required):
        st.error("El Excel no tiene todas las columnas necesarias")
    else:

        df["media_3m"] = df[["ventas_mes_1","ventas_mes_2","ventas_mes_3"]].mean(axis=1)

        df["factor_estacional"] = df.apply(
            lambda r: factor_estacional(r["categoria"], r["mes"]), axis=1
        )

        df["consumo_previsto"] = (df["media_3m"] * df["factor_estacional"]).round(0)

        df["pedido_recomendado"] = (
            df["consumo_previsto"] + df["stock_minimo"] - df["stock_actual"]
        )

        df["pedido_recomendado"] = df["pedido_recomendado"].apply(lambda x: max(0, int(x)))

        df["riesgo_rotura"] = np.where(
            df["stock_actual"] < df["consumo_previsto"] * 0.3,
            "ALTO",
            "OK"
        )

        df["inmovilizado"] = np.where(
            (df["ventas_mes_1"] + df["ventas_mes_2"] + df["ventas_mes_3"]) == 0,
            "SI",
            "NO"
        )

        df["valor_inmovilizado"] = np.where(
            df["inmovilizado"] == "SI",
            df["stock_actual"] * df["precio_compra"],
            0
        )

        st.subheader("📊 Recomendaciones automáticas")

        st.dataframe(df[[
            "articulo","consumo_previsto","stock_actual",
            "pedido_recomendado","riesgo_rotura","inmovilizado","valor_inmovilizado"
        ]])

        st.subheader("⚠️ Alertas de rotura")
        st.dataframe(df[df["riesgo_rotura"] == "ALTO"][[
            "articulo","stock_actual","consumo_previsto"
        ]])

        st.subheader("🧊 Stock inmovilizado")
        st.dataframe(df[df["inmovilizado"] == "SI"][[
            "articulo","stock_actual","valor_inmovilizado"
        ]])

        total_muerto = df["valor_inmovilizado"].sum()

        st.metric("💰 Dinero inmovilizado en almacén (€)", round(total_muerto,2))
