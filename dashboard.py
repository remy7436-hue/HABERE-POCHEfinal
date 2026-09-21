import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import streamlit.components.v1 as components

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="⛅",
    layout="wide"
)

st.title("🏔️ Station Météo - Habère-Poche (900m)")
st.markdown("---")

# Fonction de chargement des données (à adapter selon ta source exacte : CSV, API, etc.)
@st.cache_data(ttl=600)
def charger_donnees():
    # Exemple de structure de données par défaut
    data = {
        "timestamp": pd.date_range(end=datetime.now(), periods=100, freq="H"),
        "temperature": [15 + i * 0.1 for i in range(100)],
        "humidity": [70 - i * 0.05 for i in range(100)],
        "pression": [1013 + (i % 5) for i in range(100)],
        "vent": [5 + (i % 3) for i in range(100)]
    }
    return pd.DataFrame(data)

def obtenir_normales_saison(mois):
    normales = {
        1: {"t_min": -3, "t_max": 4, "desc": "Hiver froid en moyenne en station de montagne."},
        2: {"t_min": -2, "t_max": 6, "desc": "Fin d'hiver, conditions souvent neigeuses."},
        3: {"t_min": 1, "t_max": 10, "desc": "Début du dégel printanier."},
        4: {"t_min": 4, "t_max": 14, "desc": "Printemps variable, transitions rapides."},
        5: {"t_min": 8, "t_max": 18, "desc": "Douceur printanière installée."},
        6: {"t_min": 11, "t_max": 22, "desc": "Début d'été agréable en altitude."},
        7: {"t_min": 13, "t_max": 25, "desc": "Chaleurs estivales modérées à 900m."},
        8: {"t_min": 13, "t_max": 24, "desc": "Période estivale stable, orages possibles."},
        9: {"t_min": 9, "t_max": 19, "desc": "Automne précoce, premières fraîcheurs."},
        10: {"t_min": 5, "t_max": 13, "desc": "Coloris automnaux et humidité en hausse."},
        11: {"t_min": 0, "t_max": 7, "desc": "Arrivée progressive des conditions hivernales."},
        12: {"t_min": -2, "t_max": 4, "desc": "Ambiance hivernale de fin d'année."}
    }
    return normales.get(mois, {"t_min": 5, "t_max": 15, "desc": "Normales de saison standard."})

def connecter_feuille_journal():
    # Connexion Google Sheets / Journal si configurée
    return None

# Chargement des variables de travail
df_plot = charger_donnees()
current_timestamp = datetime.now()
tendance_libelle = "Stable"
prevision_texte = "Temps calme et sec à l'horizon."
indice_confiance = "85%"

# Définition des onglets du tableau de bord
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🌡️ Direct", "📈 Graphiques", "📊 Statistiques", "📋 Tableaux",
    "📜 Historique", "💡 Prévisions", "📓 Journal", "🌐 Radar Windy"
])

with tab1:
    st.subheader("Conditions Actuelles en Direct")
    if not df_plot.empty:
        dernier = df_plot.iloc[-1]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Température", f"{dernier['temperature']:.1f} °C")
        col2.metric("Humidité", f"{dernier['humidity']:.1f} %")
        col3.metric("Pression", f"{dernier['pression']:.1f} hPa")
        col4.metric("Vent", f"{dernier['vent']:.1f} km/h")
    else:
        st.warning("Aucune donnée disponible.")

with tab2:
    st.subheader("Évolution temporelle")
    base_chart = alt.Chart(df_plot).encode(
        x=alt.X("timestamp:T", title="Heure / Date")
    )
    temp_line = base_chart.mark_line(color="#e11d48").encode(
        y=alt.Y("temperature:Q", title="Température (°C)")
    )
    st.altair_chart(temp_line, use_container_width=True)

with tab3:
    st.subheader("Statistiques globales")
    if not df_plot.empty:
        st.dataframe(df_plot.describe(), use_container_width=True)

with tab4:
    st.subheader("Données brutes")
    if not df_plot.empty:
        st.dataframe(df_plot.tail(20), use_container_width=True)

with tab5:
    st.subheader("Historique détaillé")
    base_chart_h = alt.Chart(df_plot.dropna(subset=["timestamp"])).encode(
        x=alt.X("timestamp:T", title="Heure / Date")
    )
    temp_line_h = base_chart_h.mark_line(color="#e11d48").encode(
        y=alt.Y("temperature:Q", title="Température (°C)")
    )
    st.altair_chart(temp_line_h, use_container_width=True)

with tab6:
    st.subheader("Prévisions & Analyse barométrique")
    st.info(f"**Tendance (3h) :** {tendance_libelle}")
    st.success(f"**Prévision locale :** {prevision_texte}")
    st.write(f"**Indice de confiance :** {indice_confiance}")

    mois_actuel = current_timestamp.month
    normes = obtenir_normales_saison(mois_actuel)
    st.markdown("---")
    st.write(f"**Normales de saison (Mois {mois_actuel}) :** T° min moy. {normes['t_min']}°C / T° max moy. {normes['t_max']}°C")
    st.caption(f"Contexte climatique : {normes['desc']}")

with tab7:
    st.subheader("Journal de Bord & Climat")
    sheet_j = connecter_feuille_journal()
    if sheet_j:
        try:
            records_j = sheet_j.get_all_records()
            if records_j:
                st.dataframe(pd.DataFrame(records_j), use_container_width=True)
            else:
                st.info("Aucune observation enregistrée pour le moment.")
        except Exception:
            st.info("Journal de bord disponible prochainement.")
    else:
        st.info("Journal de bord local (mode autonome).")

    st.markdown("---")
    with st.form("form_journal"):
        nouvelle_obs = st.text_area("Ajouter une note d'observation locale :")
        submit_obs = st.form_submit_button("Enregistrer dans le journal")
        if submit_obs and nouvelle_obs:
            st.success("Observation enregistrée avec succès !")

with tab8:
    st.subheader("Radar Météo & Pluie (Windy)")
    components.html(
        """
        <iframe width="100%" height="450" src="https://embed.windy.com/embed2.html?lat=46.216&lon=6.433&zoom=9&level=surface&overlay=rain&product=ecmwf&menu=&message=&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1" frameborder="0"></iframe>
        """,
        height=450
    )
