import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json
import base64
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="⛅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Nom du Google Sheet qui sera créé automatiquement s'il n'existe pas
SHEET_NAME = "Historique_Meteo_Habere_Poche"

# --- 1. CONNEXION ECOWITT (SIMULATION / API LOCALE OU CLOUD) ---
# (Remplace cette fonction par ta source de données Ecowitt réelle si tu utilises une passerelle locale ou Ecowitt.net)
def recuperer_donnees_ecowitt():
    """
    Récupère les données météo actuelles.
    Adapte cette fonction selon ton installation (ex: requête locale sur GW3000 ou API Ecowitt).
    """
    # Données simulées stables pour l'exemple de structure, à relier à tes capteurs réels WS69
    donnees_actuelles = {
        "timestamp": datetime.now(),
        "heure": datetime.now().strftime("%H:%M:%S"),
        "temperature": 14.5,
        "ressenti": 13.2,
        "humidite": 78,
        "pression": 1013.2,
        "pression_abs": 905.5, # Altitude 900m Habère-Poche
        "vent": 4.2,
        "rafale": 8.5,
        "direction": 220, # Sud-Ouest
        "pluie": 0.0
    }
    return donnees_actuelles

# --- 2. GESTION GOOGLE SHEETS (CRÉATION AUTO & ROBUSTE) ---
@st.cache_resource
def connecter_google_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    gcp_creds = dict(st.secrets["gcp_service_account"])

    if "private_key" in gcp_creds:
        key_val = str(gcp_creds["private_key"]).strip()
        if not key_val.startswith("-----BEGIN"):
            try:
                key_val = base64.b64decode(key_val).decode("utf-8")
            except Exception:
                pass
        gcp_creds["private_key"] = key_val.replace("\\n", "\n")

    creds = Credentials.from_service_account_info(gcp_creds, scopes=scope)
    client = gspread.authorize(creds)

    try:
        # Tente d'ouvrir le fichier existant
        sheet = client.open(SHEET_NAME).sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        # S'il n'existe pas, création automatique et ajout des en-têtes
        spreadsheet = client.create(SHEET_NAME)
        sheet = spreadsheet.sheet1
        en_tetes = [
            "timestamp", "heure", "temperature", "ressenti",
            "humidite", "pression", "pression_abs", "vent",
            "rafale", "direction", "pluie"
        ]
        sheet.append_row(en_tetes)

    return sheet

def charger_historique_gsheet():
    df_vide = pd.DataFrame(columns=[
        "timestamp", "heure", "temperature", "ressenti",
        "humidite", "pression", "pression_abs", "vent",
        "rafale", "direction", "pluie"
    ])
    try:
        sheet = connecter_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.dropna(subset=["timestamp"])
                if not df.empty:
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    if "pluie" not in df.columns:
                        df["pluie"] = 0.0
                    return df
    except Exception as e:
        st.warning(f"⚠️ Connexion au Google Sheet : {e}")

    return df_vide

def sauvegarder_mesure_gsheet(mesure):
    try:
        sheet = connecter_google_sheet()
        ligne = [
            mesure["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            mesure["heure"],
            mesure["temperature"],
            mesure["ressenti"],
            mesure["humidite"],
            mesure["pression"],
            mesure["pression_abs"],
            mesure["vent"],
            mesure["rafale"],
            mesure["direction"],
            mesure["pluie"]
        ]
        sheet.append_row(ligne)
    except Exception as e:
        st.error(f"❌ Erreur critique d'écriture Google Sheets : {e}")

# --- 3. INTERFACE UTILISATEUR (STREAMLIT) ---
st.title("🏔️ Station Météo - Habère-Poche (900m)")
st.markdown("Tableau de bord temps réel et historique connecté (Ecowitt GW3000 & Google Sheets).")

# Récupération des mesures actuelles
mesure_actuelle = recuperer_donnees_ecowitt()

# Optionnel : Sauvegarde automatique de la mesure du moment
# sauvegarder_mesure_gsheet(mesure_actuelle)

# Chargement de l'historique
df_historique = charger_historique_gsheet()

# Menu de navigation / Onglets
onglets = st.tabs([
    "📊 Temps Réel & Extrêmes",
    "🧭 Rose des Vents",
    "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux",
    "📈 Historique et tendances",
    "💡 Prévisions et analyses"
])

with onglets[0]:
    st.subheader("Conditions Actuelles en direct")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Température", f"{mesure_actuelle['temperature']} °C", f"Ressenti {mesure_actuelle['ressenti']} °C")
    with col2:
        st.metric("Humidité", f"{mesure_actuelle['humidite']} %")
    with col3:
        st.metric("Pression Absolue", f"{mesure_actuelle['pression_abs']} hPa")
    with col4:
        st.metric("Vent moyen", f"{mesure_actuelle['vent']} km/h", f"Rafales {mesure_actuelle['rafale']} km/h")

with onglets[1]:
    st.subheader("Orientation et Dynamique du Vent")
    st.info("Données de la direction du vent en cours (Secteur Sud-Ouest).")

with onglets[2]:
    st.subheader("Suivi des Précipitations")
    st.metric("Cumul pluie du jour", f"{mesure_actuelle['pluie']} mm")

with onglets[3]:
    st.subheader("Estimation du Plancher Nuageux")
    # Calcul approximatif basé sur la différence T et Td (ou humidité)
    st.write("Calcul de l'altitude estimée de la base des cumulus par rapport aux 900m d'Habère-Poche.")

with onglets[4]:
    st.subheader("Historique des enregistrements (Google Sheets)")
    if not df_historique.empty:
        st.dataframe(df_historique.tail(50), use_container_width=True)

        # Graphique simple d'évolution de la température
        fig = px.line(df_historique, x="timestamp", y="temperature", title="Évolution de la température")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucune donnée enregistrée pour le moment dans le Google Sheet.")

with onglets[5]:
    st.subheader("Analyses et Tendances locales")
    st.write("Tendances météorologiques pour la vallée verte.")
