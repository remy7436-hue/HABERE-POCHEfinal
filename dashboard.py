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
    JD = int(365.25 * (year + 4716)) + int(30.
