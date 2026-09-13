import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sqlite3

# 1. Configuration de la page
st.set_page_config(
    page_title="Météo Habère-Poche",
    page_icon="🏔️",
    layout="wide"
)

# 2. Récupération des secrets Ecowitt
ECOWITT_API_KEY = st.secrets.get("ECOWITT_API_KEY", "")
ECOWITT_APP_KEY = st.secrets.get("ECOWITT_APP_KEY", "")
GW3000_MAC = st.secrets.get("GW3000_MAC", "")

DB_NAME = "meteo_historique.db"


# 3. Initialisation de la Base de Données SQLite
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historique (
            timestamp DATETIME PRIMARY KEY,
            heure TEXT,
            temperature REAL,
            ressenti REAL,
            humidite REAL,
            pression REAL,
            pression_abs REAL,
            vent REAL,
            rafale REAL,
            direction REAL,
            pluie REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()


def sauvegarder_mesure_db(timestamp, heure, temp, ressenti, humidite, pression, pression_abs, vent, rafale, direction, pluie):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO historique
            (timestamp, heure, temperature, ressenti, humidite, pression, pression_abs, vent, rafale, direction, pluie)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp.strftime("%Y-%m-%d %H:%M:%S"), heure, temp, ressenti, humidite, pression, pression_abs, vent, rafale, direction, pluie))
        conn.commit()
        conn.close()
    except Exception:
        pass


def charger_historique_db(limite_heures=720):
    try:
        conn = sqlite3.connect(DB_NAME)
        query = f"SELECT * FROM historique ORDER BY timestamp DESC LIMIT {limite_heures * 60}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)
            if "pluie" not in df.columns:
                df["pluie"] = 0.0
        return df
    except Exception:
        return pd.DataFrame(columns=["timestamp", "heure", "temperature", "ressenti", "humidite", "pression", "pression_abs", "vent", "rafale", "direction", "pluie"])


# 4. Fonctions utilitaires & calculs avancés
def to_float(val):
    if val is None or val == "":
        return 0.0
    try:
        clean_val = (
            str(val)
            .replace("%", "")
            .replace("°C", "")
            .replace("km/h", "")
            .replace("hPa", "")
            .replace("mm", "")
            .replace(",", ".")
            .strip()
        )
        return float(clean_val)
    except (ValueError, TypeError):
        return 0.0


def degres_vers_cardinal(deg):
    if deg is None or pd.isna(deg):
        return "N/A"
    try:
        deg = float(deg)
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
        ix = int((deg + 11.25) / 22.5)
        return dirs[ix % 16]
    except (ValueError, TypeError):
        return "N/A"


def calculer_base_cumulus(temp, humidite, altitude_station=900):
    if temp is None or humidite is None:
        return None, None
    try:
        t = float(temp)
        rh = float(humidite)
        a, b = 17.27, 237.7
        alpha = ((a * t) / (b + t)) + np.log(rh / 100.0)
        dew_point = (b * alpha) / (a - alpha)

        base_sol = (t - dew_point) * 125.0
        altitude_mer = base_sol + altitude_station
        return round(base_sol), round(altitude_mer)
    except Exception:
        return None, None


def calculer_ressenti(temp, wind_speed_kmh, humidite):
    if temp is None:
        return None, "Indisponible"

    ressenti = temp
    mode = "Standard"

    if temp <= 10.0 and wind_speed_kmh is not None and wind_speed_kmh > 4.8:
        v = wind_speed_kmh
        t = temp
        wc = 13.12 + 0.6215 * t - 11.37 * (v ** 0.16) + 0.3965 * t * (v ** 0.16)
        ressenti = round(wc, 1)
        mode = "Windchill (Vent)"
    elif temp >= 20.0 and humidite is not None:
        t = temp
        rh = humidite
        a, b = 17.27, 237.7
        alpha = ((a * t) / (b + t)) + np.log(rh / 100.0)
        dew_point = (b * alpha) / (a - alpha)
        e = 6.11 * np.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_point))))
        h = t + (5/9) * (e - 10)
        ressenti = round(h, 1)
        mode = "Humidex (Moiteur)"

    return ressenti, mode


def analyser_risques_montagne(temp, humidite, pression, vent_speed):
    """Calcule le risque de gel, l'évapotranspiration estimée et les alertes jardin."""
    if temp is None or humidite is None:
        return "Indisponible", "Indisponible", "Données insuffisantes"

    # Point de rosée
    a, b = 17.27, 237.7
    alpha = ((a * temp) / (b + temp)) + np.log(humidite / 100.0)
    dew_point = (b * alpha) / (a - alpha)

    # 1. Risque de gel
    if temp <= 2.0:
        risque_gel = "🚨 Risque de gel imminent ou avéré !"
    elif temp <= 5.0 and dew_point <= 2.0:
        risque_gel = "⚠️ Risque de gelée blanche matinale (surfaces froides)"
    else:
        risque_gel = "✅ Aucun risque de gel pour l'instant"

    # 2. Estimation simple de l'évapotranspiration (ETP journalière approximative en mm)
    # Formule simplifiée basée sur température et humidité relative
    etp = max(0.1, round(0.0023 * (temp + 17.8) * (100 - humidite)**0.5 * 5, 2))

    return risque_gel, etp, round(dew_point, 1)


def prevision_zambretti(pression_hpa, tendance_hpa_par_heure):
    if pression_hpa is None:
        return "Données barométriques insuffisantes pour la prévision."

    p = pression_hpa
    tendance = tendance_hpa_par_heure

    if tendance > 0.1:
        if p >= 1030: return "☀️ Temps beau et stable (Anticyclone fort)"
        elif p >= 1020: return "🌤️ Beau temps persistant"
        elif p >= 1010: return "⛅ Amélioration temporaire, beau temps probable"
        elif p >= 1000: return "🌦️ Instable mais tendant vers l'amélioration"
        else: return "🌧️ Forte perturbation en évacuation, amélioration en vue"
    elif tendance < -0.1:
        if p >= 1030: return "🌤️ Temps beau mais se dégradant"
        elif p >= 1020: return "⛅ Temps variable, tendance à la dégradation"
        elif p >= 1010: return "🌧️ Risque d'averses, temps pluvieux probable"
        elif p >= 1000: return "⛈️ Dégradation rapide, pluie ou orages imminents"
        else: return "🌪️ Forte tempête ou intempéries majeures en approche"
    else:
        if p >= 1025: return "☀️ Temps beau, stable et sec"
        elif p >= 1015: return "⛅ Temps correct et globalement stable"
        elif p >= 1005: return "☁️ Temps changeant, passages nuageux"
        else: return "🌧️ Temps pluvieux et maussade persistant"


def interpreter_vent_local(degres, vitesse_kmh):
    if degres is None or pd.isna(degres):
        v = vitesse_kmh if vitesse_kmh is not None else 0
        if v < 2:
            return "Calme plat / Vent variable", "💤"
        return "Direction indéterminée", "❓"

    deg = float(degres)
    v = vitesse_kmh if vitesse_kmh is not None else 0

    if v < 3:
        return "Calme (insensible)", "💤"

    if 315 <= deg <= 360 or 0 <= deg < 45:
        return "Bise / Vent de Nord : Temps généralement plus sec, assèchement, fraîcheur.", "🌬️"
    elif 45 <= deg < 135:
        return "Vent d'Est / Sud-Est : Flux continental, souvent stable ou prélude à un changement de temps.", "🌤️"
    elif 135 <= deg < 225:
        return "Vent du Sud / Sud-Ouest : Flux perturbé doux, souvent annonciateur d'une dégradation (pluie, orages en saison chaude).", "⛈️"
    elif 225 <= deg < 315:
        return "Vent d'Ouest / Nord-Ouest : Flux de traîne ou front d'occlusion, passages nuageux et averses probables.", "🌧️"

    return "Vent variable", "🍃"


# 5. Récupération des données depuis l'API Ecowitt Cloud
def fetch_ecowitt_data(app_key, api_key, mac):
    url = "https://api.ecowitt.net/api/v3/device/real_time"
    params = {
        "application_key": app_key,
        "api_key": api_key,
        "mac": mac,
        "call_by": "all",
        "temp_unitid": "1",
        "wind_speed_unitid": "7",
        "pressure_unitid": "3",
        "rain_unitid": "12"
    }
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


# Sidebar
with st.sidebar:
    st.header("⚙️ Station Météo — Cloud")
    st.write("**Altitude :** 900 m (Vallée Verte)")

    if st.button("🔄 Forcer la synchro & Actualiser"):
        st.rerun()

st.title("🏔️ Station Météo — Habère-Poche")

# Appel immédiat et synchro fraîche de l'API Ecowitt
raw_data = fetch_ecowitt_data(ECOWITT_APP_KEY, ECOWITT_API_KEY, GW3000_MAC)

if not raw_data or raw_data.get("code") != 0:
    st.error("Impossible de récupérer les données depuis les serveurs Ecowitt. Vérifie tes clés API et ton MAC dans les secrets Streamlit Cloud.")
    st.stop()

data_sensors = raw_data.get("data", {})

def get_sensor_val(sensor_group, key_name):
    group = data_sensors.get(sensor_group, {})
    val_obj = group.get(key_name, {})
    return to_float(val_obj.get("value"))

temp = get_sensor_val("outdoor", "temperature")
humidity = get_sensor_val("outdoor", "humidity")
pressure = get_sensor_val("pressure", "relative")
pressure_abs = get_sensor_val("pressure", "absolute")
wind_speed = get_sensor_val("wind", "wind_speed")
wind_gust = get_sensor_val("wind", "wind_gust")
wind_dir = get_sensor_val("wind", "wind_direction")
rain_day = get_sensor_val("rainfall", "day")

base_cumulus_sol, altitude_cumulus_mer = calculer_base_cumulus(temp, humidity, 900)
temp_ressentie, mode_ressenti = calculer_ressenti(temp, wind_speed, humidity)
risque_gel, etp_val, point_rosee = analyser_risques_montagne(temp, humidity, pressure, wind_speed)

current_time_str = datetime.now().strftime("%H:%M:%S")
current_timestamp = datetime.now()


# 6. Sauvegarde immédiate dans SQLite
if temp is not None:
    sauvegarder_mesure_db(
        current_timestamp, current_time_str, float(temp),
        float(temp_ressentie) if temp_ressentie is not None else float(temp),
        float(humidity) if humidity is not None else 0.0,
        float(pressure) if pressure is not None else 0.0,
        float(pressure_abs) if pressure_abs is not None else 0.0,
        float(wind_speed) if wind_speed is not None else 0.0,
        float(wind_gust) if wind_gust is not None else 0.0,
        float(wind_dir) if wind_dir is not None else 0.0,
        float(rain_day) if rain_day is not None else 0.0
    )

df_hist = charger_historique_db(limite_heures=720)

# Gestion des deltas persistants
delta_temp, delta_hum, delta_press = 0.0, 0.0, 0.0
if len(df_hist) >= 2:
    delta_temp = round(df_hist.iloc[-1]["temperature"] - df_hist.iloc[-2]["temperature"], 1)
    delta_hum = round(df_hist.iloc[-1]["humidite"] - df_hist.iloc[-2]["humidite"], 1)
    delta_press = round(df_hist.iloc[-1]["pression"] - df_hist.iloc[-2]["pression"], 2)


# 7. Gestion des extrêmes du jour
if "initialized" not in st.session_state:
    st.session_state.initialized = True

max_temp, min_temp, max_temp_time, min_temp_time = "--", "--", "", ""
max_wind, max_gust = 0.0, 0.0

if not df_hist.empty:
    today_str = current_timestamp.strftime("%Y-%m-%d")
    df_today = df_hist[df_hist["timestamp"].dt.strftime("%Y-%m-%d"] == today_str]
    if not df_today.empty:
        max_t_row = df_today.loc[df_today["temperature"].idxmax()]
        min_t_row = df_today.loc[df_today["temperature"].idxmin()]
        max_temp = max_t_row["temperature"]
        max_temp_time = max_t_row["heure"]
        min_temp = min_t_row["temperature"]
        min_temp_time = min_t_row["heure"]
        max_wind = df_today["vent"].max()
        max_gust = df_today["rafale"].max()

tendance_baro = 0.0
if len(df_hist) >= 2:
    tendance_baro = round(df_hist.iloc[-1]["pression"] - df_hist.iloc[0]["pression"], 2)

prevision_texte = prevision_zambretti(pressure, tendance_baro)


# 8. Structure par Onglets
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Temps Réel & Extrêmes",
    "🧭 Rose des Vents",
    "🌧️ Pluviométrie",
    "☁️ Plancher Nuageux & Paysage",
    "📈 Historique & Tendances",
    "💡 Prévisions & Analyse"
])

# --- ONGLET 1 : Temps Réel & Extrêmes ---
with tab1:
    st.subheader("📡 Conditions Actuelles (Flux Ecowitt Cloud)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Température", f"{temp} °C" if temp is not None else "--", delta=f"{delta_temp:+.1f} °C")
    col2.metric("Humidité", f"{humidity} %" if humidity is not None else "--", delta=f"{delta_hum:+.1f} %")
    col3.metric("Pression relative", f"{pressure} hPa" if pressure is not None else "--", delta=f"{delta_press:+.2f} hPa")
    col4.metric("Pression absolue", f"{pressure_abs} hPa" if pressure_abs is not None else "--")

    st.markdown("---")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Température Ressentie", f"{temp_ressentie} °C" if temp_ressentie is not None else "--", help=mode_ressenti)
    col6.metric("Vent moyen", f"{wind_speed} km/h" if wind_speed is not None else "--")
    col7.metric("Rafale", f"{wind_gust} km/h" if wind_gust is not None else "--")
    col8.metric("Direction", f"{degres_vers_cardinal(wind_dir)} ({int(wind_dir)}°)" if wind_dir is not None else "--")

    st.markdown("---")
    col9, _ = st.columns(2)
    col9.metric("Pluie du jour", f"{rain_day} mm" if rain_day is not None else "0.0 mm")

    st.markdown("### 🏆 Extrêmes & Records du jour")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Max Chaleur (Tx)", f"{max_temp} °C" if max_temp != "--" else "--", f"à {max_temp_time}" if max_temp_time else "")
    e2.metric("Min Fraîcheur (Tn)", f"{min_temp} °C" if min_temp != "--" else "--", f"à {min_temp_time}" if min_temp_time else "")
    e3.metric("Vent max mesuré", f"{max_wind} km/h")
    e4.metric("Rafale la plus rapide", f"{max_gust} km/h")

    st.caption(f"Dernière synchronisation cloud : **{current_time_str}** | Points en base SQLite : **{len(df_hist)}**")

# --- ONGLET 2 : Rose des Vents ---
with tab2:
    st.subheader("🧭 Rose des Vents Cumulée (Base SQLite)")
    if not df_hist.empty:
        fig_rose = go.Figure()
        fig_rose.add_trace(go.Barpolar(
            r=df_hist["vent"],
            theta=df_hist["direction"],
            width=15,
            marker=dict(color=df_hist["vent"], colorscale="Blues", showscale=True, colorbar=dict(title="km/h")),
            opacity=0.75,
            name="Vents"
        ))
        fig_rose.update_layout(
            polar=dict(radialaxis=dict(visible=True, title="Vitesse (km/h)"), angularaxis=dict(direction="clockwise", period=360, rotation=90)),
            height=500, margin=dict(t=40, b=40, l=40, r=40)
        )
        st.plotly_chart(fig_rose, use_container_width=True)
        st.info(f"📊 Mesures historiques cumulées : **{len(df_hist)}** points")
    else:
        st.info("Accumulation des données de vent en cours...")

# --- ONGLET 3 : Pluviométrie ---
with tab3:
    st.subheader("🌧️ Suivi de la Pluviométrie")
    if not df_hist.empty and "pluie" in df_hist.columns:
        df_rain = df_hist.copy()
        df_rain["date_seule"] = df_rain["timestamp"].dt.date
        df_rain["mois"] = df_rain["timestamp"].dt.strftime("%Y-%m")

        df_journalier = df_rain.groupby("date_seule")["pluie"].max().reset_index()
        df_mensuel = df_rain.groupby("mois")["pluie"].max().reset_index()

        col_p1, col_p2, col_p3 = st.columns(3)
        derniere_pluie_jour = df_journalier.iloc[-1]["pluie"] if not df_journalier.empty else 0.0
        col_p1.metric("Cumul Journalier Récent", f"{derniere_pluie_jour} mm")
        col_p2.metric("Total Mois en cours", f"{df_mensuel.iloc[-1]['pluie'] if not df_mensuel.empty else 0.0} mm")
        col_p3.metric("Max enregistré sur un jour", f"{df_journalier['pluie'].max()} mm")

        st.markdown("### 📊 Cumul de pluie par jour (mm)")
        fig_rain_day = px.bar(df_journalier, x="date_seule", y="pluie", labels={"date_seule": "Date", "pluie": "Pluie (mm)"}, color_discrete_sequence=["#2980b9"])
        st.plotly_chart(fig_rain_day, use_container_width=True)

        st.markdown("### 🗓️ Cumul de pluie par mois (mm)")
        fig_rain_month = px.bar(df_mensuel, x="mois", y="pluie", labels={"mois": "Mois", "pluie": "Pluie (mm)"}, color_discrete_sequence=["#16a085"])
        st.plotly_chart(fig_rain_month, use_container_width=True)
    else:
        st.info("Accumulation des données de pluie en cours...")

# --- ONGLET 4 : Plancher Nuageux & Paysage ---
with tab4:
    st.subheader("🏔️ Visualisation du Plancher Nuageux sur les Crêtes")
    if base_cumulus_sol is not None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Altitude du village", "900 m")
        c2.metric("Hauteur base des nuages / sol", f"+{base_cumulus_sol} m")
        c3.metric("Altitude absolue du nuage", f"{altitude_cumulus_mer} m")

        # Intégration graphique avec la photo et le niveau nuageux
        fig_pano = go.Figure()

        # Ajout du profil de montagne stylisé et positionnement du nuage dynamique
        fig_pano.add_trace(go.Scatter(x=[0, 1.5, 3, 4.5, 6], y=[300, 900, 450, 900, 300], mode="lines", fill="tozeroy", fillcolor="rgba(80, 50, 30, 0.5)", line=dict(color="#3d2817", width=3), hoverinfo="skip", name="Relief Habère-Poche"))
        fig_pano.add_trace(go.Scatter(x=[3], y=[altitude_cumulus_mer], mode="markers+text", marker=dict(size=48, color="#ffffff", line=dict(color="#4a90e2", width=3), symbol="circle"), text=[f"☁️ Base des Cumulus\n({altitude_cumulus_mer} m)"], textposition="top center", textfont=dict(size=15, color="#1e3f66", family="Arial Black")))

        fig_pano.update_layout(
            title="Position estimée des nuages par rapport aux reliefs locaux",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(title="Altitude (mètres)", range=[100, max(altitude_cumulus_mer + 800, 2400)]),
            plot_bgcolor="rgba(220, 240, 255, 0.8)",
            height=500,
            showlegend=False
        )
        st.plotly_chart(fig_pano, use_container_width=True)
        st.caption("📷 Les crêtes immortalisées depuis la Vallée Verte servent de repère visuel pour situer l'épaisseur de la couche convective.")
    else:
        st.info("⚠️ Données requises pour le calcul du plancher nuageux.")

# --- ONGLET 5 : Historique & Tendances Graphiques ---
with tab5:
    st.subheader("📈 Suivi Chronologique (Persistant)")
    if not df_hist.empty:
        fig_temp = px.line(df_hist, x="timestamp", y=["temperature", "ressenti"], markers=False, title="🌡️ Température et Ressenti")
        st.plotly_chart(fig_temp, use_container_width=True)

        fig_hum = px.line(df_hist, x="timestamp", y="humidite", markers=False, color_discrete_sequence=["#3498db"], title="💧 Humidité Relative")
        st.plotly_chart(fig_hum, use_container_width=True)

        fig_press = px.line(df_hist, x="timestamp", y=["pression", "pression_abs"], markers=False, title="BAROMÈTRE — Pressions")
        st.plotly_chart(fig_press, use_container_width=True)
    else:
        st.info("📊 En attente de points d'historique dans la base...")

# --- ONGLET 6 : Prévisions & Analyse ---
with tab6:
    st.subheader("🔮 Prévisions Expertes & Indicateurs de Moyenne Montagne")

    if pressure is not None:
        st.success(f"### 🎯 Tendance Barométrique : **{prevision_texte}**")
        c_z1, c_z2 = st.columns(2)
        c_z1.metric("Pression relative", f"{pressure} hPa")
        c_z2.metric("Tendance barométrique", f"{tendance_baro:+.2f} hPa")
    else:
        st.warning("Données barométriques non disponibles.")

    st.markdown("---")

    st.subheader("🌱 Indicateurs Jardin & Montagne (Gel & ETP)")
    g1, g2, g3 = st.columns(3)
    g1.metric("Risque Gel / Gélives", risque_gel)
    g2.metric("Évapotranspiration (ETP du jour)", f"{etp_val} mm/j", help="Estimation de l'évaporation et transpiration des sols/plantes")
    g3.metric("Point de rosée", f"{point_rosee} °C", help="Température à laquelle l'air se sature (condensation)")

    st.markdown("---")

    st.subheader("💨 Analyse du Vent & Signification Locale")
    if wind_dir is not None:
        nom_cardinal = degres_vers_cardinal(wind_dir)
        interpretation_vent, emoji_vent = interpreter_vent_local(wind_dir, wind_speed)

        col_v1, col_v2 = st.columns([1, 2])
        with col_v1:
            st.metric("Secteur actuel", f"{nom_cardinal} ({int(wind_dir)}°)", f"{wind_speed} km/h")
        with col_v2:
            st.markdown(f"### {emoji_vent} {interpretation_vent}")
            st.caption("Interprétation empirique basée sur l'orientation des flux dans notre configuration de moyenne montagne à Habère-Poche.")
    else:
        st.info("Données de vent insuffisantes pour l'analyse locale.")
