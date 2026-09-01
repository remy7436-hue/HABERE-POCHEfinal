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
    if is_summer and solar_rad > 500 and humidity > 50 and temp_c > 20 and
