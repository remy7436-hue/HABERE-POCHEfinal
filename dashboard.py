import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Configuration de la page
st.set_page_config(
    page_title="Station Météo — Historique et Tendances",
    layout="wide",
)

st.title("📊 Historique et Tendances Météo")

# --- Chargement ou simulation des données ---
@st.cache_data
def charger_donnees():
    dates = pd.date_range("2026-09-10", periods=168, freq="h")
    np.random.seed(42)
    return pd.DataFrame(
        {
            "datetime": dates,
            "temperature": np.random.uniform(8, 24, size=len(dates)),
            "pression": np.random.uniform(1005, 1025, size=len(dates)),
            "vitesse_vent": np.random.uniform(2, 38, size=len(dates)),
            "dir_vent": np.random.uniform(0, 360, size=len(dates)),
        }
    )

df = charger_donnees()

# --- Fonctions des graphiques Altair ---

def graphique_temperature(data):
    return (
        alt.Chart(data)
        .mark_line(color="#e67e22", strokeWidth=2)
        .encode(
            x=alt.X("datetime:T", title="Date / Heure"),
            y=alt.Y("temperature:Q", title="Température (°C)"),
            tooltip=[
                alt.Tooltip("datetime:T", title="Date", format="%d/%m %H:%M"),
                alt.Tooltip("temperature:Q", title="Temp. (°C)", format=".1f"),
            ],
        )
        .properties(title="Évolution de la Température", height=220)
        .interactive()
    )

def graphique_pression(data):
    return (
        alt.Chart(data)
        .mark_line(color="#27ae60", strokeWidth=2)
        .encode(
            x=alt.X("datetime:T", title="Date / Heure"),
            y=alt.Y("pression:Q", title="Pression (hPa)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("datetime:T", title="Date", format="%d/%m %H:%M"),
                alt.Tooltip("pression:Q", title="Pression (hPa)", format=".1f"),
            ],
        )
        .properties(title="Pression Atmosphérique", height=220)
        .interactive()
    )

def graphique_direction_vent(data):
    # Lignes horizontales de repère pour les 4 points cardinaux
    reperes = pd.DataFrame([
        {"cap": 0, "label": "N (0°)"},
        {"cap": 90, "label": "E (90°)"},
        {"cap": 180, "label": "S (180°)"},
        {"cap": 270, "label": "O (270°)"},
        {"cap": 360, "label": "N (360°)"},
    ])

    lignes_repere = (
        alt.Chart(reperes)
        .mark_rule(color="#bdc3c7", strokeDash=[3, 3], strokeWidth=1)
        .encode(y="cap:Q")
    )

    labels_repere = (
        alt.Chart(reperes)
        .mark_text(align="left", dx=5, dy=-4, fontSize=10, color="#7f8c8d")
        .encode(y="cap:Q", text="label:N")
    )

    # Liaison pointillée entre les relevés
    ligne_liaison = (
        alt.Chart(data)
        .mark_line(color="#e74c3c", strokeWidth=1, opacity=0.3, strokeDash=[2, 2])
        .encode(x="datetime:T", y="dir_vent:Q")
    )

    # Flèches de direction orientées
    fleches = (
        alt.Chart(data)
        .mark_point(shape="arrow", size=110, color="#c0392b", filled=True)
        .encode(
            x=alt.X("datetime:T", title="Date / Heure"),
            y=alt.Y(
                "dir_vent:Q",
                title="Direction du vent (°)",
                scale=alt.Scale(domain=[0, 360]),
                axis=alt.Axis(values=[0, 90, 180, 270, 360]),
            ),
            angle=alt.Angle("dir_vent:Q", scale=alt.Scale(domain=[0, 360])),
            tooltip=[
                alt.Tooltip("datetime:T", title="Heure", format="%d/%m %H:%M"),
                alt.Tooltip("dir_vent:Q", title="Direction (°)", format=".0f"),
                alt.Tooltip("vitesse_vent:Q", title="Vitesse (km/h)", format=".1f"),
            ],
        )
    )

    return (
        (lignes_repere + labels_repere + ligne_liaison + fleches)
        .properties(title="Direction du vent", height=280)
        .interactive()
    )

# --- Affichage dans la page ---
tab_historique, tab_autres = st.tabs(["Historique et tendances", "Autres métriques"])

with tab_historique:
    st.altair_chart(graphique_temperature(df), use_container_width=True)
    st.altair_chart(graphique_pression(df), use_container_width=True)
    st.altair_chart(graphique_direction_vent(df), use_container_width=True)
