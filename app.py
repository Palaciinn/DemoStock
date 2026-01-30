import streamlit as st
import pandas as pd
import numpy as np
import os
from openai import OpenAI

# =========================
# Config UI
# =========================
st.set_page_config(page_title="Demo IA – Compras e Inventario Taller", layout="wide")
st.title("🚗 IA para gestión de compras e inventario del taller")

# =========================
# GROQ (OpenAI-compatible)
# Base URL oficial Groq: https://api.groq.com/openai/v1
# =========================
groq_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))

# Debug seguro (NO muestra la clave completa)
st.caption("🔧 Debug conexión IA (Groq)")
st.caption(f"GROQ_API_KEY cargada: {'Sí' if groq_key else 'No'}")
if groq_key:
    st.caption(f"Prefijo: {groq_key[:4]}...  Longitud: {len(groq_key)}")
else:
    st.caption("Añade GROQ_API_KEY en Streamlit Cloud → Manage app → Settings → Secrets")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=groq_key
) if groq_key else None

# Modelo recomendado (puedes cambiarlo)
# Groq docs: llama-3.3-70b-versatile (recomendado en migraciones/deprecations)
MODEL_ID = "llama-3.3-70b-versatile"

# =========================
# Upload
# =========================
file = st.file_uploader("📤 Subir Excel", type=["xlsx"])

# =========================
# Helpers
# =========================
def factor_estacional(categoria, mes):
    categoria = str(categoria).lower()
    if categoria == "a/c" and mes in [5, 6, 7]:
        return 1.3
    if categoria == "baterias" and mes in [11, 12, 1, 2]:
        return 1.25
    if categoria == "itv" and mes in [3, 9]:
        return 1.2
    return 1.0

# =========================
# Main
# =========================
if file:
    df = pd.read_excel(file)

    st.subheader("📄 Datos cargados")
    st.dataframe(df)

    required = [
        "articulo", "categoria", "stock_actual", "stock_minimo",
        "ventas_mes_1", "ventas_mes_2", "ventas_mes_3", "mes", "precio_compra"
    ]

    if not all(col in df.columns for col in required):
        st.error("❌ El Excel no tiene todas las columnas necesarias.")
        st.caption("Columnas obligatorias:")
        st.code(", ".join(required))
    else:
        # Sanitización mínima (por si viene como texto)
        for col in ["stock_actual", "stock_minimo", "ventas_mes_1", "ventas_mes_2", "ventas_mes_3", "mes", "precio_compra"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if df[["stock_actual", "stock_minimo", "ventas_mes_1", "ventas_mes_2", "ventas_mes_3", "mes", "precio_compra"]].isna().any().any():
            st.warning("⚠️ Hay valores no numéricos o vacíos en columnas numéricas. Se han convertido a NaN.")

        # ======================
        # Cálculos
        # ======================
        df["media_3m"] = df[["ventas_mes_1", "ventas_mes_2", "ventas_mes_3"]].mean(axis=1)

        df["factor_estacional"] = df.apply(
            lambda r: factor_estacional(r["categoria"], int(r["mes"]) if not pd.isna(r["mes"]) else 0),
            axis=1
        )

        df["consumo_previsto"] = (df["media_3m"] * df["factor_estacional"]).round(0)

        df["pedido_recomendado"] = (
            df["consumo_previsto"] + df["stock_minimo"] - df["stock_actual"]
        )
        df["pedido_recomendado"] = df["pedido_recomendado"].fillna(0).apply(lambda x: max(0, int(x)))

        df["riesgo_rotura"] = np.where(
            df["stock_actual"] < df["consumo_previsto"] * 0.3,
            "ALTO",
            "OK"
        )

        df["inmovilizado"] = np.where(
            (df["ventas_mes_1"] + df["ventas_mes_2"] + df["ventas_mes_3"]).fillna(0) == 0,
            "SI",
            "NO"
        )

        df["valor_inmovilizado"] = np.where(
            df["inmovilizado"] == "SI",
            (df["stock_actual"].fillna(0) * df["precio_compra"].fillna(0)),
            0
        )

        # ======================
        # Salidas
        # ======================
        st.subheader("📊 Recomendaciones automáticas")
        st.dataframe(df[
            ["articulo", "consumo_previsto", "stock_actual",
             "pedido_recomendado", "riesgo_rotura", "inmovilizado", "valor_inmovilizado"]
        ])

        st.subheader("⚠️ Alertas de rotura")
        st.dataframe(df[df["riesgo_rotura"] == "ALTO"][["articulo", "stock_actual", "consumo_previsto"]])

        st.subheader("🧊 Stock inmovilizado")
        st.dataframe(df[df["inmovilizado"] == "SI"][["articulo", "stock_actual", "valor_inmovilizado"]])

        total_muerto = float(df["valor_inmovilizado"].sum())
        st.metric("💰 Dinero inmovilizado en almacén (€)", round(total_muerto, 2))

        # ======================
        # IA (Groq)
        # ======================
        st.subheader("🧠 Análisis con IA (resumen ejecutivo)")

        if not groq_key or client is None:
            st.warning("Falta configurar GROQ_API_KEY en Secrets para usar el análisis con IA.")
        else:
            top_riesgo = df[df["riesgo_rotura"] == "ALTO"].copy()
            top_inmo = df[df["inmovilizado"] == "SI"].copy()
            top_pedido = df.sort_values("pedido_recomendado", ascending=False).head(10).copy()

            payload = {
                "mes": int(df["mes"].dropna().iloc[0]) if df["mes"].dropna().shape[0] > 0 else None,
                "kpis": {
                    "dinero_inmovilizado": float(df["valor_inmovilizado"].sum()),
                    "num_alertas_rotura": int((df["riesgo_rotura"] == "ALTO").sum()),
                    "num_inmovilizados": int((df["inmovilizado"] == "SI").sum()),
                },
                "top_pedido": top_pedido[
                    ["articulo", "categoria", "consumo_previsto", "stock_actual", "stock_minimo", "pedido_recomendado"]
                ].to_dict(orient="records"),
                "alertas_rotura": top_riesgo[
                    ["articulo", "categoria", "consumo_previsto", "stock_actual"]
                ].to_dict(orient="records"),
                "inmovilizados": top_inmo[
                    ["articulo", "categoria", "stock_actual", "valor_inmovilizado"]
                ].to_dict(orient="records"),
            }

            st.caption("🔎 Debug IA: payload generado correctamente.")
            st.caption(f"Modelo: {MODEL_ID} | top_pedido: {len(payload['top_pedido'])} | alertas: {len(payload['alertas_rotura'])} | inmovilizados: {len(payload['inmovilizados'])}")

            if st.button("Generar análisis con IA"):
                with st.spinner("Analizando inventario (Groq)..."):
                    try:
                        completion = client.chat.completions.create(
                            model=MODEL_ID,
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "Eres un asesor experto en gestión de compras e inventario para talleres. "
                                        "Analiza datos y devuelve un resumen ejecutivo claro, accionable y conciso."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": (
                                        "Datos procesados (JSON):\n"
                                        f"{payload}\n\n"
                                        "Devuelve:\n"
                                        "1) 3 riesgos operativos principales (roturas) con acciones.\n"
                                        "2) 3 oportunidades de ahorro (sobrestock/inmovilizado).\n"
                                        "3) Lista priorizada de compra (máximo 8 items).\n"
                                        "4) Una frase final tipo 'próximo paso' para el jefe de taller.\n"
                                        "Formato: bullets, conciso, español de España."
                                    ),
                                },
                            ],
                            temperature=0.2,
                        )
                        text = completion.choices[0].message.content
                        st.success("✅ Listo")
                        st.write(text)

                    except Exception as e:
                        st.error("❌ No se ha podido conectar con Groq (clave inválida, permisos o límites).")
                        st.caption(f"Detalle técnico: {type(e).__name__}: {e}")
else:
    st.info("📌 Sube un Excel para empezar (usa la plantilla).")
