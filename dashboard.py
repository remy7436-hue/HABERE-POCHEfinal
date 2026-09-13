import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import base64

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="🏔️",
    layout="wide"
)

# --- TITRE ET INTRODUCTION ---
st.title("🏔️ Station Météo d'Habère-Poche (900m)")
st.markdown("Suivi météorologique en temps réel, analyses et modélisations de moyenne montagne.")

# --- SIMULATION OU CHARGEMENT DES DONNÉES MÉTÉO ---
# (Remplace cette section par tes flux réels Ecowitt / WeeWX / Cumulus MX habituels)
altitude_village = 900
temp_actuelle = 18.5
point_rosee = 8.5

# Calculs de base pour le plancher nuageux (Formule de Slocum / approximation standard)
# Élévation de la base des cumulus par rapport au sol en mètres : (Temp - Point de rosée) * 125
base_cumulus_sol = int((temp_actuelle - point_rosee) * 125)
altitude_cumulus_mer = altitude_village + base_cumulus_sol

# --- ORGANISATION EN ONGLETS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Conditions Actuelles",
    "📈 Historique & Tendances",
    "🌱 Jardin & Observations",
    "☁️ Plancher Nuageux & Paysage"
])

# --- ONGLET 1 : Conditions Actuelles ---
with tab1:
    st.subheader("🌡️ Mesures instantanées")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Température", f"{temp_actuelle} °C", "+0.4°C /h")
    col2.metric("Point de rosée", f"{point_rosee} °C")
    col3.metric("Humidité", "58 %")
    col4.metric("Pression", "1016.2 hPa", "Stable")

    st.info("💡 Capteurs Ecowitt WS69 opérationnels connectés via la passerelle GW3000.")

# --- ONGLET 2 : Historique & Tendances ---
with tab2:
    st.subheader("📈 Évolution journalière")
    # Exemple de graphique simple d'historique
    df_temp = pd.DataFrame({
        "Heure": ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
        "Température": [11.2, 10.5, 13.1, 19.8, 18.5, 15.0]
    })
    st.line_chart(df_temp.set_index("Heure"))

# --- ONGLET 3 : Jardin & Observations ---
with tab3:
    st.subheader("🌿 Suivi du Potager et de la Végétation à 900m")
    col_j1, col_j2 = st.columns(2)
    with col_j1:
        st.markdown("""
        * **Paillage foin** : Actif sur les pommes de terre et courges.
        * **Récoltes en cours** : Tomates cerises, haricots verts, piments.
        """)
    with col_j2:
        st.markdown("""
        * **Flore sauvage** : Séchage en cours de l'achillée mille-feuille et du millepertuis.
        * **Faune locale** : Passages réguliers de chevreuils suivis par piège photographique.
        """)

# --- ONGLET 4 : Plancher Nuageux & Paysage ---
with tab4:
    st.subheader("🏔️ Visualisation du Plancher Nuageux sur les Crêtes")

    if base_cumulus_sol is not None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Altitude du village", f"{altitude_village} m")
        c2.metric("Hauteur base des nuages / sol", f"+{base_cumulus_sol} m")
        c3.metric("Altitude absolue du nuage", f"{altitude_cumulus_mer} m")

        # Fichier image de la crête locale
        image_path = "PXL_20260913_173725056.MP_2.jpg"

        fig_pano = go.Figure()

        if os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                encoded_img = base64.b64encode(img_file.read()).decode()

            # Intégration de la vraie photo en arrière-plan du graphique Plotly
            fig_pano.add_layout_image(
                dict(
                    source=f"data:image/jpeg;base64,{encoded_img}",
                    xref="x", yref="y",
                    x=0, y=2400,          # Calage de l'échelle verticale de la photo
                    sizex=10, sizey=2400,
                    sizing="stretch",
                    opacity=0.92,
                    layer="below"
                )
            )

        # Couche nuageuse semi-transparente avec effet de fondu vaporeux calculée en temps réel
        y_nuage_base = altitude_cumulus_mer
        y_nuage_haut = altitude_cumulus_mer + 700

        fig_pano.add_trace(go.Scatter(
            x=[0, 5, 10, 10, 5, 0],
            y=[y_nuage_base, y_nuage_base, y_nuage_base, y_nuage_haut, y_nuage_haut, y_nuage_haut],
            fill="toself",
            fillcolor="rgba(255, 255, 255, 0.45)",  # Effet de fondu laiteux sur les cumulus
            line=dict(color="rgba(255, 255, 255, 0.1)", width=1),
            hoverinfo="skip",
            name="Strate nuageuse"
        ))

        # Marqueur interactif de la base exacte des cumulus
        fig_pano.add_trace(go.Scatter(
            x=[5],
            y=[y_nuage_base],
            mode="markers+text",
            marker=dict(size=18, color="#ffffff", line=dict(color="#1b4f72", width=3), symbol="circle"),
            text=[f"☁️ Base des Cumulus : {y_nuage_base} m"],
            textposition="top center",
            textfont=dict(size=13, color="#ffffff", family="Arial Black")
        ))

        # Cadrage et mise en page de la scène
        fig_pano.update_layout(
            title="Immersion — Strate nuageuse en temps réel sur la crête",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0, 10]),
            yaxis=dict(title="Altitude (mètres)", range=[0, 2400], showgrid=True, gridcolor="rgba(255,255,255,0.2)"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=550,
            showlegend=False
        )

        st.plotly_chart(fig_pano, use_container_width=True)
        st.caption("📷 Superposition dynamique de la base des cumulus calculée directement par-dessus la photo de la ligne de crête de la Vallée Verte.")
    else:
        st.info("⚠️ Données météo requises pour afficher l'immersion paysagère.")
