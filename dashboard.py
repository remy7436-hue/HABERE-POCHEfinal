from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import sqlite3
import streamlit as st
from streamlit_autorefresh import st_autorefresh

plotly_disponible = True
try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    plotly_disponible = False

# --- Configuration Weather Underground ---
WU_STATION_ID = "IHABRE19"
WU_API_KEY = "7783683bcac243da83683bcac213da8d"
DB_FILE = "meteo_historique.db"

# --- Configuration Streamlit & Auto-refresh ---
st.set_page_config(
    page_title="Météo Habère-Poche", page_icon="🌤️", layout="wide"
)

# Actualisation automatique toutes les 60 secondes
st_autorefresh(interval=60000, key="meteo_autorefresh")


def degre_vers_cardinal(degre):
    """Convertit un angle en degrés en point cardinal."""
    if degre is None:
        return "N/A"
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"
    ]
    index = int((degre + 11.25) / 22.5) % 16
    return directions[index]


def calculer_point_rosee(temp_c, humidity):
    """Calcule approximativement le point de rosée (°C) (Formule de Magnus-Tetens)."""
    if humidity <= 0 or humidity > 100:
        return temp_c
    a = 17.27
    b = 237.7
    alpha = ((a * temp_c) / (b + temp_c)) + np.log(humidity / 100.0)
    dew_point = (b * alpha) / (a - alpha)
    return round(dew_point, 1)


def calculer_et0_simplifie(temp_c, wind_speed, humidity, solar_rad):
    """Estime l'évapotranspiration potentielle journalière simplifiée (mm/jour)."""
    temp_factor = max(0, temp_c + 5)
    wind_factor = 1 + (wind_speed / 15.0)
    humidity_factor = max(0.1, (100 - humidity) / 50.0)
    solar_factor = max(0.1, solar_rad / 300.0)
    et0 = round((temp_factor * wind_factor * humidity_factor * solar_factor) * 0.08, 2)
    return max(0.0, et0)


def analyser_indice_uv(uv):
    """Analyse l'indice UV et retourne un niveau, une couleur et des recommandations adaptées."""
    if uv <= 2:
        return "Faible 🟢", "Pas de protection particulière nécessaire.", []
    elif uv <= 5:
        return "Modéré 🟡", "Protection recommandée lors des expositions prolongées.", ["Lunettes de soleil", "Casquette"]
    elif uv <= 7:
        return "Élevé 🟠", "Protection solaire indispensable (surtout en montagne !).", ["Crème solaire (indice 30+)", "Lunettes de soleil", "Casquette", "Ombre entre 12h et 16h"]
    elif uv <= 10:
        return "Très élevé 🔴", "Protection renforcée obligatoire en altitude.", ["Crème solaire (indice 50+)", "Lunettes cat. 3 ou 4", "Vêtements couvrants"]
    else:
        return "Extrême 🟣", "Danger exceptionnel. Éviter toute exposition prolongée.", ["Protection intégrale maximale"]


def calculer_phase_lune(dt: datetime):
    """Calcule de manière précise la phase de la lune."""
    year, month, day = dt.year, dt.month, dt.day
    if month <= 2:
        year -= 1
        month += 12
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    JD = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
    days_since_new = JD - 2460321.0
    synodic_month = 29.53058867
    lunar_age = days_since_new % synodic_month
    if lunar_age < 0:
        lunar_age += synodic_month
    illumination = round((1 - np.cos(2 * np.pi * lunar_age / synodic_month)) / 2 * 100)

    if lunar_age < 1.84:
        phase, icone = "Nouvelle Lune", "🌑"
    elif lunar_age < 5.54:
        phase, icone = "Premier Croissant", "🌒"
    elif lunar_age < 9.23:
        phase, icone = "Premier Quartier", "🌓"
    elif lunar_age < 12.92:
        phase, icone = "Lune Gibbeuse Croissante", "🌔"
    elif lunar_age < 16.61:
        phase, icone = "Pleine Lune", "🌕"
    elif lunar_age < 20.30:
        phase, icone = "Lune Gibbeuse Décroissante", "🌖"
    elif lunar_age < 23.99:
        phase, icone = "Dernier Quartier", "🌗"
    elif lunar_age < 27.68:
        phase, icone = "Dernier Croissant", "🌘"
    else:
        phase, icone = "Nouvelle Lune", "🌑"
    return phase, icone, round(lunar_age, 1), illumination


def prevision_zambretti_avancee(pression_actuelle, delta_pression_3h, mois, dir_cardinal, solar_rad, humidity, temp_c, delta_hum_3h):
    """Algorithme de Zambretti enrichi pour la montagne."""
    p_mer = pression_actuelle * pow(1.0 - (0.0065 * 900.0) / (15.0 + 0.0065 * 900.0 + 273.15), -5.257)
    is_summer = mois in [4, 5, 6, 7, 8, 9]

    if delta_pression_3h > 0.6:
        val = (127 if is_summer else 144) - (0.12 if is_summer else 0.13) * p_mer
        tendance_txt = "Hausse nette 📈"
    elif delta_pression_3h < -0.6:
        val = (185 if is_summer else 171) - (0.16 if is_summer else 0.15) * p_mer
        tendance_txt = "Chute rapide 📉"
    else:
        val = (135 if is_summer else 145) - (0.13 if is_summer else 0.14) * p_mer
        tendance_txt = "Stationnaire ➡️"

    if delta_pression_3h <= -2.0:
        val += 50
    elif delta_pression_3h <= -1.2:
        val += 30

    if delta_hum_3h > 8 and humidity > 80:
        val += 15

    if dir_cardinal in ["NO", "O", "ONO"] and delta_pression_3h < 0:
        val += 15

    risque_orage = False
    if is_summer and solar_rad > 500 and humidity > 50 and temp_c > 20 and delta_pression_3h <= 0:
        risque_orage = True
        val = max(val, 105)

    if val < 45:
        text = "Temps splendide et stable ☀️"
    elif val < 55:
        text = "Beau temps, puis voilé / se couvrant 🌤️"
    elif val < 65:
        text = "Éclaircies mais risque d'averses sur les crêtes ⛅"
    elif val < 75:
        text = "Temps changeant, instabilité 🌥️"
    elif val < 85:
        text = "Averses probables, dégradation 🌦️"
    elif val < 95:
        text = "Pluie et dégradation rapide 🌧️"
    elif val < 105:
        text = "Temps perturbé, agité et pluvieux 🌧️💨"
    else:
        text = "Risque d'orages de masse d'air / Instabilité marquée ⚡🌧️"

    return text, tendance_txt, risque_orage


def init_db_et_maj():
    """Initialise la base SQLite et récupère la dernière observation de Weather Underground."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT UNIQUE,
            temp_c REAL, humidity INTEGER, pressure REAL,
            wind_speed REAL, wind_gust REAL, wind_direction INTEGER,
            rain_rate REAL, rain_day REAL, rain_week REAL,
            rain_month REAL, rain_year REAL, solar_radiation REAL, uv INTEGER
        )
    """)
    conn.commit()

    url = f"https://api.weather.com/v2/pws/observations/current?stationId={WU_STATION_ID}&format=json&units=m&apiKey={WU_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "observations" in data and len(data["observations"]) > 0:
                obs = data["observations"][0]
                
                obs_time = datetime.now()
                if "obsTimeLocal" in obs:
                    try:
                        obs_time = datetime.strptime(obs["obsTimeLocal"], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                
                date_time_str = obs_time.strftime("%Y-%m-%d %H:%M:%S")
                metric = obs.get("metric", {})

                temp_c = float(metric.get("temp", 0.0))
                humidity = int(obs.get("humidity", 0))
                pressure = float(metric.get("pressure", 0.0))
                wind_speed = float(metric.get("windSpeed", 0.0))
                wind_gust = float(metric.get("windGust", 0.0))
                wind_direction = int(obs.get("winddir", 0))
                rain_rate = float(metric.get("precipRate", 0.0))
                rain_day = float(metric.get("precipTotal", 0.0))
                solar_radiation = float(obs.get("solarRadiation", 0.0))
                uv = int(obs.get("uv", 0))

                cursor.execute("""
                    INSERT OR REPLACE INTO mesures (
                        date_time, temp_c, humidity, pressure, wind_speed,
                        wind_gust, wind_direction, rain_rate, rain_day,
                        rain_week, rain_month, rain_year, solar_radiation, uv
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, ?, ?)
                """, (date_time_str, temp_c, humidity, pressure, wind_speed, wind_gust, wind_direction, rain_rate, rain_day, solar_radiation, uv))
                conn.commit()
    except Exception as e:
        print(f"⚠️ Erreur sync Weather Underground : {e}")
    finally:
        conn.close()


init_db_et_maj()

if st.sidebar.button("🔄 Rafraîchir les données"):
    st.rerun()

st.title("🌤️ Suivi Météorologique Local")
st.markdown("Station Ecowitt (GW3000) • Habère-Poche (900 m) • Flux Weather Underground (IHABRE19)")


def load_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM mesures ORDER BY date_time DESC", conn)
    conn.close()
    if not df.empty:
        df["date_time"] = pd.to_datetime(df["date_time"])
        df["cardinal"] = df["wind_direction"].apply(degre_vers_cardinal)
    return df


df = load_data()

if df.empty:
    st.warning("Aucune donnée disponible pour l'instant.")
else:
    derniere_mesure = df.iloc[0]
    dir_deg = derniere_mesure['wind_direction']
    dir_card = derniere_mesure['cardinal']
    df_sorted = df.sort_values("date_time")
    current_time = derniere_mesure['date_time']

    # --- Calculs pluie jour et mois (avec base fixe de 66 mm pour le mois) ---
    pluie_jour = derniere_mesure.get('rain_day', 0.0)
    
    df['date_dt'] = pd.to_datetime(df['date_time'])
    df_mois_en_cours = df[
        (df['date_dt'].dt.year == current_time.year) & 
        (df['date_dt'].dt.month == current_time.month)
    ]
    
    # Cumul de base connu pour le mois d'août
    PLUIE_BASE_MOIS = 66.0 
    
    if not df_mois_en_cours.empty:
        df_mois_en_cours['jour'] = df_mois_en_cours['date_dt'].dt.date
        pluie_mois_suivie = round(df_mois_en_cours.groupby('jour')['rain_day'].max().sum(), 1)
        # On s'assure d'ajouter la base de 66mm (en évitant de compter deux fois la pluie du jour si elle est déjà englobée dans la base ou non, 
        # ici on prend la base fixe + l'incrément journalier glissant par sécurité)
        pluie_mois = round(PLUIE_BASE_MOIS + pluie_jour, 1)
    else:
        pluie_mois = round(PLUIE_BASE_MOIS + pluie_jour, 1)

    target_1h = current_time - timedelta(hours=1)
    df_temp_1h = df_sorted.copy()
    df_temp_1h['diff_1h'] = (df_temp_1h['date_time'] - target_1h).abs()
    row_1h = df_temp_1h.loc[df_temp_1h['diff_1h'].idxmin()] if not df_temp_1h.empty else None

    delta_temp = round(derniere_mesure['temp_c'] - row_1h['temp_c'], 1) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0.0
    delta_hum = int(derniere_mesure['humidity'] - row_1h['humidity']) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0
    delta_press = round(derniere_mesure['pressure'] - row_1h['pressure'], 1) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0.0

    target_3h = current_time - timedelta(hours=3)
    df_temp_3h = df_sorted.copy()
    df_temp_3h['diff_3h'] = (df_temp_3h['date_time'] - target_3h).abs()
    row_3h = df_temp_3h.loc[df_temp_3h['diff_3h'].idxmin()] if not df_temp_3h.empty else None
    delta_press_3h = round(derniere_mesure['pressure'] - row_3h['pressure'], 1) if row_3h is not None and row_3h['diff_3h'] <= timedelta(minutes=45) else delta_press * 3
    delta_hum_3h = int(derniere_mesure['humidity'] - row_3h['humidity']) if row_3h is not None and row_3h['diff_3h'] <= timedelta(minutes=45) else 0

    df_24h = df_sorted[df_sorted['date_time'] >= (current_time - timedelta(hours=24))]
    if df_24h.empty:
        df_24h = df_sorted

    max_gust_row = df_24h.loc[df_24h['wind_gust'].idxmax()]
    max_wind_row = df_24h.loc[df_24h['wind_speed'].idxmax()]
    dew_point = calculer_point_rosee(derniere_mesure['temp_c'], derniere_mesure['humidity'])
    et0_jour = calculer_et0_simplifie(derniere_mesure['temp_c'], derniere_mesure['wind_speed'], derniere_mesure['humidity'], derniere_mesure['solar_radiation'])
    pluie_24h_glissante = round(df_24h['rain_day'].max() - df_24h['rain_day'].min(), 1) if not df_24h.empty else derniere_mesure['rain_day']

    lune_phase, lune_icone, _, lune_illum = calculer_phase_lune(current_time)
    uv_actuel = int(derniere_mesure['uv'])
    uv_niveau, uv_conseil_txt, uv_recos = analyser_indice_uv(uv_actuel)

    mois_actuel = current_time.month
    normales_ref = {
        1: -1.0, 2: 0.0, 3: 4.0, 4: 8.0, 5: 12.0, 6: 16.0,
        7: 18.0, 8: 17.5, 9: 13.0, 10: 8.5, 11: 3.0, 12: 0.0
    }
    normale_saison = normales_ref.get(mois_actuel, 15.0)
    df_mois_actuel = df_sorted[(df_sorted['date_time'].dt.year == current_time.year) & (df_sorted['date_time'].dt.month == mois_actuel)]
    moy_mois_station = round(df_mois_actuel['temp_c'].mean(), 1) if len(df_mois_actuel) > 10 else derniere_mesure['temp_c']
    donnees_suffisantes = len(df_mois_actuel) > 10

    tab_dashboard, tab_previ, tab_climat, tab_graph, tab_brutes = st.tabs([
        "📊 Tableau de Bord",
        "🔮 Prévisions & Risques",
        "🌱 Climat & Jardin",
        "📈 Graphiques",
        "📁 Données Brutes"
    ])

    with tab_dashboard:
        st.subheader("Conditions Météo en Direct")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Température", f"{derniere_mesure['temp_c']} °C", delta=f"{delta_temp:+.1f} °C /1h")
        c2.metric("Humidité", f"{derniere_mesure['humidity']} %", delta=f"{delta_hum:+d} % /1h")
        c3.metric("Pression", f"{derniere_mesure['pressure']} hPa", delta=f"{delta_press:+.1f} hPa /1h")
        c4.metric("Pluie glissante (24h)", f"{pluie_24h_glissante} mm")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Vent moyen", f"{derniere_mesure['wind_speed']} km/h", delta=f"Max {max_wind_row['wind_speed']} à {max_wind_row['date_time'].strftime('%H:%M')}")
        c6.metric("Direction", f"{dir_card} ({dir_deg}°)")
        c7.metric("Rafale max (24h)", f"{max_gust_row['wind_gust']} km/h", delta=f"À {max_gust_row['date_time'].strftime('%H:%M')}")
        c8.metric("Point de rosée", f"{dew_point} °C")

        st.subheader("☀️ Solaire & Pluviométrie")
        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Indice UV", uv_actuel, delta=uv_niveau)
        u2.metric("Rayonnement", f"{derniere_mesure['solar_radiation']} W/m²")
        u3.metric("Pluie du jour", f"{pluie_jour} mm")
        u4.metric("Pluie du mois", f"{pluie_mois} mm")

        if uv_actuel >= 3:
            recos_str = " • ".join([f"**{r}**" for r in uv_recos])
            st.info(f"🕶️ **Alerte Solaire :** {uv_conseil_txt} — Pensez à : {recos_str}")

    with tab_previ:
        st.subheader("🔮 Bulletin Prévisionnel & Analyse des Risques")
        z_text, z_trend, risque_orage = prevision_zambretti_avancee(
            derniere_mesure['pressure'], delta_press_3h, current_time.month,
            dir_card, derniere_mesure['solar_radiation'], derniere_mesure['humidity'],
            derniere_mesure['temp_c'], delta_hum_3h
        )

        p1, p2 = st.columns(2)
        with p1:
            if risque_orage or delta_press_3h <= -2.0:
                st.error(f"**Prévision (12-24h) :**\n\n### {z_text}")
            else:
                st.success(f"**Prévision (12-24h) :**\n\n### {z_text}")

            st.write(f"* **Tendance barométrique (3h) :** {z_trend} ({delta_press_3h:+.1f} hPa)")
            st.write(f"* **Tendance humidité (3h) :** {delta_hum_3h:+d} %")
            st.write(f"* **Flux dominant :** {dir_card} ({dir_deg}°)")

            cart_temp_dew = round(derniere_mesure['temp_c'] - dew_point, 1)
            if derniere_mesure['temp_c'] <= 2.0:
                st.error(f"❄️ **ALERTE GEL :** Température de {derniere_mesure['temp_c']}°C à 900m.")
            if cart_temp_dew < 1.5 and derniere_mesure['humidity'] > 88:
                st.warning(f"🌫️ **ALERTE BROUILLARD :** Écart air/rosée critique ({cart_temp_dew}°C).")
            if risque_orage:
                st.warning("⚡ **Alerte Convective :** Risque de développement orageux diurne sur les reliefs.")

        with p2:
            st.markdown("### 🧭 Rose des Vents (7j)")
            if plotly_disponible and not df_sorted.empty:
                bins = [0, 5, 10, 15, 20, 50]
                labels = ['0-5', '5-10', '10-15', '15-20', '>20']
                df_sorted['vitesse_tranche'] = pd.cut(df_sorted['wind_speed'], bins=bins, labels=labels, right=False)
                df_sorted['dir_sector'] = (np.floor((df_sorted['wind_direction'] + 11.25) / 22.5) * 22.5) % 360
                rose_df = df_sorted.groupby(['dir_sector', 'vitesse_tranche'], observed=False).size().reset_index(name='count')

                fig = px.bar_polar(rose_df, r='count', theta='dir_sector', color='vitesse_tranche',
                                   color_discrete_sequence=px.colors.sequential.Plasma_r, template="plotly_dark")
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                  margin=dict(l=10, r=10, t=10, b=10),
                                  polar=dict(bgcolor='rgba(0,0,0,0)', radialaxis=dict(showticklabels=False),
                                             angularaxis=dict(direction="clockwise", rotation=90,
                                                              tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                                                              ticktext=['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'])))
                st.plotly_chart(fig, use_container_width=True)

    with tab_climat:
        st.subheader("🌱 Climatologie, Jardin & Astronomie")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.markdown("### 🌡️ Comparatif Climatique (900m)")
            diff_normale = round(moy_mois_station - normale_saison, 1)
            if not donnees_suffisantes:
                st.info("💡 Station récente : estimation basée sur la température actuelle.")
            st.write(f"* **Moyenne du mois :** `{moy_mois_station} °C`")
            st.write(f"* **Normale saisonnière :** `{normale_saison} °C`")
            if diff_normale > 0.5:
                st.warning(f"🌡️ Mois plus chaud de `+{diff_normale} °C` par rapport à la normale.")
            elif diff_normale < -0.5:
                st.info(f"❄️ Mois plus frais de `{diff_normale} °C` par rapport à la normale.")
            else:
                st.success("✅ Températures conformes aux normales de saison.")

            st.markdown("### 💧 Suivi de l'Évaporation")
            st.metric("Évapotranspiration (ET0)", f"{et0_jour} mm/j", help="Indice d'assèchement du sol et des plantes")

        with c_col2:
            st.markdown("### 🌙 Calendrier Lunaire")
            st.metric(f"{lune_icone} {lune_phase}", f"Illumination {lune_illum}%")
            
            lune_cols = st.columns(5)
            for i, offset in enumerate(range(-2, 3)):
                futur_dt = current_time + timedelta(days=offset)
                f_phase, f_icone_j, _, f_illum_j = calculer_phase_lune(futur_dt)
                label_jour = "Aujourd'hui" if offset == 0 else futur_dt.strftime("%d/%m")
                with lune_cols[i]:
                    st.markdown(f"""
                        <div style='text-align: center; background: rgba(255,255,255,0.05); padding: 8px; border-radius: 8px;'>
                            <b style='font-size: 0.85em;'>{label_jour}</b><br>
                            <span style='font-size: 24px;'>{f_icone_j}</span><br>
                            <small>{f_illum_j}%</small>
                        </div>
                    """, unsafe_allow_html=True)

    with tab_graph:
        st.subheader("📈 Graphiques d'Évolution")
        periode_choisie = st.radio("Sélectionner la période des graphiques :", ["24 heures", "48 heures", "7 jours"], horizontal=True)
        
        heures_map = {"24 heures": 24, "48 heures": 48, "7 jours": 24 * 7}
        limite_dt = current_time - timedelta(hours=heures_map[periode_choisie])
        df_graphe = df_sorted[df_sorted['date_time'] >= limite_dt]

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("### Température (°C)")
            st.line_chart(df_graphe.set_index("date_time")["temp_c"])
        with g2:
            st.markdown("### Pression (hPa)")
            if plotly_disponible:
                fig_p = px.line(df_graphe, x="date_time", y="pressure", template="plotly_dark")
                fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.line_chart(df_graphe.set_index("date_time")["pressure"])

        g3, g4 = st.columns(2)
        with g3:
            st.markdown("### Vent (km/h)")
            st.line_chart(df_graphe.set_index("date_time")[["wind_speed", "wind_gust"]])
        with g4:
            st.markdown("### Rayonnement Solaire (W/m²)")
            st.line_chart(df_graphe.set_index("date_time"]["solar_radiation"])

    with tab_brutes:
        st.subheader("📁 Historique complet des mesures")
        st.dataframe(df, use_container_width=True)
