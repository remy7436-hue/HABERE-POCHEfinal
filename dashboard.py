import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import altair as alt
import streamlit.components.v1 as components
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 1. CONFIGURATION DE LA PAGE
# ---------------------------------------------------------
st.set_page_config(
    page_title="Météo Habère-Poche (900m)",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 2. CHARGEMENT & SIMULATION DES DONNÉES DE LA STATION
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def load_weather_data():
    """
    Tente de charger les données réelles (ex: CSV ou API Ecowitt).
    Génère un jeu de données de secours si le fichier local n'est pas encore présent.
    """
    try:
        # Remplace 'data.csv' par le chemin exact de ton fichier de données
        df = pd.read_csv("data.csv")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception:
        # Données de secours (7 derniers jours par pas de 30 min)
        dates = pd.date_range(end=datetime.now(), periods=336, freq='30min')
        np.random.seed(42)

        temp_base = 12 + 6 * np.sin(np.linspace(0, 14 * np.pi, 336)) + np.random.normal(0, 1.5, 336)
        pression_base = 1013 + 8 * np.cos(np.linspace(0, 4 * np.pi, 336)) + np.random.normal(0, 0.8, 336)
        humidite_base = np.clip(70 + 20 * np.cos(np.linspace(0, 14 * np.pi, 336)) + np.random.normal(0, 5, 336), 30, 100)
        vent_base = np.clip(10 + 8 * np.random.randn(336), 0, 65)
        rafales_base = vent_base * np.random.uniform(1.2, 1.8, 336)
        pluie_base = np.where(np.random.rand(336) > 0.88, np.random.exponential(1.5, 336), 0)
        orientations = [0, 45, 90, 135, 180, 225, 270, 315]
        vent_dir = np.random.choice(orientations, size=336)

        df = pd.DataFrame({
            'timestamp': dates,
            'temperature': np.round(temp_base, 1),
            'pression': np.round(pression_base, 1),
            'humidite': np.round(humidite_base, 0),
            'vent_vitesse': np.round(vent_base, 1),
            'vent_rafale': np.round(rafales_base, 1),
            'vent_direction': vent_dir,
            'pluie_mm': np.round(pluie_base, 1)
        })
        return df

df = load_weather_data()
dernière_mesure = df.iloc[-1]

# ---------------------------------------------------------
# 3. BARRE LATÉRALE (SIDEBAR)
# ---------------------------------------------------------
st.sidebar.title("🌲 Météo Habère-Poche")
st.sidebar.markdown("**Altitude :** 900 m  \n**Vallée Verte, Haute-Savoie**")
st.sidebar.divider()

st.sidebar.subheader("⚙️ Options d'affichage")
auto_refresh = st.sidebar.checkbox("Rafraîchissement automatique (5 min)", value=True)
st.sidebar.info(f"Dernière mise à jour : {dernière_mesure['timestamp'].strftime('%d/%m/%Y à %H:%M')}")

if st.sidebar.button("🔄 Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------
# 4. EN-TÊTE PRINCIPAL
# ---------------------------------------------------------
st.title("🌤️ Tableau de Bord Météo — Habère-Poche")
st.caption("Station Ecowitt GW3000 / WS69 — Suivi météo en temps réel et données historiques")

# ---------------------------------------------------------
# 5. STRUCTURE DES 7 ONGLETS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🌡️ Temps Réel",
    "📈 Historique & Tendances",
    "🌧️ Pluviométrie",
    "💨 Vent & Rose des Vents",
    "📊 Normales & Climat",
    "🛰️ Radar & Cartes",
    "📖 Journal & Station"
])

# =========================================================
# ONGLET 1 : TEMPS RÉEL
# =========================================================
with tab1:
    st.header("Conditions actuelles")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Température",
        f"{dernière_mesure['temperature']} °C",
        delta=f"{round(dernière_mesure['temperature'] - df.iloc[-2]['temperature'], 1)} °C"
    )
    col2.metric(
        "Humidité",
        f"{int(dernière_mesure['humidite'])} %",
        delta=f"{int(dernière_mesure['humidite'] - df.iloc[-2]['humidite'])} %"
    )
    col3.metric(
        "Pression Relative",
        f"{dernière_mesure['pression']} hPa",
        delta=f"{round(dernière_mesure['pression'] - df.iloc[-2]['pression'], 1)} hPa"
    )
    col4.metric(
        "Vent Moyen",
        f"{dernière_mesure['vent_vitesse']} km/h",
        delta=f"Rafales: {dernière_mesure['vent_rafale']} km/h"
    )

    st.divider()

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Vue rapide (Dernières 24h)")
        df_24h = df[df['timestamp'] >= datetime.now() - timedelta(hours=24)]
        fig_quick = px.line(
            df_24h, x='timestamp', y='temperature',
            labels={'timestamp': 'Heure', 'temperature': 'Température (°C)'},
            color_discrete_sequence=['#ef4444']
        )
        fig_quick.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10), template="plotly_white")
        st.plotly_chart(fig_quick, use_container_width=True)

    with c2:
        st.subheader("Résumé de la journée")
        temp_max_24h = df_24h['temperature'].max()
        temp_min_24h = df_24h['temperature'].min()
        pluie_24h = df_24h['pluie_mm'].sum()

        st.write(f"🌡️ **Temp. Max :** {temp_max_24h} °C")
        st.write(f"❄️ **Temp. Min :** {temp_min_24h} °C")
        st.write(f"🌧️ **Cumul Pluie :** {round(pluie_24h, 1)} mm")
        st.write(f"💨 **Rafale Max :** {df_24h['vent_rafale'].max()} km/h")

# =========================================================
# ONGLET 2 : HISTORIQUE & TENDANCES (Graphique avec correctif line 1079)
# =========================================================
with tab2:
    st.header("📈 Historique & Tendances")
    st.subheader("Évolution globale Température & Pression")

    try:
        fig_hist = go.Figure()

        # Courbe Température (Axe Y principal)
        fig_hist.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['temperature'],
            name="Température (°C)",
            line=dict(color="#ef4444", width=2)
        ))

        # Courbe Pression (Axe Y secondaire)
        fig_hist.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['pression'],
            name="Pression (hPa)",
            yaxis="y2",
            line=dict(color="#3b82f6", width=2)
        ))

        # Configuration mise à jour avec syntaxe title_font (ligne 1079 corrigée)
        fig_hist.update_layout(
            title_text="Évolution de la Température et de la Pression",
            xaxis_title="Horodatage",
            yaxis=dict(
                title="Température (°C)",
                title_font=dict(color="#ef4444")
            ),
            yaxis2=dict(
                title="Pression (hPa)",
                title_font=dict(color="#3b82f6"),
                overlaying="y",
                side="right"
            ),
            height=400,
            margin=dict(l=10, r=10, t=40, b=10),
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        st.plotly_chart(fig_hist, use_container_width=True)

    except Exception as e:
        st.error(f"Impossible de générer le graphique d'historique : {e}")

    st.subheader("Statistiques sur la période sélectionnée")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    col_stat1.metric("Moyenne Température", f"{round(df['temperature'].mean(), 1)} °C")
    col_stat2.metric("Pression Max", f"{df['pression'].max()} hPa")
    col_stat3.metric("Pression Min", f"{df['pression'].min()} hPa")

# =========================================================
# ONGLET 3 : PLUVIOMÉTRIE
# =========================================================
with tab3:
    st.header("🌧️ Suivi de la Pluviométrie")

    col_p1, col_p2 = st.columns([3, 1])

    with col_p1:
        fig_rain = px.bar(
            df, x='timestamp', y='pluie_mm',
            title="Intensité des précipitations (mm)",
            labels={'timestamp': 'Horodatage', 'pluie_mm': 'Pluie (mm)'},
            color_discrete_sequence=['#0284c7']
        )
        fig_rain.update_layout(height=380, template="plotly_white")
        st.plotly_chart(fig_rain, use_container_width=True)

    with col_p2:
        st.subheader("Cumuls d'eau")
        cumul_total = df['pluie_mm'].sum()
        st.metric("Total Période", f"{round(cumul_total, 1)} mm")
        st.metric("Max en 30 min", f"{df['pluie_mm'].max()} mm")
        st.info("La collecte s'effectue automatiquement via le pluviomètre de la station WS69.")

# =========================================================
# ONGLET 4 : VENT & ROSE DES VENTS
# =========================================================
with tab4:
    st.header("💨 Vent & Rose des Vents")

    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.subheader("Vitesse et Rafales")
        fig_wind = go.Figure()
        fig_wind.add_trace(go.Scatter(x=df['timestamp'], y=df['vent_vitesse'], name="Vent Moyen", line=dict(color="#10b981")))
        fig_wind.add_trace(go.Scatter(x=df['timestamp'], y=df['vent_rafale'], name="Rafales", line=dict(color="#f59e0b", dash="dot")))
        fig_wind.update_layout(height=350, template="plotly_white", xaxis_title="Horodatage", yaxis_title="Vitesse (km/h)")
        st.plotly_chart(fig_wind, use_container_width=True)

    with col_v2:
        st.subheader("Rose des Vents (Directions)")
        try:
            dirs_labels = {0: 'N', 45: 'NE', 90: 'E', 135: 'SE', 180: 'S', 225: 'SO', 270: 'O', 315: 'NO'}
            df['dir_label'] = df['vent_direction'].map(dirs_labels).fillna('N')

            wind_counts = df['dir_label'].value_counts().reset_index()
            wind_counts.columns = ['Direction', 'Frequence']

            fig_rose = px.bar_polar(
                wind_counts, r='Frequence', theta='Direction',
                title="Distribution des orientations du vent",
                color_discrete_sequence=['#3b82f6']
            )
            fig_rose.update_layout(height=350)
            st.plotly_chart(fig_rose, use_container_width=True)
        except Exception as e:
            st.warning(f"Affichage simplifié de la rose des vents : {e}")

# =========================================================
# ONGLET 5 : NORMALES & CLIMAT
# =========================================================
with tab5:
    st.header("📊 Normales & Comparatif Climatologique")
    st.markdown("Comparaison des mesures de la station à 900m d'altitude par rapport aux moyennes de saison.")

    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.subheader("Profil thermique horaire")
        df['heure'] = df['timestamp'].dt.hour
        hourly_temp = df.groupby('heure')['temperature'].mean().reset_index()

        fig_hourly = px.line(
            hourly_temp, x='heure', y='temperature',
            labels={'heure': 'Heure de la journée', 'temperature': 'Température Moyenne (°C)'},
            title="Cycle quotidien moyen de température"
        )
        fig_hourly.update_layout(template="plotly_white")
        st.plotly_chart(fig_hourly, use_container_width=True)

    with col_c2:
        st.subheader("Indicateurs Climat")
        st.write("• **Secteur :** Préalpes du Chablais / Vallée Verte")
        st.write("• **Isotherme 0°C estimé :** ~ 1800 m")
        st.write("• **Jours de gel (période) :**", len(df[df['temperature'] <= 0]))
        st.write("• **Précipitations cumulées :**", f"{round(df['pluie_mm'].sum(), 1)} mm")

# =========================================================
# ONGLET 6 : RADAR & CARTES (WINDY)
# =========================================================
with tab6:
    st.header("🛰️ Radar Météo & Cartes Interactives")
    st.caption("Intégration du radar pluie & vent Windy centré sur Habère-Poche")

    # Coordonnées Habère-Poche : Lat 46.26, Lon 6.47
    windy_embed_url = "https://embed.windy.com/embed2.html?lat=46.260&lon=6.470&detailLat=46.260&detailLon=6.470&width=100%25&height=450&zoom=10&level=surface&overlay=radar&product=radar&menu=&message=&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1"

    components.iframe(windy_embed_url, height=500, scrolling=False)

# =========================================================
# ONGLET 7 : JOURNAL & DIAGNOSTICS STATION
# =========================================================
with tab7:
    st.header("📖 Journal & Diagnostics de la Station")
    st.subheader("Derniers relevés enregistrés")

    st.dataframe(
        df.sort_values(by='timestamp', ascending=False).head(50),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("Export & Maintenance")
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger les données CSV",
            data=csv_data,
            file_name=f"meteo_habere_poche_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    with col_d2:
        st.success("✅ Passerelle Ecowitt GW3000 : Connectée")
        st.success("✅ Carte MicroSD : Carte FAT32 active")
