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

WU_STATION_ID = "IHABRE19"
WU_API_KEY = "7783683bcac243da83683bcac213da8d"
DB_FILE = "meteo_historique.db"

st.set_page_config(
    page_title="Météo Habère-Poche", page_icon="🌤️", layout="wide"
)

st_autorefresh(interval=60000, key="meteo_autorefresh")


def degre_vers_cardinal(degre):
    if degre is None:
        return "N/A"
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"
    ]
    index = int((degre + 11.25) / 22.5) % 16
    return directions[index]


def calculer_point_rosee(temp_c, humidity):
    if humidity <= 0 or humidity > 100:
        return temp_c
    a = 17.27
    b = 237.7
    alpha = ((a * temp_c) / (b + temp_c)) + np.log(humidity / 100.0)
    dew_point = (b * alpha) / (a - alpha)
    return round(dew_point, 1)


def calculer_et0_simplifie(temp_c, wind_speed, humidity, solar_rad):
    temp_factor = max(0, temp_c + 5)
    wind_factor = 1 + (wind_speed / 15.0)
    humidity_factor = max(0.1, (100 - humidity) / 50.0)
    solar_factor = max(0.1, solar_rad / 300.0)
    et0 = round((temp_factor * wind_factor * humidity_factor * solar_factor) * 0.08, 2)
    return max(0.0, et0)


def analyser_indice_uv(uv):
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

    pluie_jour = derniere_mesure.get('rain_day', 0.0)
    df['date_dt'] = pd.to_datetime(df['date_time'])
    df_mois_en_cours = df[
        (df['date_dt'].dt.year == current_time.year) &
        (df['date_dt'].dt.month == current_time.month)
    ]

    PLUIE_BASE_MOIS = 66.0
    pluie_mois = round(PLUIE_BASE_MOIS + pluie_jour, 1)

    target_1h = current_time - timedelta(hours=1)
    df_temp_1h = df_sorted.copy()
    df_temp_1h['diff_1h'] = (df_temp_1h['date_time'] - target_1h).abs()
    row_1h = df_temp_1h.loc[df_temp_1h['diff_1h'].idxmin()] if not df_temp_1h.empty else None

    delta_temp = round(derniere_mesure['temp_c'] - row_1h['temp_c'], 1) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0.0
    delta_hum = int(derniere_mesure['humidity'] - row_1h['humidity']) if row_1h is not None and row_1h['diff_1h'] <= timedelta(minutes=20) else 0
    delta_press = round(derniere_mesure['pressure'] - row_1h['pressure'], 1) if row_1h is
