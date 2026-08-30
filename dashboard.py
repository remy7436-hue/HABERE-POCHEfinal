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

# --- Configuration de l'API Ecowitt ---
APPLICATION_KEY = "9A10455F8BBE5DFFEA6E970BF213172D"
API_KEY = "e7c7ac1f-9f8d-41b7-8d4e-ff02bafac937"
MAC = "00:70:07:C2:E4:93"
DB_FILE = "meteo_historique.db"

# --- Configuration Streamlit & Auto-refresh ---
st.set_page_config(
    page_title="Météo Locale - Habère-Poche", page_icon="🌤️", layout="wide"
)

# Actualisation automatique toutes les 60 secondes (60000 millisecondes)
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


def analyser_indice_uv(uv):
    """Analyse l'indice UV et retourne un niveau, une couleur et des recommandations adaptées (spécial montagne)."""
    if uv <= 2:
        return "Faible 🟢", "Pas de protection particulière nécessaire.", []
    elif uv <= 5:
        return "Modéré 🟡", "Protection recommandée lors des expositions prolongées.", ["Lunettes de soleil", "Casquette"]
    elif uv <= 7:
        return "Élevé 🟠", "Protection solaire indispensable (surtout en montagne !).", ["Crème solaire (indice 30+)", "Lunettes de soleil", "Casquette ou chapeau", "Recherche d'ombre entre 12h et 16h"]
    elif uv <= 10:
        return "Très élevé 🔴", "Protection renforcée obligatoire. Le rayonnement en altitude est intense.", ["Crème solaire (indice 50+)", "Lunettes de soleil de catégorie 3 ou 4", "Casquette / Vêtements couvrant", "Éviter l'exposition aux heures de plénitude"]
    else:
        return "Extrême 🟣", "Danger exceptionnel. Évitez toute exposition prolongée au soleil.", ["Protection intégrale maximale (Crème 50+, lunettes cat. 4, vêtements anti-UV)", "Rester à l'ombre absolument"]


def calculer_phase_lune(dt: datetime):
    """Calcule de manière précise la phase de la lune (Algorithme astronomique par Jour Julien)."""
    year = dt.year
    month = dt.month
    day = dt.day

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

    if lunar_age < 1.84566:
        phase, icone = "Nouvelle Lune", "🌑"
    elif lunar_age < 5.53699:
        phase, icone = "Premier Croissant", "🌒"
    elif lunar_age < 9.22831:
        phase, icone = "Premier Quartier", "🌓"
    elif lunar_age < 12.91964:
        phase, icone = "Lune Gibbeuse Croissante", "🌔"
    elif lunar_age < 16.61096:
        phase, icone = "Pleine Lune", "🌕"
    elif lunar_age < 20.30229:
        phase, icone = "Lune Gibbeuse Décroissante", "🌖"
    elif lunar_age < 23.99361:
        phase, icone = "Dernier Quartier", "🌗"
    elif lunar_age < 27.68494:
        phase, icone = "Dernier Croissant", "🌘"
    else:
        phase, icone = "Nouvelle Lune", "🌑"

    return phase, icone, round(lunar_age, 1), illumination


def prevision_zambretti_avancee(pression_actuelle, delta_pression_3h, mois, dir_cardinal, solar_rad, humidity, temp_c):
    """Algorithme de Zambretti enrichi avec des seuils de réactivité renforcés pour la montagne."""
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


@st.cache_resource
def synchroniser_au_demarrage():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT UNIQUE,
            temp_c REAL,
            humidity INTEGER,
            pressure REAL,
            wind_speed REAL,
            wind_gust REAL,
            wind_direction INTEGER,
            rain_rate REAL,
            rain_day REAL,
            rain_week REAL,
            rain_month REAL,
            rain_year REAL,
            solar_radiation REAL,
            uv INTEGER
        )
    """)
    conn.commit()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    url = "https://api.ecowitt.net/api/v3/device/history"
    params = {
        "application_key": APPLICATION_KEY,
        "api_key": API_KEY,
        "mac": MAC,
        "start_date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S"),
        "call_back": "outdoor,wind,pressure,solar_and_uvi,rainfall",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        result = response.json()
        if result.get("code") == 0:
            data = result.get("data", {})
            outdoor = data.get("outdoor", {})
            wind = data.get("wind", {})
            pressure_data = data.get("pressure", {})
            solar_data = data.get("solar_and_uvi", {})
            rain = data.get("rainfall", {})

            temp_dict = outdoor.get("temperature", {}).get("list", {})
            if not temp_dict:
                temp_dict = outdoor.get("temp", {}).get("list", {})

            for timestamp_str, temp_f_val in temp_dict.items():
                try:
                    dt = datetime.fromtimestamp(int(timestamp_str))
                    date_time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue

                try:
                    temp_c = round((float(temp_f_val) - 32) * 5.0 / 9.0, 1)
                except Exception:
                    temp_c = 0.0

                try:
                    humidity = int(float(outdoor.get("humidity", {}).get("list", {}).get(timestamp_str, 0)))
                except Exception:
                    humidity = 0

                try:
                    pressure = 0.0
                    val_rel = pressure_data.get("relative", {}).get("list", {}).get(timestamp_str)
                    if not val_rel:
                        val_rel = pressure_data.get("baromrel", {}).get("list", {}).get(timestamp_str)
                    if val_rel and float(val_rel) > 0:
                        pressure = round(float(val_rel) * 33.8639, 1)
                    else:
                        val_abs = pressure_data.get("absolute", {}).get("list", {}).get(timestamp_str)
                        if not val_abs:
                            val_abs = pressure_data.get("baromabs", {}).get("list", {}).get(timestamp_str)
                        if val_abs and float(val_abs) > 0:
                            pressure = round(float(val_abs) * 33.8639, 1)
                except Exception:
                    pressure = 0.0

                try:
                    wind_speed = round(float(wind.get("wind_speed", {}).get("list", {}).get(timestamp_str, 0)) * 1.60934, 1)
                except Exception:
                    wind_speed = 0.0

                try:
                    wind_gust = round(float(wind.get("wind_gust", {}).get("list", {}).get(timestamp_str, 0)) * 1.60934, 1)
                except Exception:
                    wind_gust = 0.0

                try:
                    wind_direction = int(float(wind.get("wind_direction", {}).get("list", {}).get(timestamp_str, 0)))
                except Exception:
                    wind_direction = 0

                try:
                    rain_rate = round(float(rain.get("rain_rate", {}).get("list", {}).get(timestamp_str, 0)) * 25.4, 1)
                except Exception:
                    rain_rate = 0.0

                try:
                    rain_day = round(float(rain.get("rain_day", {}).get("list", {}).get(timestamp_str, 0)) * 25.4, 1)
                except Exception:
                    rain_day = 0.0

                try:
                    rain_week = round(float(rain.get("rain_week", {}).get("list", {}).get(timestamp_str, 0)) * 25.4, 1)
                except Exception:
                    rain_week = 0.0

                try:
                    val_month = rain.get("rain_month", {}).get("list", {}).get(timestamp_str)
                    if not val_month:
                        val_month = rain.get("monthly", {}).get("list", {}).get(timestamp_str, 0)
                    rain_month = round(float(val_month) * 25.4, 1)
                except Exception:
                    rain_month = 0.0

                try:
                    val_year = rain.get("rain_year", {}).get("list", {}).get(timestamp_str)
                    if not val_year:
                        val_year = rain.get("yearly", {}).get("list", {}).get(timestamp_str, 0)
                    rain_year = round(float(val_year) * 25.4, 1)
                except Exception:
                    rain_year = 0.0

                try:
                    solar_radiation = float(solar_data.get("solar", {}).get("list", {}).get(timestamp_str, 0))
                except Exception:
                    solar_radiation = 0.0

                try:
                    uv = int(float(solar_data.get("uvi", {}).get("list", {}).get(timestamp_str, 0)))
                except Exception:
                    uv = 0

                if temp_c < -50 or temp_c > 60:
                    continue

                cursor.execute(
                    """
                        INSERT OR IGNORE INTO mesures (
                            date_time, temp_c, humidity, pressure, wind_speed,
                            wind_gust, wind_direction, rain_rate, rain_day,
                            rain_week, rain_month, rain_year,
                            solar_radiation, uv
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date_time_str, temp_c, humidity, pressure, wind_speed,
                        wind_gust, wind_direction, rain_rate, rain_day,
                        rain_week, rain_month, rain_year, solar_radiation, uv,
                    ),
                )
            conn.commit()
    except Exception as e:
        print(f"⚠️ Erreur sync cloud : {e}")
    finally:
        conn.close()


synchroniser_au_demarrage()

# --- Paramétrage des offsets dans la barre latérale ---
st.sidebar.header("⚙️ Calibrage Capteurs")
offset_temp = st.sidebar.slider("Offset Température (°C)", min_value=-5.0, max_value=5.0, value=-1.1, step=0.1, help="Permet d'ajuster l'écart avec la console officielle.")
offset_hum = st.sidebar.slider("Offset Humidité (%)", min_value=-10, max_value=10, value=3, step=1, help="Permet d'ajuster l'écart d'humidité.")

st.title("🌤️ Suivi Météorologique Local")
st.markdown(
    "Tableau de bord connecté en direct à votre station Ecowitt"
    " (GW3000) à Habère-Poche (900 m d'altitude)."
)


@st.cache_data(ttl=10)
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
    st.warning("Aucune donnée pour l'instant.")
else:
    # Application des offsets de correction sur l'ensemble du DataFrame pour les graphiques et calculs
    df["temp_c"] = round(df["temp_c"] + offset_temp, 1)
    df["humidity"] = np.clip(df["humidity"] + offset_hum, 0, 100)

    derniere_mesure = df.iloc[0]
    dir_deg = derniere_mesure['wind_direction']
    dir_card = derniere_mesure['cardinal']
    df_sorted = df.sort_values("date_time")

    current_time = derniere_mesure['date_time']
    target_1h = current_time - timedelta(hours=1)
    df_temp_1h = df_sorted.copy()
    df_temp_1h['diff_1h'] = (df_temp_1h['date_time'] - target_1h).abs()
    row_1h = df_temp_1h.loc[df_temp_1h['diff_1h'].idxmin()] if not df_temp_1h.empty else None

    delta_temp = round(derniere_mesure['temp_c'] - row_1h['temp_c'], 1) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0.0
    delta_hum = int(derniere_mesure['humidity'] - row_1h['humidity']) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0
    delta_press = round(derniere_mesure['pressure'] - row_1h['pressure'], 1) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0.0

    df_24h = df_sorted[df_sorted['date_time'] >= (current_time - timedelta(hours=24))]
    if df_24h.empty:
        df_24h = df_sorted

    max_gust_row = df_24h.loc[df_24h['wind_gust'].idxmax()]
    max_wind_row = df_24h.loc[df_24h['wind_speed'].idxmax()]
    dew_point = calculer_point_rosee(derniere_mesure['temp_c'], derniere_mesure['humidity'])
    pluie_24h_glissante = round(df_24h['rain_day'].max() - df_24h['rain_day'].min(), 1) if not df_24h.empty else derniere_mesure['rain_day']

    lune_phase, lune_icone, lune_age, lune_illum = calculer_phase_lune(current_time)
    uv_actuel = int(derniere_mesure['uv'])
    uv_niveau, uv_conseil_txt, uv_recos = analyser_indice_uv(uv_actuel)

    # --- Climatologie & Normales de référence (900m - Haute-Savoie) ---
    mois_actuel = current_time.month
    normales_ref = {
        1: -1.0, 2: 0.0, 3: 4.0, 4: 8.0, 5: 12.0, 6: 16.0,
        7: 18.0, 8: 17.5, 9: 13.0, 10: 8.5, 11: 3.0, 12: 0.0
    }
    normale_saison = normales_ref.get(mois_actuel, 15.0)

    df_mois_actuel = df_sorted[(df_sorted['date_time'].dt.year == current_time.year) & (df_sorted['date_time'].dt.month == mois_actuel)]
    if len(df_mois_actuel) > 10:
        moy_mois_station = round(df_mois_actuel['temp_c'].mean(), 1)
        Donnees_suffisantes = True
    else:
        moy_mois_station = derniere_mesure['temp_c']
        Donnees_suffisantes = False

    # --- Onglets ---
    tab_direct, tab_previ, tab_graph, tab_brutes = st.tabs([
        "📊 Direct & Synthèse",
        "🔮 Prévisions et analyses",
        "📈 Graphiques 7j",
        "📁 Données brutes"
    ])

    with tab_direct:
        st.subheader("Conditions en direct (Variations sur 1h)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Température", f"{derniere_mesure['temp_c']} °C", delta=f"{delta_temp:+.1f} °C /1h")
        with col2:
            st.metric("Humidité", f"{derniere_mesure['humidity']} %", delta=f"{delta_hum:+d} % /1h")
        with col3:
            st.metric("Pression", f"{derniere_mesure['pressure']} hPa", delta=f"{delta_press:+.1f} hPa /1h")
        with col4:
            st.metric("Pluie du jour", f"{derniere_mesure['rain_day']} mm")

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("Vent moyen", f"{derniere_mesure['wind_speed']} km/h", delta=f"Max {max_wind_row['wind_speed']} à {max_wind_row['date_time'].strftime('%H:%M')}")
        with col6:
            st.metric("Direction du vent", f"{dir_card} ({dir_deg}°)")
        with col7:
            st.metric("Rafale max (24h)", f"{max_gust_row['wind_gust']} km/h", delta=f"À {max_gust_row['date_time'].strftime('%H:%M')}")
        with col8:
            st.metric("Point de rosée", f"{dew_point} °C")

        # --- Bloc Solaire et UV avec Recommandations ---
        col_u1, col_u2, col_u3, col_u4 = st.columns(4)
        with col_u1:
            st.metric("Indice UV (UVI)", uv_actuel, delta=uv_niveau)
        with col_u2:
            st.metric("Rayonnement Solaire", f"{derniere_mesure['solar_radiation']} W/m²")
        with col_u3:
            st.empty()
        with col_u4:
            st.empty()

        if uv_actuel >= 3:
            recos_str = " • ".join([f"**{r}**" for r in uv_recos])
            if uv_actuel >= 6:
                st.warning(f"⚠️ **Protection Solaire Requise (Altitude 900m) :** {uv_conseil_txt}\n\nRecommandé : {recos_str}")
            else:
                st.info(f"🕶️ **Prévention Solaire :** {uv_conseil_txt}\n\nPensez à : {recos_str}")

        st.subheader("🌧️ Bilans Pluviométriques & 🌙 Astronomie")
        col9, col10, col11, col12 = st.columns(4)
        with col9:
            st.metric("Pluie glissante (24h)", f"{pluie_24h_glissante} mm")
        with col10:
            st.metric("Pluie du mois", f"{derniere_mesure['rain_month']} mm")
        with col11:
            st.metric("Pluie de l'année", f"{derniere_mesure['rain_year']} mm")
        with col12:
            st.metric("Phase Lunaire", f"{lune_icone} {lune_phase}", delta=f"Illumination {lune_illum}%")

    with tab_previ:
        st.subheader("🔮 Prévision Météo Locale & Analyse de Masse d'Air (Habère-Poche)")

        target_3h = current_time - timedelta(hours=3)
        df_temp_3h = df_sorted.copy()
        df_temp_3h['diff_3h'] = (df_temp_3h['date_time'] - target_3h).abs()
        row_3h = df_temp_3h.loc[df_temp_3h['diff_3h'].idxmin()] if not df_temp_3h.empty else None
        delta_press_3h = round(derniere_mesure['pressure'] - row_3h['pressure'], 1) if row_3h is not None and row_3h['diff_3h'] <= timedelta(minutes=45) else delta_press * 3

        z_text, z_trend, risque_orage = prevision_zambretti_avancee(
            derniere_mesure['pressure'],
            delta_press_3h,
            current_time.month,
            dir_card,
            derniere_mesure['solar_radiation'],
            derniere_mesure['humidity'],
            derniere_mesure['temp_c']
        )

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown("### 🎯 Bulletin Prévisionnel Expert")
            if risque_orage or delta_press_3h <= -2.0:
                st.error(f"**Prévision (12-24h) :**\n\n### {z_text}")
            else:
                st.success(f"**Prévision (12-24h) :**\n\n### {z_text}")

            st.write(f"* **Tendance barométrique (3h) :** {z_trend} ({delta_press_3h:+.1f} hPa)")
            st.write(f"* **Flux dominant :** {dir_card} ({dir_deg}°)")

            # --- COMPARATIF CLIMATIQUE HYBRIDE ---
            st.markdown("### 📊 Comparatif Climatique (Normale 900m)")
            diff_normale = round(moy_mois_station - normale_saison, 1)

            if Donnees_suffisantes:
                st.write(f"* **Moyenne de votre station ce mois :** `{moy_mois_station} °C`")
            else:
                st.info("💡 Station trop récente : estimation basée sur la température actuelle en attendant l'historique complet du mois.")
                st.write(f"* **Température de référence / mesurée :** `{moy_mois_station} °C`")

            st.write(f"* **Normale saisonnière (900m) :** `{normale_saison} °C`")

            if diff_normale > 0.5:
                st.warning(f"🌡️ Ce mois est **plus chaud** que la normale de saison d'environ `+{diff_normale} °C`.")
            elif diff_normale < -0.5:
                st.info(f"❄️ Ce mois est **plus frais** que la normale de saison d'environ `{diff_normale} °C`.")
            else:
                st.success("✅ Les températures sont **dans les normales de saison**.")

            # --- ANALYSE VENT & RELIEF ---
            st.markdown("### 💨 Analyse du Flux & Effet de Site")
            if dir_card in ["NO", "ONO", "O"]:
                st.info(f"🏔️ **Flux de {dir_card} :** Entrées maritimes / blocage orographique fréquent à 900m. Risque d'accrochage nuageux et d'averses sur les reliefs.")
            elif dir_card in ["NE", "NNE", "E"]:
                st.info(f"❄️ **Flux de {dir_card} (Continental/Bise) :** Air souvent plus sec et frais. En hiver, conditions propices aux inversions thermiques ou au froid sec.")
            elif dir_card in ["SO", "SSO", "S"]:
                st.info(f"🌡️ **Flux de {dir_card} (Sud/Secteur chaud) :** Flux de sud généralement doux, précurseur de perturbations instables si la pression baisse.")
            else:
                st.write(f"Vent de secteur {dir_card}, flux modéré sur le site.")

            # --- ÉTAPE LUNAIRE / CALENDRIER PROCHES JOURS ---
            st.markdown("### 🌙 Évolution Lunaire (Prochains jours)")
            lune_cols = st.columns(5)
            for i, offset in enumerate(range(-2, 3)):
                futur_dt = current_time + timedelta(days=offset)
                f_phase, f_icone, _, f_illum = calculer_phase_lune(futur_dt)
                label_jour = "Aujourd'hui" if offset == 0 else futur_dt.strftime("%d/%m")
                with lune_cols[i]:
                    st.markdown(f"""
                        <div style='text-align: center; background: rgba(255,255,255,0.05); padding: 8px; border-radius: 8px;'>
                            <b style='font-size: 0.85em;'>{label_jour}</b><br>
                            <span style='font-size: 28px; line-height: 1.2;'>{f_icone}</span><br>
                            <small style='color: #a0a0a0;'>{f_illum}%</small>
                        </div>
                    """, unsafe_allow_html=True)

            # --- ALERTES AUTOMATIQUES ---
            st.markdown("### ⚠️ Veille et Vigilance Locale")

            alerte_active = False
            cart_temp_dew = round(derniere_mesure['temp_c'] - dew_point, 1)

            if derniere_mesure['temp_c'] <= 2.5 and derniere_mesure.get('rain_rate', 0) > 0:
                st.error(f"🌨️ **ALERTE NEIGE / FLOCONS :** Température de {derniere_mesure['temp_c']}°C avec précipitations en cours ({derniere_mesure['rain_rate']} mm/h). Risque de neige ou de transition pluie-neige à 900m !")
                alerte_active = True
            elif derniere_mesure['temp_c'] <= 2.0:
                st.error(f"❄️ **ALERTE GEL :** Température basse ({derniere_mesure['temp_c']}°C). Risque de gel sensible au sol ou sous abri à 900m.")
                alerte_active = True

            if cart_temp_dew < 1.5 and derniere_mesure['humidity'] > 88:
                st.warning(f"🌫️ **ALERTE BROUILLARD / NUAGES BAS :** Écart critique air/rosée ({cart_temp_dew}°C) avec forte humidité ({derniere_mesure['humidity']}%). Visibilité réduite sur les hauteurs.")
                alerte_active = True
            else:
                st.write(f"✨ **Masse d'air :** Écart température/rosée sain ({cart_temp_dew}°C). Pas de saturation imminente.")

            if derniere_mesure['wind_gust'] >= 50:
                st.error(f"💨 **ALERTE VENT FORT :** Rafales mesurées à {derniere_mesure['wind_gust']} km/h. Prudence en extérieur.")
                alerte_active = True

            if risque_orage and not alerte_active:
                st.warning("⚡ **Alerte Convective :** Conditions réunies pour un développement orageux diurne sur le relief.")

        with col_p2:
            st.markdown("### 🧭 Rose des Vents (7 derniers jours)")
            if plotly_disponible and not df_sorted.empty:
                bins = [0, 5, 10, 15, 20, 50]
                labels = ['0-5 km/h', '5-10 km/h', '10-15 km/h', '15-20 km/h', '> 20 km/h']
                df_sorted['vitesse_tranche'] = pd.cut(df_sorted['wind_speed'], bins=bins, labels=labels, right=False)
                sector_width = 22.5
                df_sorted['dir_sector'] = (np.floor((df_sorted['wind_direction'] + sector_width / 2) / sector_width) * sector_width) % 360
                rose_df = df_sorted.groupby(['dir_sector', 'vitesse_tranche'], observed=False).size().reset_index(name='count')

                fig = px.bar_polar(
                    rose_df, r='count', theta='dir_sector', color='vitesse_tranche',
                    color_discrete_sequence=px.colors.sequential.Plasma_r, template="plotly_dark"
                )
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=10, r=10, t=10, b=10),
                    polar=dict(
                        bgcolor='rgba(0,0,0,0)',
                        radialaxis=dict(showticklabels=False, ticks='', gridcolor='#444444'),
                        angularaxis=dict(
                            direction="clockwise", rotation=90,
                            tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                            ticktext=['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'],
                            gridcolor='#444444'
                        )
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Plotly non disponible.")

    with tab_graph:
        st.subheader("📈 Évolutions temporelles détaillées (7 derniers jours)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Température (°C)")
            st.line_chart(df_sorted.set_index("date_time")["temp_c"])
        with c2:
            st.markdown("### Pression (hPa)")
            if plotly_disponible:
                fig_p = px.line(df_sorted, x="date_time", y="pressure", template="plotly_dark")
                fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.line_chart(df_sorted.set_index("date_time")["pressure"])

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### Vent (km/h & Rafales)")
            st.line_chart(df_sorted.set_index("date_time")[["wind_speed", "wind_gust"]])
        with c4:
            st.markdown("### Rayonnement Solaire & UV")
            st.line_chart(df_sorted.set_index("date_time")[["solar_radiation", "uv"]])

    with tab_brutes:
        st.subheader("📁 Historique complet des mesures")
        st.dataframe(df, use_container_width=True)

 


        
 
