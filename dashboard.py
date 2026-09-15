import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Configuration de la page
st.set_page_config(page_title="Station Météo - Habère-Poche", layout="wide")

st.title("Station Météo - Habère-Poche (900m)")
st.markdown("Historique, tendances lissées et rose des vents optimisée.")

# --- CHARGEMENT ET NETTOYAGE DES DONNÉES ---
@st.cache_data(ttl=600)
def load_data():
    # Remplacer par votre lien ou source Google Sheets / CSV habituelle
    # Ici on simule ou récupère les données de la base
    url = "https://docs.google.com/spreadsheets/d/your_sheet_id/export?format=csv"
    try:
        df = pd.read_csv(url)
    except Exception:
        # Données de secours / structure type si besoin
        df = pd.DataFrame(columns=['timestamp', 'temperature', 'humidite', 'pression', 'vent', 'direction'])

    # Nettoyage des anomalies de démarrage (ex: température aberrante -147°C)
    if 'temperature' in df.columns:
        df = df[df['temperature'] > -50]

    return df

df_meteo = load_data()

# --- SECTION 1 : ROSE DES VENTS AMÉLIORÉE ---
st.header("Rose des Vents")

def plot_wind_rose(df):
    if df.empty or 'vent' not in df.columns or 'direction' not in df.columns:
        # Graphique vide par défaut si pas de données
        return px.scatter(title="En attente de données suffisantes...")

    # Définition de paliers de vitesse plus précis pour la colorbar (en km/h)
    bins = [0, 5, 10, 15, 20, 30, 40, 50, 100]
    labels = ['< 5', '5-10', '10-15', '15-20', '20-30', '30-40', '40-50', '> 50']

    df['vent_tranche'] = pd.cut(df['vent'], bins=bins, labels=labels, right=False)

    # Calcul des fréquences par direction et par tranche de vitesse
    wind_freq = df.groupby(['direction', 'vent_tranche'], observed=False).size().reset_index(name='count')

    # Calcul du pourcentage de vents calmes (< 1 km/h)
    calm_count = len(df[df['vent'] < 1])
    total_count = len(df)
    calm_percentage = (calm_count / total_count * 100) if total_count > 0 else 0

    # Création du graphique polaire avec Plotly
    fig = px.bar_polar(
        wind_freq,
        r='count',
        theta='direction',
        color='vent_tranche',
        color_discrete_sequence=px.colors.sequential.Blues,
        template="plotly_white"
    )

    fig.update_layout(
        title=f"Distribution des Vents (Vents calmes : {calm_percentage:.1f}%)",
        polar=dict(
            radialaxis=dict(showticklabels=True, ticks=''),
            angularaxis=dict(direction="clockwise", rotation=90)
        )
    )

    return fig

st.plotly_chart(plot_wind_rose(df_meteo), use_container_width=True)

# --- SECTION 2 : TENDANCES LISSÉES ---
st.header("Historique & Tendances Lissées")

if not df_meteo.empty and 'timestamp' in df_meteo.columns:
    fig_temp = px.line(df_meteo, x='timestamp', y='temperature', title="Température et Ressenti (°C)")
    st.plotly_chart(fig_temp, use_container_width=True)
else:
    st.info("Les données historiques se lissent progressivement au fil des enregistrements.")
