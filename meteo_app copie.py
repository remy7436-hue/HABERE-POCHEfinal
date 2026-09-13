import csv
from datetime import datetime, timedelta
import math
import os
import random
import re
import sys

try:
  from PyQt5.QtCore import Qt, QTimer
  from PyQt5.QtWidgets import (
      QApplication,
      QFileDialog,
      QFrame,
      QGridLayout,
      QHBoxLayout,
      QHeaderView,
      QLabel,
      QMainWindow,
      QMessageBox,
      QPushButton,
      QTableWidget,
      QTableWidgetItem,
      QTabWidget,
      QVBoxLayout,
      QWidget,
  )

  PYQT_VERSION = 5
except ImportError:
  from PyQt6.QtCore import Qt, QTimer
  from PyQt6.QtWidgets import (
      QApplication,
      QFileDialog,
      QFrame,
      QGridLayout,
      QHBoxLayout,
      QHeaderView,
      QLabel,
      QMainWindow,
      QMessageBox,
      QPushButton,
      QTableWidget,
      QTableWidgetItem,
      QTabWidget,
      QVBoxLayout,
      QWidget,
  )

  PYQT_VERSION = 6

import matplotlib

if PYQT_VERSION == 5:
  matplotlib.use('Qt5Agg')
  from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
else:
  matplotlib.use('Qt6Agg')
  from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

import matplotlib.dates as mdates
from matplotlib.figure import Figure

CSV_FILE = 'meteo_historique.csv'


class MplCanvasGlobal(FigureCanvas):

  def __init__(self, parent=None, width=5, height=9, dpi=100):
    self.fig = Figure(figsize=(width, height), dpi=dpi)
    self.ax_temp = self.fig.add_subplot(511)
    self.ax_pres = self.fig.add_subplot(512)
    self.ax_pluie = self.fig.add_subplot(513)
    self.ax_hum = self.fig.add_subplot(514)
    self.ax_vent = self.fig.add_subplot(515)
    super().__init__(self.fig)


class MplCanvasLive(FigureCanvas):

  def __init__(self, parent=None, width=5, height=8, dpi=100):
    self.fig = Figure(figsize=(width, height), dpi=dpi)
    self.ax_temp = self.fig.add_subplot(711)
    self.ax_hum = self.fig.add_subplot(712)
    self.ax_pres = self.fig.add_subplot(713)
    self.ax_vent = self.fig.add_subplot(714)
    self.ax_solaire = self.fig.add_subplot(715)
    self.ax_uv = self.fig.add_subplot(716)
    self.ax_pluie = self.fig.add_subplot(717)
    super().__init__(self.fig)


class MplCanvasCSV(FigureCanvas):

  def __init__(self, parent=None, width=5, height=6, dpi=100):
    self.fig = Figure(figsize=(width, height), dpi=dpi)
    self.ax_temp = self.fig.add_subplot(311)
    self.ax_pres = self.fig.add_subplot(312)
    self.ax_pluie = self.fig.add_subplot(313)
    super().__init__(self.fig)


class MplCanvasVent(FigureCanvas):

  def __init__(self, parent=None, width=5, height=6, dpi=100):
    self.fig = Figure(figsize=(width, height), dpi=dpi)
    self.ax = self.fig.add_subplot(111, projection='polar')
    super().__init__(self.fig)


class MplCanvasPrev(FigureCanvas):

  def __init__(self, parent=None, width=5, height=4, dpi=100):
    self.fig = Figure(figsize=(width, height), dpi=dpi)
    self.ax_temp = self.fig.add_subplot(211)
    self.ax_pres = self.fig.add_subplot(212)
    super().__init__(self.fig)


class MeteoApp(QMainWindow):

  def __init__(self):
    super().__init__()
    self.setWindowTitle('Tableau de Bord Météo - Habère-Poche (900m)')
    self.setGeometry(100, 100, 1300, 1050)

    font = self.font()
    font.setPointSize(11)
    self.setFont(font)

    self.initialiser_csv_global()
    self.combler_trous_au_demarrage()

    self.central_widget = QWidget()
    self.setCentralWidget(self.central_widget)
    main_layout = QVBoxLayout(self.central_widget)

    top_layout = QHBoxLayout()
    self.btn_importer = QPushButton('📁 Importer un fichier CSV d\'archives')
    self.btn_importer.setStyleSheet(
        'font-size: 11pt; font-weight: bold; padding: 6px;'
    )
    self.btn_importer.clicked.connect(self.importer_csv_externe)
    top_layout.addWidget(self.btn_importer)
    main_layout.addLayout(top_layout)

    self.tabs = QTabWidget()
    self.tabs.setStyleSheet("""
            QTabBar::tab {
                font-size: 10pt;
                font-weight: bold;
                padding: 8px 10px;
                min-width: 110px;
            }
        """)
    main_layout.addWidget(self.tabs)

    # Onglet 1 : Historique
    self.tab_global = QWidget()
    global_layout = QVBoxLayout(self.tab_global)
    self.canvas_global = MplCanvasGlobal(self, width=5, height=9, dpi=100)
    global_layout.addWidget(self.canvas_global)
    self.tabs.addTab(self.tab_global, '📈 Historique')

    # Onglet 2 : Live
    self.tab_live = QWidget()
    live_layout = QVBoxLayout(self.tab_live)

    self.panel_synthese = QWidget()
    grid_synthese = QGridLayout(self.panel_synthese)
    grid_synthese.setContentsMargins(0, 0, 0, 0)

    self.lbl_card_temp = self.creer_tuile_meteo(
        '🌡️ Température', '-- °C', 'Ressenti: -- °C'
    )
    self.lbl_card_vent = self.creer_tuile_meteo(
        '💨 Vent & Rafales', '-- km/h', 'Direction: --'
    )
    self.lbl_card_pres = self.creer_tuile_meteo(
        '⏱️ Pression & Tendance 3h', '-- hPa', 'Stable'
    )
    self.lbl_card_hum = self.creer_tuile_meteo(
        '💧 Humidité & Rosée', '-- %', 'Rosée: -- °C'
    )
    self.lbl_card_pluie = self.creer_tuile_meteo(
        '🌧️ Précipitations', 'Débit: -- mm/h', 'Cumul: -- mm'
    )
    self.lbl_card_uv = self.creer_tuile_meteo(
        '☀️ Solaire & UV', 'Solaire: -- W/m²', 'Indice UV: --'
    )

    grid_synthese.addWidget(self.lbl_card_temp, 0, 0)
    grid_synthese.addWidget(self.lbl_card_vent, 0, 1)
    grid_synthese.addWidget(self.lbl_card_pres, 0, 2)
    grid_synthese.addWidget(self.lbl_card_hum, 1, 0)
    grid_synthese.addWidget(self.lbl_card_pluie, 1, 1)
    grid_synthese.addWidget(self.lbl_card_uv, 1, 2)

    live_layout.addWidget(self.panel_synthese)

    self.canvas_live = MplCanvasLive(self, width=5, height=7, dpi=100)
    live_layout.addWidget(self.canvas_live)

    self.label_conseils = QLabel(
        'Analyse des conditions en cours à Habère-Poche (900m)...'
    )
    self.label_conseils.setStyleSheet("""
            background-color: #2c3e50;
            color: #ecf0f1;
            padding: 12px;
            border-radius: 6px;
            font-size: 11pt;
            font-weight: bold;
        """)
    self.label_conseils.setWordWrap(True)
    live_layout.addWidget(self.label_conseils)

    self.tabs.addTab(self.tab_live, '⚡ Temps Réel')

    # Onglet 3 : Flux & Vent
    self.tab_vent = QWidget()
    vent_layout = QHBoxLayout(self.tab_vent)

    left_vent_layout = QVBoxLayout()
    lbl_titre_rose = QLabel(
        '🧭 Rose des Vents & Régimes de Pente (Habère-Poche - 900m)'
    )
    lbl_titre_rose.setStyleSheet(
        'font-size: 12pt; font-weight: bold; color: #2c3e50;'
    )
    left_vent_layout.addWidget(lbl_titre_rose)

    self.canvas_vent_rose = MplCanvasVent(self, width=5, height=6, dpi=100)
    left_vent_layout.addWidget(self.canvas_vent_rose)
    vent_layout.addLayout(left_vent_layout, 3)

    right_vent_layout = QVBoxLayout()
    lbl_titre_analyse = QLabel('🏔️ Interprétation Synoptique & Thermique')
    lbl_titre_analyse.setStyleSheet(
        'font-size: 12pt; font-weight: bold; color: #2c3e50;'
    )
    right_vent_layout.addWidget(lbl_titre_analyse)

    self.card_flux_actuel = self.creer_tuile_meteo(
        '🌬️ Flux & Brise Locale', 'Direction: --', 'Analyse dynamique'
    )
    self.card_foehn_analyse = self.creer_tuile_meteo(
        '⚠️ Analyse Foehn / Lombarde',
        'Surveillance en cours',
        "Indicateurs de masse d'air",
    )
    self.card_bise_analyse = self.creer_tuile_meteo(
        '❄️ Entrées Nord / Bise',
        'Analyse thermique',
        'Impact sur le relief et le potager',
    )

    right_vent_layout.addWidget(self.card_flux_actuel)
    right_vent_layout.addWidget(self.card_foehn_analyse)
    right_vent_layout.addWidget(self.card_bise_analyse)
    right_vent_layout.addStretch()

    vent_layout.addLayout(right_vent_layout, 2)
    self.tabs.addTab(self.tab_vent, '🧭 Flux & Vent')

    # Onglet 4 : Statistiques
    self.tab_stats = QWidget()
    stats_layout = QVBoxLayout(self.tab_stats)

    lbl_titre_stats = QLabel(
        '📊 Bilan Statistiques, GDD & Extrêmes (Habère-Poche - 900m)'
    )
    lbl_titre_stats.setStyleSheet(
        'font-size: 13pt; font-weight: bold; color: #2c3e50; margin-bottom:'
        ' 5px;'
    )
    stats_layout.addWidget(lbl_titre_stats)

    self.panel_stats_grid = QGridLayout()

    self.stat_t_min = self.creer_tuile_meteo(
        '🌡️ Température Min', '-- °C', 'Min historique'
    )
    self.stat_t_max = self.creer_tuile_meteo(
        '🌡️ Température Max', '-- °C', 'Max historique'
    )
    self.stat_rafales = self.creer_tuile_meteo(
        '💨 Rafale Max', '-- km/h', 'Max enregistré'
    )
    self.stat_pression = self.creer_tuile_meteo(
        '⏱️ Pression Moyenne', '-- hPa', 'Tendance globale'
    )
    self.stat_pluie_mois = self.creer_tuile_meteo(
        '🌧️ Cumul Pluie Total', '-- mm', 'Volume cumulé'
    )
    self.stat_solaire_max = self.creer_tuile_meteo(
        '☀️ Pic Solaire Max', '-- W/m²', 'Maximum observé'
    )
    self.stat_uv_moyen = self.creer_tuile_meteo(
        '🔆 Indice UV Max', '--', 'Max enregistré'
    )
    self.stat_gdd = self.creer_tuile_meteo(
        '🌱 Degrés-Jours (GDD)',
        '-- GDD',
        'Somme thermique potager (seuil 10°C)',
    )

    self.panel_stats_grid.addWidget(self.stat_t_min, 0, 0)
    self.panel_stats_grid.addWidget(self.stat_t_max, 0, 1)
    self.panel_stats_grid.addWidget(self.stat_rafales, 0, 2)
    self.panel_stats_grid.addWidget(self.stat_pression, 1, 0)
    self.panel_stats_grid.addWidget(self.stat_pluie_mois, 1, 1)
    self.panel_stats_grid.addWidget(self.stat_solaire_max, 1, 2)
    self.panel_stats_grid.addWidget(self.stat_uv_moyen, 2, 0)
    self.panel_stats_grid.addWidget(self.stat_gdd, 2, 1)

    stats_layout.addLayout(self.panel_stats_grid)
    stats_layout.addStretch()

    self.tabs.addTab(self.tab_stats, '📊 Statistiques')

    # Onglet 5 : Prévisions
    self.tab_previsions = QWidget()
    prev_layout = QVBoxLayout(self.tab_previsions)

    lbl_titre_prev = QLabel(
        '🔮 Bulletin Prévisionnel & Expertises Montagne (Habère-Poche - 900m)'
    )
    lbl_titre_prev.setStyleSheet(
        'font-size: 13pt; font-weight: bold; color: #2c3e50; margin-bottom:'
        ' 5px;'
    )
    prev_layout.addWidget(lbl_titre_prev)

    grid_alertes_prev = QGridLayout()
    self.card_gel_matinal = self.creer_tuile_meteo(
        '❄️ Risque Gel Matinal (Potager)',
        'Analyse en cours...',
        'Seuil critique courgettes/courges',
    )
    self.card_orage_pente = self.creer_tuile_meteo(
        '⚡ Alerte Orages de Pente',
        'Analyse convective...',
        "Risque d'instabilité locale & rosée",
    )
    self.card_jardin_avance = self.creer_tuile_meteo(
        '🌱 Stratégie Arrosage & ETP',
        'ETP : Calcul...',
        "Indice d'évapotranspiration à 900m",
    )

    grid_alertes_prev.addWidget(self.card_gel_matinal, 0, 0)
    grid_alertes_prev.addWidget(self.card_orage_pente, 0, 1)
    grid_alertes_prev.addWidget(self.card_jardin_avance, 0, 2)
    prev_layout.addLayout(grid_alertes_prev)

    lbl_sub_graph = QLabel(
        '📈 Tendance Prospective sur 48 Heures (Température & Pression)'
    )
    lbl_sub_graph.setStyleSheet(
        'font-size: 11pt; font-weight: bold; color: #34495e; margin-top: 5px;'
    )
    prev_layout.addWidget(lbl_sub_graph)

    self.canvas_prev = MplCanvasPrev(self, width=5, height=3.5, dpi=100)
    prev_layout.addWidget(self.canvas_prev)

    lbl_sub_prev = QLabel('📅 Prévisions à 4 Jours (Moyenne Montagne)')
    lbl_sub_prev.setStyleSheet(
        'font-size: 11pt; font-weight: bold; color: #34495e; margin-top: 5px;'
    )
    prev_layout.addWidget(lbl_sub_prev)

    self.table_previsions = QTableWidget()
    self.table_previsions.setColumnCount(4)
    self.table_previsions.setHorizontalHeaderLabels([
        'Jour',
        'Temps dominant',
        'Températures (Min / Max)',
        'Risque de pluie',
    ])
    self.table_previsions.setStyleSheet('font-size: 10pt;')

    header = self.table_previsions.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.Stretch)

    self.table_previsions.setFixedHeight(140)
    prev_layout.addWidget(self.table_previsions)

    self.tabs.addTab(self.tab_previsions, '🔮 Prévisions')

    # Onglet 6 : Archives CSV
    self.tab_csv = QWidget()
    csv_layout = QVBoxLayout(self.tab_csv)
    self.canvas_csv = MplCanvasCSV(self, width=5, height=6, dpi=100)
    csv_layout.addWidget(self.canvas_csv)

    self.table_csv = QTableWidget()
    self.table_csv.setStyleSheet('font-size: 10pt;')
    csv_layout.addWidget(self.table_csv)

    self.tabs.addTab(self.tab_csv, '📂 Archives CSV')

    self.dernier_csv_lignes = []

    self.mettre_a_jour_graphiques_principaux()
    self.mettre_a_jour_previsions()

    self.timer = QTimer()
    self.timer.timeout.connect(self.ajouter_point_automatique)
    self.timer.start(30000)

  def creer_tuile_meteo(self, titre, val_principale, val_secondaire):
    frame = QFrame()
    frame.setStyleSheet("""
            QFrame {
                background-color: #34495e;
                border-radius: 8px;
                padding: 10px;
            }
        """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)

    lbl_titre = QLabel(titre)
    lbl_titre.setStyleSheet(
        'color: #bdc3c7; font-size: 10.5pt; font-weight: bold;'
    )

    lbl_val1 = QLabel(val_principale)
    lbl_val1.setStyleSheet('color: #ffffff; font-size: 14pt; font-weight: bold;')

    lbl_val2 = QLabel(val_secondaire)
    lbl_val2.setStyleSheet('color: #ecf0f1; font-size: 9.5pt;')

    layout.addWidget(lbl_titre)
    layout.addWidget(lbl_val1)
    layout.addWidget(lbl_val2)
    return frame

  def convertir_degres_en_texte(self, deg):
    try:
      d = float(deg)
    except (ValueError, TypeError):
      return 'N/A'
    directions = [
        'N',
        'NNE',
        'NE',
        'ENE',
        'E',
        'ESE',
        'SE',
        'SSE',
        'S',
        'SSW',
        'SW',
        'WSW',
        'W',
        'WNW',
        'NW',
        'NNW',
    ]
    index = int((d + 11.25) / 22.5) % 16
    return directions[index]

  def parser_date_flexible(self, date_str):
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%d/%m/%Y %H:%M',
        '%Y-%m-%d',
        '%d/%m/%Y',
    ]
    for fmt in formats:
      try:
        return datetime.strptime(date_str.strip(), fmt)
      except ValueError:
        continue
    return None

  def initialiser_csv_global(self):
    if not os.path.exists(CSV_FILE):
      with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Heure',
            'Temperature',
            'Humidite',
            'Pression',
            'Vent',
            'Rafales',
            'Solaire',
            'UV',
            'Pluie',
            'Direction',
        ])

  def combler_trous_au_demarrage(self):
    if not os.path.exists(CSV_FILE):
      return

    lignes = []
    with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
      reader = csv.reader(f)
      lignes = list(reader)

    if len(lignes) <= 1:
      return

    derniere_ligne = lignes[-1]
    str_derniere_heure = derniere_ligne[0]

    dt_dernier = self.parser_date_flexible(str_derniere_heure)
    if not dt_dernier:
      return

    dt_actuel = datetime.now()
    ecart_secondes = (dt_actuel - dt_dernier).total_seconds()

    if ecart_secondes > 30:
      if ecart_secondes > 86400:
        dt_dernier = dt_actuel - timedelta(days=1)

      nouveaux_points = []
      courant = dt_dernier + timedelta(seconds=30)

      try:
        t_courant = float(derniere_ligne[1])
        h_courant = float(derniere_ligne[2])
        p_courant = float(derniere_ligne[3])
        dir_courant = (
            float(derniere_ligne[9]) if len(derniere_ligne) > 9 else 180.0
        )
      except (ValueError, IndexError):
        t_courant, h_courant, p_courant, dir_courant = (
            20.0,
            50.0,
            1013.0,
            180.0,
        )

      while courant < dt_actuel:
        t_courant = round(
            max(-10.0, min(40.0, t_courant + random.uniform(-0.2, 0.2))), 1
        )
        h_courant = round(
            max(10.0, min(100.0, h_courant + random.uniform(-0.5, 0.5))), 1
        )
        p_courant = round(
            max(900.0, min(1050.0, p_courant + random.uniform(-0.1, 0.1))), 1
        )
        v_val = round(8.0 + random.uniform(0, 3), 1)
        r_val = round(v_val * 1.4, 1)
        dir_courant = round((dir_courant + random.uniform(-25, 25)) % 360, 1)

        heure_dec = courant.hour + courant.minute / 60.0
        if 6.0 <= heure_dec <= 21.0:
          angle = math.pi * (heure_dec - 6.0) / 15.0
          s_val = round(
              max(0.0, 85.0 * math.sin(angle) + random.uniform(-5, 5)), 1
          )
          uv_val = round(
              max(0.0, 2.0 * math.sin(angle) + random.uniform(-0.1, 0.1)), 1
          )
        else:
          s_val = 0.0
          uv_val = 0.0

        pl_val = 0.0
        nouveaux_points.append([
            courant.strftime('%Y-%m-%d %H:%M:%S'),
            t_courant,
            h_courant,
            p_courant,
            v_val,
            r_val,
            s_val,
            uv_val,
            pl_val,
            dir_courant,
        ])
        courant += timedelta(seconds=30)

      if nouveaux_points:
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
          writer = csv.writer(f)
          writer.writerows(nouveaux_points)

  def nettoyer_texte(self, texte):
    if not texte:
      return ''
    return re.sub(r'[\x00]', '', str(texte)).strip()

  def chercher_valeur(self, row, cles_possibles, valeur_defaut='0'):
    row_clean = {}
    for k, v in row.items():
      if k:
        k_clean = re.sub(r'[\x00]', '', str(k)).lower().strip()
        row_clean[k_clean] = v

    for cle in cles_possibles:
      cle_clean = cle.lower().strip()
      if (
          cle_clean in row_clean
          and row_clean[cle_clean] is not None
          and str(row_clean[cle_clean]).strip() != ''
      ):
        return str(row_clean[cle_clean]).strip()

    for k, v in row_clean.items():
      for cle in cles_possibles:
        if cle.lower() in k and v is not None and str(v).strip() != '':
          return str(v).strip()
    return valeur_defaut

  def importer_csv_externe(self):
    file_path, _ = QFileDialog.getOpenFileName(
        self,
        'Sélectionner un fichier CSV',
        '',
        'Fichiers CSV (*.csv);;Tous les fichiers (*)',
    )
    if not file_path:
      return

    lignes_actuelles = []
    for enc in ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-8', 'latin-1', 'cp1252']:
      try:
        with open(file_path, mode='r', encoding=enc, errors='ignore') as f:
          sample = f.read(2048)
          f.seek(0)
          delimiter = ';' if sample.count(';') > sample.count(',') else ','

          reader = csv.DictReader(f, delimiter=delimiter)

          for row in reader:
            if not row:
              continue

            h = self.chercher_valeur(
                row, ['Date', 'Heure', 'Timestamp', 'Time', 'Jour'], ''
            )
            t = self.chercher_valeur(
                row,
                ['Température (°C)', 'Temperature', 'Temp', 'Ext_Temp', 'T_ext'],
                '0',
            )
            hu = self.chercher_valeur(
                row,
                ['Humidité (%)', 'Humidite', 'Hum', 'Humidity', 'H_ext'],
                '0',
            )
            p = self.chercher_valeur(
                row,
                [
                    'Pression atmosphérique (hPa)',
                    'Pression',
                    'Pres',
                    'Baro',
                    'Pressure',
                ],
                '1013',
            )
            v = self.chercher_valeur(
                row,
                [
                    'Vitesse moyenne du vent (km/h)',
                    'Vent',
                    'Wind',
                    'WindSpeed',
                ],
                '0',
            )
            r = self.chercher_valeur(
                row,
                [
                    'Rafale maximale de vent (km/h)',
                    'Rafales',
                    'Rafale',
                    'Gust',
                    'WindGust',
                ],
                v,
            )
            s = self.chercher_valeur(
                row, ['Solaire', 'Solar', 'Radiation', 'Lux', 'Rayonnement'], '0'
            )
            uv = self.chercher_valeur(
                row, ['Indice UV', 'UV', 'Ultraviolet'], '0'
            )
            pl = self.chercher_valeur(
                row, ['Pluie (mm)', 'Pluie', 'Rain', 'Precipitation', 'Precip'],
                '0',
            )
            dir_v = self.chercher_valeur(
                row, ['Direction du vent (°)', 'Direction', 'WindDir', 'Dir'],
                '180',
            )

            h_clean = self.nettoyer_texte(h)
            if not h_clean:
              h_clean = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            lignes_actuelles.append({
                'Heure': h_clean,
                'Temperature': self.nettoyer_texte(t).replace(',', '.'),
                'Humidite': self.nettoyer_texte(hu).replace(',', '.'),
                'Pression': self.nettoyer_texte(p).replace(',', '.'),
                'Vent': self.nettoyer_texte(v).replace(',', '.'),
                'Rafales': self.nettoyer_texte(r).replace(',', '.'),
                'Solaire': self.nettoyer_texte(s).replace(',', '.'),
                'UV': self.nettoyer_texte(uv).replace(',', '.'),
                'Pluie': self.nettoyer_texte(pl).replace(',', '.'),
                'Direction': self.nettoyer_texte(dir_v).replace(',', '.'),
            })
        if lignes_actuelles:
          break
      except Exception:
        continue

    if lignes_actuelles:
      self.dernier_csv_lignes = lignes_actuelles
      self.mettre_a_jour_graphique_csv()
      self.remplir_tableau_csv()
      QMessageBox.information(
          self,
          'Importation réussie',
          f'{len(lignes_actuelles)} lignes chargées avec succès.',
      )
    else:
      QMessageBox.warning(
          self,
          "Erreur d'import",
          'Impossible de lire ce fichier CSV ou format non reconnu.',
      )

  def ajouter_point_automatique(self):
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    derniere_dir = 180.0
    if os.path.exists(CSV_FILE):
      with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        lignes = list(reader)
        if len(lignes) > 1:
          try:
            derniere_dir = float(lignes[-1][9])
          except (ValueError, IndexError):
            pass

    t_val = round(22.0 + random.uniform(-1.0, 1.0), 1)
    h_val = round(50.0 + random.uniform(-3, 3), 1)
    p_val = round(1016.0 + random.uniform(-2, 2), 1)
    v_val = round(8.0 + random.uniform(0, 3), 1)
    r_val = round(v_val * 1.4, 1)
    dir_val = round((derniere_dir + random.uniform(-20, 20)) % 360, 1)

    heure_dec = now.hour + now.minute / 60.0
    if 6.0 <= heure_dec <= 21.0:
      angle = math.pi * (heure_dec - 6.0) / 15.0
      s_val = round(
          max(0.0, 85.0 * math.sin(angle) + random.uniform(-5, 5)), 1
      )
      uv_val = round(
          max(0.0, 2.0 * math.sin(angle) + random.uniform(-0.1, 0.1)), 1
      )
    else:
      s_val = 0.0
      uv_val = 0.0

    pl_val = 0.0

    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
      writer = csv.writer(f)
      writer.writerow([
          now_str,
          t_val,
          h_val,
          p_val,
          v_val,
          r_val,
          s_val,
          uv_val,
          pl_val,
          dir_val,
      ])

    self.mettre_a_jour_graphiques_principaux()
    self.mettre_a_jour_previsions()

  def mettre_a_jour_graphiques_principaux(self):
    if not os.path.exists(CSV_FILE):
      return

    heures, temps, hums, pressions, vents, rafales, solaires, uvs, pluies, dirs = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )

    with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
      reader = csv.DictReader(f)
      for row in reader:
        dt = self.parser_date_flexible(row.get('Heure', ''))
        if dt:
          try:
            heures.append(dt)
            temps.append(float(row.get('Temperature', 0)))
            hums.append(float(row.get('Humidite', 0)))
            pressions.append(float(row.get('Pression', 0)))
            vents.append(float(row.get('Vent', 0)))
            rafales.append(float(row.get('Rafales', 0)))
            solaires.append(float(row.get('Solaire', 0)))
            uvs.append(float(row.get('UV', 0)))
            pluies.append(float(row.get('Pluie', 0)))
            dirs.append(float(row.get('Direction', 0)))
          except (ValueError, TypeError):
            continue

    if not heures:
      return

    dernier_t = temps[-1]
    dernier_h = hums[-1]
    dernier_p = pressions[-1]
    dernier_v = vents[-1]
    dernier_r = rafales[-1]
    dernier_s = solaires[-1]
    dernier_uv = uvs[-1]
    dernier_pl = pluies[-1]
    derniere_dir = dirs[-1]

    # Mise à jour onglet Live tuiles
    self.mettre_a_jour_tuiles(
        dernier_t,
        dernier_h,
        dernier_p,
        dernier_v,
        dernier_r,
        dernier_s,
        dernier_uv,
        dernier_pl,
        derniere_dir,
    )
    conseils = self.generer_conseils_intelligents(
        dernier_t,
        dernier_h,
        dernier_p,
        dernier_v,
        dernier_s,
        dernier_uv,
        dernier_pl,
    )
    self.label_conseils.setText(conseils)
    self.analyser_flux_vent_local(
        derniere_dir,
        dernier_v,
        dernier_h,
        dernier_t,
        dernier_p,
        heures[-1],
    )

    # 1. Graphique Global (5 subplots)
    c_g = self.canvas_global
    c_g.ax_temp.clear()
    c_g.ax_pres.clear()
    c_g.ax_pluie.clear()
    c_g.ax_hum.clear()
    c_g.ax_vent.clear()

    c_g.ax_temp.plot(heures, temps, color='#e74c3c', label='Température (°C)')
    c_g.ax_temp.set_ylabel('Temp (°C)')
    c_g.ax_temp.legend(loc='upper left')
    c_g.ax_temp.grid(True, linestyle='--', alpha=0.6)

    c_g.ax_pres.plot(
        heures, pressions, color='#3498db', label='Pression (hPa)'
    )
    c_g.ax_pres.set_ylabel('Pres (hPa)')
    c_g.ax_pres.legend(loc='upper left')
    c_g.ax_pres.grid(True, linestyle='--', alpha=0.6)

    c_g.ax_pluie.bar(
        heures, pluies, color='#2980b9', width=0.02, label='Pluie (mm)'
    )
    c_g.ax_pluie.set_ylabel('Pluie (mm)')
    c_g.ax_pluie.legend(loc='upper left')
    c_g.ax_pluie.grid(True, linestyle='--', alpha=0.6)

    c_g.ax_hum.plot(heures, hums, color='#1abc9c', label='Humidité (%)')
    c_g.ax_hum.set_ylabel('Hum (%)')
    c_g.ax_hum.legend(loc='upper left')
    c_g.ax_hum.grid(True, linestyle='--', alpha=0.6)

    c_g.ax_vent.plot(heures, vents, color='#95a5a6', label='Vent moyen (km/h)')
    c_g.ax_vent.plot(
        heures, rafales, color='#7f8c8d', linestyle='--', label='Rafales (km/h)'
    )
    c_g.ax_vent.set_ylabel('Vent (km/h)')
    c_g.ax_vent.legend(loc='upper left')
    c_g.ax_vent.grid(True, linestyle='--', alpha=0.6)
    c_g.ax_vent.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    c_g.fig.autofmt_xdate()
    c_g.fig.tight_layout()
    c_g.draw()

    # 2. Graphique Live (7 subplots)
    c_l = self.canvas_live
    for ax in [
        c_l.ax_temp,
        c_l.ax_hum,
        c_l.ax_pres,
        c_l.ax_vent,
        c_l.ax_solaire,
        c_l.ax_uv,
        c_l.ax_pluie,
    ]:
      ax.clear()

    c_l.ax_temp.plot(heures, temps, color='#e74c3c')
    c_l.ax_temp.set_ylabel('Temp')
    c_l.ax_temp.grid(True, alpha=0.4)

    c_l.ax_hum.plot(heures, hums, color='#1abc9c')
    c_l.ax_hum.set_ylabel('Hum')
    c_l.ax_hum.grid(True, alpha=0.4)

    c_l.ax_pres.plot(heures, pressions, color='#3498db')
    c_l.ax_pres.set_ylabel('Pres')
    c_l.ax_pres.grid(True, alpha=0.4)

    c_l.ax_vent.plot(heures, vents, color='#7f8c8d')
    c_l.ax_vent.set_ylabel('Vent')
    c_l.ax_vent.grid(True, alpha=0.4)

    c_l.ax_solaire.plot(heures, solaires, color='#f1c40f')
    c_l.ax_solaire.set_ylabel('Sol.')
    c_l.ax_solaire.grid(True, alpha=0.4)

    c_l.ax_uv.plot(heures, uvs, color='#e67e22')
    c_l.ax_uv.set_ylabel('UV')
    c_l.ax_uv.grid(True, alpha=0.4)

    c_l.ax_pluie.bar(heures, pluies, color='#2980b9', width=0.02)
    c_l.ax_pluie.set_ylabel('Pluie')
    c_l.ax_pluie.grid(True, alpha=0.4)

    c_l.ax_pluie.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    c_l.fig.autofmt_xdate()
    c_l.fig.tight_layout()
    c_l.draw()

    # 3. Rose des Vents (Onglet Vent)
    c_v = self.canvas_vent_rose
    c_v.ax.clear()
    c_v.ax.set_theta_zero_direction('N')
    c_v.ax.set_theta_zero_location('N')

    dirs_rad = [math.radians(d) for d in dirs]
    c_v.ax.scatter(dirs_rad, vents, c=vents, cmap='coolwarm', alpha=0.7, s=30)
    c_v.ax.set_title(
        'Direction & Vitesse des Flux (Habère-Poche)', va='bottom', fontsize=10
    )
    c_v.fig.tight_layout()
    c_v.draw()

    # 4. Statistiques globales
    if temps:
      self.mettre_a_jour_texte_tuile(
          self.stat_t_min, f'{min(temps)} °C', 'Min enregistré'
      )
      self.mettre_a_jour_texte_tuile(
          self.stat_t_max, f'{max(temps)} °C', 'Max enregistré'
      )
    if rafales:
      self.mettre_a_jour_texte_tuile(
          self.stat_rafales, f'{max(rafales)} km/h', 'Rafale maximale'
      )
    if pressions:
      self.mettre_a_jour_texte_tuile(
          self.stat_pression,
          f'{round(sum(pressions)/len(pressions), 1)} hPa',
          'Moyenne globale',
      )
    if pluies:
      self.mettre_a_jour_texte_tuile(
          self.stat_pluie_mois,
          f'{round(sum(pluies), 2)} mm',
          'Volume cumulé total',
      )
    if solaires:
      self.mettre_a_jour_texte_tuile(
          self.stat_solaire_max, f'{max(solaires)} W/m²', 'Pic maximum'
      )
    if uvs:
      self.mettre_a_jour_texte_tuile(
          self.stat_uv_moyen, f'{max(uvs)}', 'Indice UV Max'
      )

    # Calcul GDD potager (seuil 10°C)
    gdd_total = sum([max(0.0, (t - 10.0) / 24.0) for t in temps])
    self.mettre_a_jour_texte_tuile(
        self.stat_gdd,
        f'{round(gdd_total, 1)} GDD',
        'Somme thermique active (seuil 10°C)',
    )

  def generer_conseils_intelligents(self, t, h, p, v, s, uv, pl):
    conseils = []
    if t < 2.0:
      conseils.append(
          '❄️ Température fraîche en altitude : attention aux risques de gel'
          ' matinal pour les cultures sensibles.'
      )
    elif t > 25.0:
      conseils.append(
          '☀️ Chaleur notable à 900m : surveillez l\'arrosage des courgettes et'
          ' courges en fin de journée.'
      )
    else:
      conseils.append(
          '🌱 Température idéale pour la croissance potagère en zone de moyenne'
          ' montagne.'
      )

    if uv > 4:
      conseils.append(
          '⚠️ Indice UV significatif à 900m : protection solaire conseillée'
          ' pour vos travaux extérieurs.'
      )

    if pl > 0.5:
      conseils.append(
          '🌧️ Précipitations détectées : l\'arrosage naturel du jardin est pris'
          ' en charge.'
      )
    elif h < 40:
      conseils.append(
          '💧 Air sec détecté : atmosphère propice à l\'évapotranspiration,'
          ' surveillez l\'humidité des sols.'
      )

    if v > 30:
      conseils.append(
          '💨 Vent soutenu en rafales : sécurisez le matériel léger et les'
          ' abris de jardin.'
      )

    if p < 1005:
      conseils.append(
          '📉 Pression en baisse : risque d\'évolution instable ou passage'
          ' perturbé en vue.'
      )
    elif p > 1020:
      conseils.append(
          '📈 Haute pression stable : conditions calmes et dégagées durables.'
      )

    if not conseils:
      conseils.append('✨ Conditions stables et calmes sur le secteur.')

    return ' | '.join(conseils)

  def analyser_flux_vent_local(
      self, dir_deg, v_val, h_val, t_val, p_val, heure_actuelle
  ):
    txt_dir = self.convertir_degres_en_texte(dir_deg)

    is_jour = 6 <= heure_actuelle.hour <= 20
    if is_jour and (45 <= dir_deg <= 135):
      regime_pente = '☀️ Brise montante thermique (Vent de versant diurne)'
    elif not is_jour and (225 <= dir_deg <= 315):
      regime_pente = (
          '🌙 Brise descendante nocturne (Drainage d\'air frais des crêtes)'
      )
    else:
      regime_pente = '🌬️ Flux synoptique (Régime général de grande échelle)'

    desc_flux = (
        f'Flux de secteur {txt_dir} ({dir_deg}°) à {v_val} km/h.'
        f' {regime_pente}.'
    )

    if 135 <= dir_deg <= 225:
      if h_val < 45 and p_val < 1015:
        desc_foehn = (
            '🔥 Foehn / Lombarde actif : Air très sec et réchauffé par effet de'
            ' subsidence sur le relief.'
        )
      else:
        desc_foehn = (
            '↗️ Composante Sud prononcée : Effet de foehn modéré possible.'
        )
    else:
      desc_foehn = "✅ Pas d'indice de foehn majeur."

    if 315 <= dir_deg or dir_deg <= 45:
      if t_val < 10:
        desc_bise = (
            '❄️ Entrée froide / Bise marquée : Descente d\'air polaire ou'
            ' continental. Impact sensible au potager.'
        )
      else:
        desc_bise = "☁️ Flux de Nord : Air plus frais et assainissement de l'atmosphère."
    else:
      desc_bise = '✅ Absence de bise froide directe.'

    self.mettre_a_jour_texte_tuile(
        self.card_flux_actuel,
        desc_flux,
        f'Humidité: {h_val}% | Temp: {t_val}°C',
    )
    self.mettre_a_jour_texte_tuile(
        self.card_foehn_analyse, desc_foehn, 'Effet de versant & Lombarde'
    )
    self.mettre_a_jour_texte_tuile(
        self.card_bise_analyse, desc_bise, 'Régime thermique amont'
    )

  def mettre_a_jour_previsions(self):
    pressions_recentes = []
    dernier_t = 15.0
    dernier_h = 50.0
    dernier_p = 1013.0
    dernier_s = 0.0

    if os.path.exists(CSV_FILE):
      with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        lignes = list(reader)
        if lignes:
          try:
            dernier_t = float(lignes[-1].get('Temperature', 15))
            dernier_h = float(lignes[-1].get('Humidite', 50))
            dernier_p = float(lignes[-1].get('Pression', 1013))
            dernier_s = float(lignes[-1].get('Solaire', 0))
          except (ValueError, TypeError):
            pass
        for row in lignes:
          try:
            p = float(row.get('Pression', 0))
            if p > 100:
              pressions_recentes.append(p)
          except (ValueError, TypeError):
            pass

    t_nuit_estimee = dernier_t - 5.0
    if t_nuit_estimee <= 2.0:
      titre_gel = '⚠️ RISQUE DE GEL / FRAÎCHEUR'
      desc_gel = (
          f'Nuit estimée à ~{round(t_nuit_estimee, 1)}°C. Protection recommandée'
          ' pour courgettes et courges !'
      )
    else:
      titre_gel = '✅ Risque de gel : Faible'
      desc_gel = (
          f'Nuit estimée à ~{round(t_nuit_estimee, 1)}°C. Conditions'
          ' sécurisées pour le potager.'
      )
    self.mettre_a_jour_tuile(self.card_gel_matinal, titre_gel, desc_gel)

    delta_p_3h = 0.0
    if len(pressions_recentes) >= 360:
      delta_p_3h = pressions_recentes[-1] - pressions_recentes[-360]
    elif len(pressions_recentes) >= 120:
      delta_p_3h = pressions_recentes[-1] - pressions_recentes[-120]
    elif len(pressions_recentes) >= 12:
      delta_p_3h = pressions_recentes[-1] - pressions_recentes[-12]

    txt_tendance_3h = f'Tendance 3h : {round(delta_p_3h, 1)} hPa'
    if delta_p_3h < -1.5:
      txt_tendance_3h += ' (Baisse rapide ⚠️)'
    elif delta_p_3h > 1.5:
      txt_tendance_3h += ' (Hausse rapide 📈)'
    else:
      txt_tendance_3h += ' (Stable 🌤️)'
    self.mettre_a_jour_tuile(
        self.lbl_card_pres, f'{dernier_p} hPa', txt_tendance_3h
    )

    point_rosee = dernier_t - ((100 - dernier_h) / 5)
    if delta_p_3h < -1.5 and point_rosee > 12.0:
      titre_orage = "⚡ Risque d'Orages de Pente Élevé"
      desc_orage = (
          f'Chute barométrique 3h ({round(delta_p_3h, 1)} hPa) sous air lourd'
          f' (Rosée: {point_rosee}°C). Instabilité convective marquée.'
      )
    elif delta_p_3h < -0.8:
      titre_orage = '⚠️ Instabilité modérée'
      desc_orage = (
          f'Tendance 3h en baisse ({round(delta_p_3h, 1)} hPa). Surveillance'
          ' des crêtes.'
      )
    else:
      titre_orage = "☀️ Risque d'orage : Faible"
      desc_orage = (
          f'Tendance 3h stable ({round(delta_p_3h, 1)} hPa). Pas d\'alerte'
          ' convective.'
      )
    self.mettre_a_jour_tuile(self.card_orage_pente, titre_orage, desc_orage)

    etp_estime = round(
        max(0.1, (dernier_s / 200.0) + ((100 - dernier_h) / 30.0)), 1
    )
    if etp_estime > 3.0:
      titre_jardin = f'💧 ETP : {etp_estime} mm/j (Élevée)'
      desc_jardin = (
          'Forte demande évaporative (soleil/air sec) à 900m : arrosage des'
          ' courges requis.'
      )
    else:
      titre_jardin = f'🌱 ETP : {etp_estime} mm/j (Modérée)'
      desc_jardin = (
          'Humidité relative et ensoleillement équilibrés pour le potager'
          " d'altitude."
      )
    self.mettre_a_jour_tuile(
        self.card_jardin_avance, 'Stratégie Arrosage & Paillage', titre_jardin, desc_jardin
    )

    # Remplissage du tableau prévisionnel à 4 jours (exemple montagne)
    jours_prev = ["Aujourd'hui", 'Demain', 'Dans 2 jours', 'Dans 3 jours']
    temps_dom = [
        'Beau / Ensoleillé',
        'Nuageux / Risque orage',
        'Averses de pente',
        'Éclaircies durables',
    ]
    t_min_max = ['10°C / 22°C', '11°C / 20°C', '9°C / 18°C', '12°C / 23°C']
    risques_pluie = [
        'Faible (< 10%)',
        'Modéré (40%)',
        'Élevé (70%)',
        'Faible (< 20%)',
    ]

    self.table_previsions.setRowCount(4)
    for i in range(4):
      self.table_previsions.setItem(i, 0, QTableWidgetItem(jours_prev[i]))
      self.table_previsions.setItem(i, 1, QTableWidgetItem(temps_dom[i]))
      self.table_previsions.setItem(i, 2, QTableWidgetItem(t_min_max[i]))
      self.table_previsions.setItem(i, 3, QTableWidgetItem(risques_pluie[i]))

    # Tracé du graphique prévisionnel 48h
    c_p = self.canvas_prev
    c_p.ax_temp.clear()
    c_p.ax_pres.clear()

    heures_prev = [datetime.now() + timedelta(hours=i) for i in range(48)]
    temps_prev = [dernier_t + 3 * math.sin(i / 6.0) for i in range(48)]
    pres_prev = [dernier_p + 0.5 * math.cos(i / 10.0) for i in range(48)]

    c_p.ax_temp.plot(
        heures_prev, temps_prev, color='#e67e22', label='T° estimée (°C)'
    )
    c_p.ax_temp.set_ylabel('Temp (°C)')
    c_p.ax_temp.legend(loc='upper left')
    c_p.ax_temp.grid(True, linestyle='--', alpha=0.5)

    c_p.ax_pres.plot(
        heures_prev, pres_prev, color='#2980b9', label='Pression estimée (hPa)'
    )
    c_p.ax_pres.set_ylabel('Pres (hPa)')
    c_p.ax_pres.legend(loc='upper left')
    c_p.ax_pres.grid(True, linestyle='--', alpha=0.5)

    c_p.ax_pres.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
    c_p.fig.autofmt_xdate()
    c_p.fig.tight_layout()
    c_p.draw()

  def mettre_a_jour_texte_tuile(self, frame, val1, val2):
    labels = frame.findChildren(QLabel)
    if len(labels) >= 3:
      labels[1].setText(val1)
      labels[2].setText(val2)

  def mettre_a_jour_tuile(self, frame, titre, val1, val2):
    labels = frame.findChildren(QLabel)
    if len(labels) >= 3:
      labels[0].setText(titre)
      labels[1].setText(val1)
      labels[2].setText(val2)

  def mettre_a_jour_graphique_csv(self):
    if not self.dernier_csv_lignes:
      return
    c_csv = self.canvas_csv
    c_csv.ax_temp.clear()
    c_csv.ax_pres.clear()
    c_csv.ax_pluie.clear()

    heures, temps, pressions, pluies = [], [], [], []
    for row in self.dernier_csv_lignes:
      dt = self.parser_date_flexible(row.get('Heure', ''))
      if dt:
        try:
          heures.append(dt)
          temps.append(float(row.get('Temperature', 0)))
          pressions.append(float(row.get('Pression', 0)))
          pluies.append(float(row.get('Pluie', 0)))
        except (ValueError, TypeError):
          continue

    if not heures:
      return

    c_csv.ax_temp.plot(heures, temps, color='#d35400', label='CSV Temp')
    c_csv.ax_temp.set_ylabel('Temp')
    c_csv.ax_temp.grid(True, alpha=0.5)

    c_csv.ax_pres.plot(heures, pressions, color='#2980b9', label='CSV Pres')
    c_csv.ax_pres.set_ylabel('Pres')
    c_csv.ax_pres.grid(True, alpha=0.5)

    c_csv.ax_pluie.bar(heures, pluies, color='#16a085', width=0.02)
    c_csv.ax_pluie.set_ylabel('Pluie')
    c_csv.ax_pluie.grid(True, alpha=0.5)

    c_csv.ax_pluie.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M'))
    c_csv.fig.autofmt_xdate()
    c_csv.fig.tight_layout()
    c_csv.draw()

  def remplir_tableau_csv(self):
    if not self.dernier_csv_lignes:
      return
    self.table_csv.setRowCount(len(self.dernier_csv_lignes))
    headers = list(self.dernier_csv_lignes[0].keys())
    self.table_csv.setColumnCount(len(headers))
    self.table_csv.setHorizontalHeaderLabels(headers)

    for row_idx, row_data in enumerate(self.dernier_csv_lignes):
      for col_idx, key in enumerate(headers):
        val = str(row_data.get(key, ''))
        self.table_csv.setItem(row_idx, col_idx, QTableWidgetItem(val))


if __name__ == '__main__':
  app = QApplication(sys.argv)
  app.setStyle('Fusion')
  window = MeteoApp()
  window.show()
  sys.exit(app.exec_())
