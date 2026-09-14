import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Configuration de la page
st.set_page_config(
    page_title="Tableau de bord météo - Habère-Poche",
    page_icon="⛅",
    layout="wide",
)

st.title("⛅ Tableau de bord météo - Habère-Poche")

# ---------------------------------------------------------
# CONNEXION ET CHARGEMENT DES DONNÉES (À adapter selon ton setup)
# ---------------------------------------------------------
# Exemple avec lecture depuis une base SQLite ou un CSV :
# Remplace cette partie par ta méthode de chargement habituelle
@st.cache_data(ttl=60)
def load_data():
    # Remplace par ta connexion réelle (ex: sqlite3, pandas read_csv, etc.)
    # df = pd.read_sql("SELECT * FROM weather_data ORDER BY timestamp ASC", con=engine)
    # Pour l'exemple, on s'assure que le DataFrame contient bien les colonnes :
    # timestamp, temp, ressenti, humidite, pression, vent_dir, vent_vit, etc.
    try:
        df = pd.read_csv("weather_data.csv")  # Ajuste si tu utilises SQLite
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
    except Exception:
        # Fallback vide si pas de fichier de test immédiat
        df = pd.DataFrame(
            columns=[
                "timestamp",
                "temp",
                "ressenti",
                "humidite",
                "pression",
                "vent_dir",
                "vent_vit",
            ]
        )
    return df


df = load_data()

if df.empty:
    st.warning(
        "Aucune donnée météo trouvée pour le moment. Vérifie ta source de données."
    )
else:
    # Nettoyage de base : suppression des doublons et tri par date strict
    df = df.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"])
    df = df.sort_values("timestamp")

    # ---------------------------------------------------------
    # GRAPHIQUE 1 : TEMPÉRATURE & RESSENTI
    # ---------------------------------------------------------
    st.subheader("Température et Température ressentie (°C)")

    fig_temp = go.Figure()

    # Tracé Température
    fig_temp.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["temp"],
            mode="lines+markers",
            name="Température (°C)",
            line=dict(color="#1f77b4", width=2),
            connectgaps=True,  # Relie les points s'il y a des trous
        )
    )

    # Tracé Ressenti (si présent)
    if "ressenti" in df.columns:
        fig_temp.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["ressenti"],
                mode="lines",
                name="Ressenti (°C)",
                line=dict(color="#aec7e8", width=1.5, dash="dash"),
                connectgaps=True,
            )
        )

    # Calcul intelligent des bornes Y pour éviter d'être écrasé par un pic aberrant isolé
    valid_temp = df["temp"].dropna()
    if not valid_temp.empty:
        y_min = valid_temp.quantile(0.01) - 2
        y_max = valid_temp.quantile(0.99) + 2
        fig_temp.update_yaxes(range=[y_min, y_max])

    fig_temp.update_layout(
        xaxis_title="Temps",
        yaxis_title="°C",
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig_temp, use_container_width=True)

    # ---------------------------------------------------------
    # GRAPHIQUE 2 : HUMIDITÉ RELATIVE
    # ---------------------------------------------------------
    st.subheader("Humidité relative (%)")

    fig_hum = go.Figure()
    fig_hum.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["humidite"],
            mode="lines",
            name="Humidité (%)",
            line=dict(color="#008080", width=2),
            connectgaps=True,
            fill="tozeroy",
            fillcolor="rgba(0, 128, 128, 0.1)",
        )
    )

    fig_hum.update_yaxes(range=[0, 100])
    fig_hum.update_layout(
        xaxis_title="Temps",
        yaxis_title="Humidité",
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig_hum, use_container_width=True)

    # ---------------------------------------------------------
    # GRAPHIQUE 3 : PRESSION ATMOSPHÉRIQUE
    # ---------------------------------------------------------
    st.subheader("Pression atmosphérique (hPa)")

    fig_pres = go.Figure()
    fig_pres.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["pression"],
            mode="lines+markers",
            name="Pression (hPa)",
            line=dict(color="#6a3d9a", width=1.5),
            connectgaps=True,
        )
    )

    valid_pres = df["pression"].dropna()
    if not valid_pres.empty:
        p_min = valid_pres.min() - 2
        p_max = valid_pres.max() + 2
        fig_pres.update_yaxes(range=[p_min, p_max])

    fig_pres.update_layout(
        xaxis_title="timestamp",
        yaxis_title="pression",
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig_pres, use_container_width=True)
