import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuration de la page
st.set_page_config(
    page_title="Météo Habère-Poche (900m)",
    page_icon="⛅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Style CSS personnalisé pour l'ambiance montagne
st.markdown("""
    <style>
    .main {
        background-color: #f8fafc;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# Simulation / Chargement des données (à adapter selon ta source réelle Ecowitt/WeeWX/Cumulus MX)
@st.cache_data(ttl=300)
def charger_donnees_meteo():
    # Simulation d'un timestamp actuel
    current_timestamp = datetime.now()

    # Données actuelles simulées
    temperature_actuelle = 14.5
    humidite_actuelle = 78
    pression_actuelle = 1016.2
    vent_moyen = 12.4
    rafale_vent = 22.0
    pluie_jour = 2.4

    tendance_libelle = "À la hausse ↗"
    indice_confiance = "Élevé (85%)"
    point_rosee = 10.5
    etp_val = 2.1
    risque_gel = "Aucun risque de gel en journée. Vigilance matinale en fond de vallée."
    prevision_texte = "Éclaircies durables l'après-midi, se couvrant en fin de soirée avec un risque d'averses isolées sur les reliefs."

    # Génération d'un historique simulé (24h) pour les graphiques
    dates = [current_timestamp - timedelta(hours=i) for i in range(24, 0, -1)]
    df_plot = pd.DataFrame({
        "timestamp": dates,
        "temperature": [10.2 + i*0.2 + np.sin(i/3)*2 for i in range(24)],
        "humidite": [85 - i*0.3 for i in range(24)],
        "pression": [1014 + np.cos(i/4)*3 for i in range(24)],
        "vent": [8 + np.sin(i/2)*5 for i in range(24)],
        "rafale": [15 + np.sin(i/2)*8 for i in range(24)]
    })

    return current_timestamp, temperature_actuelle, humidite_actuelle, pression_actuelle, vent_moyen, rafale_vent, pluie_jour, tendance_libelle, indice_confiance, point_rosee, etp_val, risque_gel, prevision_texte, df_plot

def obtenir_normales_saison(mois):
    normales = {
        1: {"t_min": -3.0, "t_max": 3.0, "desc": "Hivernal, neigeux"},
        2: {"t_min": -2.5, "t_max": 4.5, "desc": "Frais, gelées fréquentes"},
        3: {"t_min": 0.0, "t_max": 9.0, "desc": "Transition, giboulées"},
        4: {"t_min": 3.0, "t_max": 13.0, "desc": "Printanier variable"},
        5: {"t_min": 7.0, "t_max": 18.0, "desc": "Doux, averses orageuses"},
        6: {"t_min": 10.0, "t_max": 22.0, "desc": "Chaud, belles journées"},
        7: {"t_min": 12.0, "t_max": 25.0, "desc": "Estival, ensoleillé"},
        8: {"t_min": 11.5, "t_max": 24.0, "desc": "Estival, orages possibles"},
        9: {"t_min": 8.0, "t_max": 19.0, "desc": "Arrière-saison agréable"},
        10: {"t_min": 4.0, "t_max": 13.0, "desc": "Frais, brumes matinales"},
        11: {"t_min": 0.0, "t_max": 7.0, "desc": "Humide, premiers flocons"},
        12: {"t_min": -2.0, "t_max": 4.0, "desc": "Hivernal, froid"}
    }
    return normales.get(mois, {"t_min": 5.0, "t_max": 15.0, "desc": "Normal"})

def connecter_feuille_journal():
    # Simulation de la connexion Google Sheets (à remplacer par gspread / st.connection)
    return None

# Chargement des données
(current_timestamp, temperature_actuelle, humidite_actuelle, pression_actuelle,
 vent_moyen, rafale_vent, pluie_jour, tendance_libelle, indice_confiance,
 point_rosee, etp_val, risque_gel, prevision_texte, df_plot) = charger_donnees_meteo()

# En-tête principal
st.title("🌲 Météo Habère-Poche (Valle Verte - 900m)")
st.markdown(f"*Dernière mise à jour des données : {current_timestamp.strftime('%d/%m/%Y à %H:%M')}*")

# Navigation par onglets
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🏠 Vue Générale",
    "🌡️ Température",
    "💧 Humidité",
    "⏱️ Pression",
    "💨 Vent",
    "💡 Analyse & Prévisions",
    "📓 Journal de Bord"
])

with tab1:
    st.subheader("Conditions en direct")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Température", f"{temperature_actuelle} °C", "1.2 °C")
    col2.metric("Humidité", f"{humidite_actuelle} %", "-2 %")
    col3.metric("Pression", f"{pression_actuelle} hPa", "+1.5 hPa")
    col4.metric("Pluie du jour", f"{pluie_jour} mm")

    st.markdown("---")
    st.subheader("Aperçu rapide des tendances (24h)")

    # Graphique combiné rapide sur la vue générale
    fig_overview = px.line(df_plot, x="timestamp", y=["temperature", "vent"], title="Évolution combinée (Température & Vent)")
    st.plotly_chart(fig_overview, use_container_width=True)

with tab2:
    st.subheader("Suivi détaillé des Températures")
    if not df_plot.empty:
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(
            x=df_plot["timestamp"], y=df_plot["temperature"],
            mode="lines", name="Température (°C)",
            line=dict(shape="spline", color="#ef4444", width=2),
            connectgaps=True
        ))
        fig_temp.update_layout(
            title="Température extérieure",
            xaxis_title="", yaxis_title="°C",
            height=350, hovermode="x unified", template="plotly_white"
        )
        st.plotly_chart(fig_temp, use_container_width=True)
    else:
        st.info("Aucune donnée disponible.")

with tab3:
    st.subheader("Suivi de l'Humidité relative")
    if not df_plot.empty:
        fig_hum = go.Figure()
        fig_hum.add_trace(go.Scatter(
            x=df_plot["timestamp"], y=df_plot["humidite"],
            mode="lines", name="Humidité (%)",
            line=dict(shape="spline", color="#3b82f6", width=2),
            connectgaps=True
        ))
        fig_hum.update_layout(
            title="Humidité (%)",
            xaxis_title="", yaxis_title="%",
            height=350, hovermode="x unified", template="plotly_white"
        )
        st.plotly_chart(fig_hum, use_container_width=True)
    else:
        st.info("Aucune donnée disponible.")

with tab4:
    st.subheader("Pression Atmosphérique")
    if not df_plot.empty:
        p_min = float(df_plot["pression"].min()) - 5
        p_max = float(df_plot["pression"].max()) + 5

        fig_press = go.Figure()
        fig_press.add_trace(go.Scatter(
            x=df_plot["timestamp"], y=df_plot["pression"],
            mode="lines", name="Pression (hPa)",
            line=dict(shape="spline", color="#8b5cf6", width=2),
            connectgaps=True
        ))
        fig_press.update_layout(
            title="Pression atmosphérique (hPa)",
            xaxis_title="",
            yaxis_title="hPa",
            yaxis=dict(range=[p_min, p_max]),
            height=280,
            hovermode="x unified",
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig_press, use_container_width=True)
    else:
        st.info("Aucune donnée disponible.")

with tab5:
    st.subheader("Vent et Rafales")
    if not df_plot.empty:
        fig_wind = go.Figure()
        fig_wind.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["vent"],
                mode="lines",
                name="Vent moyen (km/h)",
                line=dict(shape="spline", color="#f59e0b", width=1.5),
                connectgaps=True,
            )
        )
        if "rafale" in df_plot.columns:
            fig_wind.add_trace(
                go.Scatter(
                    x=df_plot["timestamp"],
                    y=pd.to_numeric(df_plot["rafale"], errors="coerce"),
                    mode="lines",
                    name="Rafales (km/h)",
                    line=dict(shape="spline", color="#ef4444", width=1, dash="dot"),
                    connectgaps=True,
                )
            )
        fig_wind.update_layout(
            title="Vent et Rafales (km/h)",
            xaxis_title="",
            yaxis_title="km/h",
            height=280,
            hovermode="x unified",
            template="plotly_white",
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig_wind, use_container_width=True)
    else:
        st.info("Aucune donnée historique disponible pour l'instant.")

with tab6:
    st.subheader("💡 Analyse & Prévisions Barométriques")

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown(f"**Tendance 3h :** {tendance_libelle}")
            st.markdown(f"**Indice de confiance :** {indice_confiance}")
            st.markdown(f"**Point de rosée :** {point_rosee} °C")
            st.markdown(f"**Évapotranspiration (ETP) :** {etp_val} mm/j")

    with col_b:
        with st.container(border=True):
            st.markdown(f"**Analyse / Risques :** {risque_gel}")
            st.markdown("### 🎯 Prévision locale")
            st.info(prevision_texte)

    st.markdown("---")
    st.subheader("📊 Normales Saisonnières (Habère-Poche - 900m)")
    mois_actuel = current_timestamp.month
    norm = obtenir_normales_saison(mois_actuel)

    cn1, cn2, cn3 = st.columns(3)
    cn1.metric("T° Min Normale", f"{norm['t_min']} °C")
    cn2.metric("T° Max Normale", f"{norm['t_max']} °C")
    cn3.metric("Ambiance du mois", norm["desc"])

with tab7:
    st.subheader("📓 Journal de Bord & Observations Locales")

    sheet_j = connecter_feuille_journal()

    with st.form("form_journal"):
        auteur = st.text_input("Auteur", value="Rémi")
        observation = st.text_area("Observation (jardin, faune, météo remarquable...)")
        submit_obs = st.form_submit_button("Ajouter au Journal")

        if submit_obs and observation:
            if sheet_j is not None:
                try:
                    date_jour = current_timestamp.strftime("%Y-%m-%d %H:%M")
                    sheet_j.append_row([date_jour, auteur, observation])
                    st.success("Observation enregistrée avec succès dans le Google Sheet !")
                except Exception as e:
                    st.error(f"Erreur lors de l'enregistrement : {e}")
            else:
                st.info("Mode simulation : l'écriture directe Google Sheets nécessite la configuration des secrets Streamlit.")

    st.markdown("### 📜 Historique des notes")
    if sheet_j is not None:
        try:
            data_j = sheet_j.get_all_records()
            if data_j:
                df_j = pd.DataFrame(data_j)
                st.dataframe(df_j, use_container_width=True)
            else:
                st.info("Aucune observation enregistrée pour le moment.")
        except Exception:
            st.info("Lecture du journal en cours...")
    else:
        st.warning("Feuille de journal non connectée (utilisez vos identifiants gspread pour l'activer).")
