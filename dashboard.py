import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="⛅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONFIGURATION DES COULEURS ET STYLE ---
PRIMARY_COLOR = "#00d2ff"
BACKGROUND_COLOR = "#0e1117"
SECONDARY_BG = "#1a1c23"
TEXT_COLOR = "#fafafa"

st.markdown(f"""
    <style>
    .main {{ background-color: {BACKGROUND_COLOR}; color: {TEXT_COLOR}; }}
    .stMetric {{
        background-color: {SECONDARY_BG};
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
    }}
    .stMetric label {{ color: #a0a0a0 !important; }}
    h1, h2, h3 {{ color: {PRIMARY_COLOR} !important; }}
    </style>
""", unsafe_allow_html=True)

# --- CONNEXION GOOGLE SHEETS ---
@st.cache_resource
def connecter_google_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    # 1. Tentative via les secrets Streamlit Cloud
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    # 2. Tentative via un fichier local (pour les tests en local)
    elif os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    else:
        st.error("⚠️ Identifiants Google Sheets introuvables (secrets ou fichier credentials.json manquant).")
        st.stop()

    client = gspread.authorize(creds)
    sheet_name = "meteo_habere_poche" # Remplace par le nom exact de ton Google Sheet si besoin
    sheet = client.open(sheet_name).sheet1
    return sheet

@st.cache_data(ttl=60) # Cache de 60 secondes pour rafraîchir régulièrement
def charger_historique_gsheet():
    try:
        sheet = connecter_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                # CORRECTION : Force la conversion en datetime pour éviter l'erreur .dt
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.dropna(subset=["timestamp"]) # Nettoie les lignes vides
                df = df.sort_values("timestamp").reset_index(drop=True)
                if "pluie" not in df.columns:
                    df["pluie"] = 0.0
                return df
    except Exception as e:
        st.warning(f"⚠️ Connexion au Google Sheet en cours ou échec temporaire : {e}")

    return pd.DataFrame(columns=[
        "timestamp", "heure", "temperature", "ressenti",
        "humidite", "pression", "pression_abs", "vent",
        "rafale", "direction", "pluie"
    ])

# --- CHARGEMENT DES DONNÉES ---
df_hist = charger_historique_gsheet()

# --- BARRE LATÉRALE (SIDEBAR) ---
st.sidebar.title("🎛️ Paramètres")
st.sidebar.markdown("---")

vue = st.sidebar.radio(
    "Choisir la vue",
    ["📊 Temps Réel & Aujourd'hui", "📈 Historique & Tendances", "⚙️ À propos"]
)

st.sidebar.markdown("---")
st.sidebar.info("📍 **Habère-Poche (Haute-Savoie)**\nAltitude : 900m\nStation : Ecowitt WS69")

# --- CORPS DE L'APPLICATION ---
timezone = pytz.timezone("Europe/Paris")
current_timestamp = datetime.now(timezone)

if vue == "📊 Temps Réel & Aujourd'hui":
    st.title("⛅ Habère-Poche - Tableau de Bord Météo")
    st.markdown(f"**Dernière mise à jour :** {current_timestamp.strftime('%d/%m/%Y à %H:%M:%S')}")
    st.markdown("---")

    if df_hist.empty:
        st.warning("Aucune donnée disponible pour le moment dans le Google Sheet.")
    else:
        # Filtrer les données du jour
        df_today = df_hist[df_hist["timestamp"].dt.strftime("%Y-%m-%d") == current_timestamp.strftime("%Y-%m-%d")]

        if df_today.empty:
            # S'il n'y a pas de données aujourd'hui, on prend les dernières enregistrées
            dernier_releve = df_hist.iloc[-1]
            st.info("ℹ️ Pas de données strictement pour aujourd'hui, affichage du dernier relevé disponible :")
        else:
            dernier_releve = df_today.iloc[-1]

        # Affichage des métriques principales en cartes
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                label="🌡️ Température",
                value=f"{dernier_releve.get('temperature', 0):.1f} °C",
                delta=f"Ressenti : {dernier_releve.get('ressenti', 0):.1f} °C"
            )
        with col2:
            st.metric(
                label="💧 Humidité",
                value=f"{dernier_releve.get('humidite', 0)} %"
            )
        with col3:
            st.metric(
                label="💨 Vent moyen",
                value=f"{dernier_releve.get('vent', 0):.1f} km/h",
                delta=f"Rafale : {dernier_releve.get('rafale', 0):.1f} km/h"
            )
        with col4:
            st.metric(
                label="📊 Pression Atm.",
                value=f"{dernier_releve.get('pression', 0):.1f} hPa"
            )

        st.markdown("---")

        # Graphique de la journée
        if not df_today.empty:
            st.subheader("📈 Évolution des températures aujourd'hui")
            fig_temp = px.line(
                df_today, x="timestamp", y="temperature",
                labels={"timestamp": "Heure", "temperature": "Température (°C)"},
                template="plotly_dark"
            )
            fig_temp.update_traces(line_color=PRIMARY_COLOR, line_width=3)
            fig_temp.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_temp, use_container_width=True)
        else:
            st.info("Graphique journalier indisponible (en attente de données pour la journée en cours).")

elif vue == "📈 Historique & Tendances":
    st.title("📈 Historique & Analyses")
    st.markdown("---")

    if df_hist.empty:
        st.warning("Aucune donnée historique à afficher.")
    else:
        # Sélecteur de période
        periode = st.selectbox("Sélectionner la période", ["Dernières 24 heures", "7 derniers jours", "Tout l'historique"])

        df_filtered = df_hist.copy()
        now_dt = pd.Timestamp(current_timestamp.replace(tzinfo=None))

        if periode == "Dernières 24 heures":
            df_filtered = df_hist[df_hist["timestamp"] >= (now_dt - timedelta(hours=24))]
        elif periode == "7 derniers jours":
            df_filtered = df_hist[df_hist["timestamp"] >= (now_dt - timedelta(days=7))]

        # Graphique combiné Température & Humidité
        fig = px.line(
            df_filtered, x="timestamp", y=["temperature", "ressenti"],
            labels={"timestamp": "Date / Heure", "value": "Température (°C)", "variable": "Légende"},
            template="plotly_dark"
        )
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.subheader("🌡️ Suivi des Températures")
        st.plotly_chart(fig, use_container_width=True)

        # Graphique pression / vent
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("💨 Vent et Rafales")
            fig_vent = px.line(df_filtered, x="timestamp", y=["vent", "rafale"], template="plotly_dark")
            fig_vent.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_vent, use_container_width=True)

        with col_b:
            st.subheader("📊 Pression Atmosphérique")
            fig_press = px.line(df_filtered, x="timestamp", y="pression", template="plotly_dark")
            fig_press.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_press, use_container_width=True)

elif vue == "⚙️ À propos":
    st.title("⚙️ À propos du projet")
    st.markdown("""
    Tableau de bord météo personnel développé pour **Habère-Poche** (900m d'altitude).
    - **Capteur :** Ecowitt WS69 7-en-1 + Passerelle GW3000
    - **Stack technique :** Python, Streamlit, Pandas, Plotly, Google Sheets API.
    - **Hébergement :** Streamlit Community Cloud.
    """)
