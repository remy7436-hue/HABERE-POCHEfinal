import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Station Météo - Habère-Poche",
    page_icon="⛅",
    layout="wide"
)

st.title("Station Météo – Habère-Poche (900m)")
st.markdown("Tableau de bord météorologique et suivi en temps réel du microclimat.")

# --- CHARGEMENT DES DONNÉES DEPUIS LE GOOGLE SHEET ---
@st.cache_data(ttl=300)
def load_meteo_data():
    # Remplacer par l'URL d'export CSV de votre Google Sheet ou lecture gspread
    sheet_url = "https://docs.google.com/spreadsheets/d/your_sheet_id/export?format=csv"
    try:
        df = pd.read_csv(sheet_url)
    except Exception:
        # Structure de secours si la liaison est en attente
        df = pd.DataFrame(columns=[
            'timestamp', 'temperature', 'ressenti', 'humidite',
            'pression', 'vent', 'rafale', 'direction', 'pluie'
        ])

    # Nettoyage automatique des valeurs aberrantes de démarrage
    if 'temperature' in df.columns:
        df = df[df['temperature'] > -50]

    return df

df_meteo = load_meteo_data()

# --- CRÉATION DES ONGLETS DE NAVIGATION ---
tab_reel, tab_rose, tab_pluie, tab_nuage, tab_histo, tab_prev = st.tabs([
    "⏱️ Temps Réel & Extrêmes",
    "🧭 Rose des Vents",
    "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux",
    "📈 Historique et tendances",
    "🔮 Prévisions et analyses"
])

# ==========================================
# 1. TEMPS RÉEL & EXTRÊMES
# ==========================================
with tab_reel:
    st.subheader("Conditions Actuelles (Flux Ecowitt Cloud)")

    if not df_meteo.empty:
        dernier = df_meteo.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("Température", f"{dernier.get('temperature', 0):.1f} °C")
        col2.metric("Humidité", f"{dernier.get('humidite', 0):.1f} %")
        col3.metric("Pression relative", f"{dernier.get('pression', 0):.1f} hPa")

        col4, col5, col6 = st.columns(3)
        col4.metric("Ressenti", f"{dernier.get('ressenti', 0):.1f} °C")
        col5.metric("Vent moyen", f"{dernier.get('vent', 0):.1f} km/h")
        col6.metric("Rafale", f"{dernier.get('rafale', 0):.1f} km/h")
    else:
        st.info("En attente des données de la station...")

    st.markdown("### Extrêmes du jour")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    col_ex1.metric("Max Chaleur (Tx)", "17,0 °C")
    col_ex2.metric("Min Fraîcheur (Tn)", "16,3 °C")
    col_ex3.metric("Vent max", "49,0 km/h")

# ==========================================
# 2. ROSE DES VENTS (OPTIMISÉE)
# ==========================================
with tab_rose:
    st.subheader("Analyse de la Rose des Vents (Fiche Google)")

    def plot_enhanced_wind_rose(df):
        if df.empty or 'vent' not in df.columns or 'direction' not in df.columns:
            return px.scatter(title="Données de vent non disponibles")

        # Définition de paliers de vitesse plus précis pour la colorbar (en km/h)
        bins = [0, 5, 10, 15, 20, 30, 40, 50, 100]
        labels = ['< 5', '5-10', '10-15', '15-20', '20-30', '30-40', '40-50', '> 50']

        df['vent_tranche'] = pd.cut(df['vent'], bins=bins, labels=labels, right=False)

        # Calcul des fréquences par direction et tranche de vitesse
        wind_freq = df.groupby(['direction', 'vent_tranche'], observed=False).size().reset_index(name='count')

        # Calcul du pourcentage de vents calmes (< 1 km/h)
        calm_count = len(df[df['vent'] < 1])
        total_count = len(df)
        calm_percentage = (calm_count / total_count * 100) if total_count > 0 else 0

        # Tracé polaire interactif avec Plotly
        fig = px.bar_polar(
            wind_freq,
            r='count',
            theta='direction',
            color='vent_tranche',
            color_discrete_sequence=px.colors.sequential.Blues,
            template="plotly_white"
        )

        fig.update_layout(
            title=f"Distribution des Directions et Vitesses (Vents calmes : {calm_percentage:.1f}%)",
            polar=dict(
                radialaxis=dict(showticklabels=True, ticks=''),
                angularaxis=dict(direction="clockwise", rotation=90)
            )
        )
        return fig

    st.plotly_chart(plot_enhanced_wind_rose(df_meteo), use_container_width=True)

# ==========================================
# 3. PLUVIOMÉTRIE
# ==========================================
with tab_pluie:
    st.subheader("Suivi Pluviométrique")
    st.markdown("Cumuls de précipitations journaliers, hebdomadaires et mensuels à 900m.")
    if not df_meteo.empty and 'pluie' in df_meteo.columns:
        fig_pluie = px.bar(df_meteo, x='timestamp', y='pluie', title="Précipitations (mm)")
        st.plotly_chart(fig_pluie, use_container_width=True)
    else:
        st.info("Aucune précipitation enregistrée sur la période récente.")

# ==========================================
# 4. PLANCHER NUAGEUX
# ==========================================
with tab_nuage:
    st.subheader("Estimation du Plancher Nuageux")
    st.markdown("Calcul dynamique basé sur l'écart entre la température et le point de rosée.")
    st.info("Le plancher nuageux s'estime généralement autour de 120 à 150 mètres par tranche de 1°C d'écart thermo-hygrométrique.")

# ==========================================
# 5. HISTORIQUE ET TENDANCES LISSÉES
# ==========================================
with tab_histo:
    st.subheader("Historique & Tendances Lissées")
    if not df_meteo.empty and 'timestamp' in df_meteo.columns:
        fig_temp = px.line(df_meteo, x='timestamp', y=['temperature', 'ressenti'], title="Températures et Ressenti (°C)")
        st.plotly_chart(fig_temp, use_container_width=True)

        fig_hum = px.line(df_meteo, x='timestamp', y='humidite', title="Humidité relative (%)")
        st.plotly_chart(fig_hum, use_container_width=True)
    else:
        st.info("Les courbes historiques se lissent automatiquement au fil des enregistrements continus.")

# ==========================================
# 6. PRÉVISIONS ET ANALYSES
# ==========================================
with tab_prev:
    st.subheader("Prévisions et analyses du microclimat")
    st.markdown("- Analyse locale des flux de Bise et de Foehn en Vallée Verte.")
    st.markdown("- Tendances barométriques pour l'anticipation des entrées de 900m.")
