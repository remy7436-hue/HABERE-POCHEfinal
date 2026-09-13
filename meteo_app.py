import sys
import os
import csv
from datetime import datetime, timedelta
import random
import re
import math

try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QPushButton, QFileDialog,
                                 QTabWidget, QMessageBox, QTableWidget, QTableWidgetItem, QLabel, QGridLayout, QFrame, QHeaderView)
    from PyQt5.QtCore import QTimer, Qt
    PYQT_VERSION = 5
except ImportError:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QPushButton, QFileDialog,
                                 QTabWidget, QMessageBox, QTableWidget, QTableWidgetItem, QLabel, QGridLayout, QHeaderView)
    from PyQt6.QtCore import QTimer, Qt
    PYQT_VERSION = 6

import matplotlib
if PYQT_VERSION == 5:
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
else:
    matplotlib.use('Qt6Agg')
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from matplotlib.figure import Figure
import matplotlib.dates as mdates

CSV_FILE = "meteo_historique.csv"

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
        self.setWindowTitle("Tableau de Bord Météo - Habère-Poche (900m)")
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
        self.btn_importer = QPushButton("📁 Importer un fichier CSV d'archives")
        self.btn_importer.clicked.connect(self.importer_csv_externe)
        top_layout.addWidget(self.btn_importer)
        main_layout.addLayout(top_layout)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.changer_onglet)
        main_layout.addWidget(self.tabs)

        # Onglet 0 : Historique
        self.tab_global = QWidget()
        global_layout = QVBoxLayout(self.tab_global)
        self.canvas_global = MplCanvasGlobal(self, width=5, height=9, dpi=100)
        global_layout.addWidget(self.canvas_global)
        self.tabs.addTab(self.tab_global, "📈 Historique")

        # Onglet 1 : Live
        self.tab_live = QWidget()
        live_layout = QVBoxLayout(self.tab_live)

        self.panel_synthese = QWidget()
        grid_synthese = QGridLayout(self.panel_synthese)
        grid_synthese.setContentsMargins(0, 0, 0, 0)

        self.lbl_card_temp = self.creer_tuile_meteo("🌡️ Température", "-- °C", "Ressenti: -- °C")
        self.lbl_card_vent = self.creer_tuile_meteo("💨 Vent & Rafales", "-- km/h", "Direction: --")
        self.lbl_card_pres = self.creer_tuile_meteo("⏱️ Pression", "-- hPa", "Stable")
        self.lbl_card_hum = self.creer_tuile_meteo("💧 Humidité & Rosée", "-- %", "Rosée: -- °C")
        self.lbl_card_pluie = self.creer_tuile_meteo("🌧️ Précipitations", "Intensité: -- mm/h", "Cumul: -- mm")
        self.lbl_card_uv = self.creer_tuile_meteo("☀️ Solaire & UV", "Solaire: -- W/m²", "Indice UV: --")

        grid_synthese.addWidget(self.lbl_card_temp, 0, 0)
        grid_synthese.addWidget(self.lbl_card_vent, 0, 1)
        grid_synthese.addWidget(self.lbl_card_pres, 0, 2)
        grid_synthese.addWidget(self.lbl_card_hum, 1, 0)
        grid_synthese.addWidget(self.lbl_card_pluie, 1, 1)
        grid_synthese.addWidget(self.lbl_card_uv, 1, 2)

        live_layout.addWidget(self.panel_synthese)

        self.canvas_live = MplCanvasLive(self, width=5, height=7, dpi=100)
        live_layout.addWidget(self.canvas_live)

        self.label_conseils = QLabel("Analyse des conditions en cours à Habère-Poche (900m)...")
        self.label_conseils.setWordWrap(True)
        live_layout.addWidget(self.label_conseils)

        self.tabs.addTab(self.tab_live, "⚡ Temps Réel")

        # Onglet 2 : Flux & Vent
        self.tab_vent = QWidget()
        vent_layout = QHBoxLayout(self.tab_vent)

        left_vent_layout = QVBoxLayout()
        lbl_titre_rose = QLabel("🧭 Rose des Vents & Fréquences (Habère-Poche - 900m)")
        left_vent_layout.addWidget(lbl_titre_rose)

        self.canvas_vent_rose = MplCanvasVent(self, width=5, height=6, dpi=100)
        left_vent_layout.addWidget(self.canvas_vent_rose)
        vent_layout.addLayout(left_vent_layout, 3)

        right_vent_layout = QVBoxLayout()
        lbl_titre_analyse = QLabel("🏔️ Interprétation Synoptique & Locale Avancée")
        right_vent_layout.addWidget(lbl_titre_analyse)

        self.card_flux_actuel = self.creer_tuile_meteo("🌬️ Flux Actuel", "Direction: --", "Vitesse & régime")
        self.card_foehn_analyse = self.creer_tuile_meteo("⚠️ Analyse Foehn / Lombarde", "Surveillance en cours", "Indicateurs de masse d'air")
        self.card_bise_analyse = self.creer_tuile_meteo("❄️ Entrées Nord / Bise", "Analyse thermique", "Impact sur le relief et le potager")

        right_vent_layout.addWidget(self.card_flux_actuel)
        right_vent_layout.addWidget(self.card_foehn_analyse)
        right_vent_layout.addWidget(self.card_bise_analyse)
        right_vent_layout.addStretch()

        vent_layout.addLayout(right_vent_layout, 2)
        self.tabs.addTab(self.tab_vent, "🧭 Flux & Vent")

        # Onglet 3 : Statistiques
        self.tab_stats = QWidget()
        stats_layout = QVBoxLayout(self.tab_stats)

        lbl_titre_stats = QLabel("📊 Bilan Statistiques & Extrêmes (Habère-Poche - 900m)")
        stats_layout.addWidget(lbl_titre_stats)

        self.panel_stats_grid = QGridLayout()

        self.stat_t_min = self.creer_tuile_meteo("🌡️ Température Min", "-- °C", "Min historique")
        self.stat_t_max = self.creer_tuile_meteo("🌡️ Température Max", "-- °C", "Max historique")
        self.stat_rafales = self.creer_tuile_meteo("💨 Rafale Max", "-- km/h", "Max enregistré")
        self.stat_pression = self.creer_tuile_meteo("⏱️ Pression Moyenne", "-- hPa", "Tendance globale")
        self.stat_pluie_mois = self.creer_tuile_meteo("🌧️ Cumul Pluie Total", "-- mm", "Volume cumulé")
        self.stat_solaire_max = self.creer_tuile_meteo("☀️ Pic Solaire Max", "-- W/m²", "Maximum observé")
        self.stat_uv_moyen = self.creer_tuile_meteo("🔆 Indice UV Max", "--", "Max enregistré")

        self.panel_stats_grid.addWidget(self.stat_t_min, 0, 0)
        self.panel_stats_grid.addWidget(self.stat_t_max, 0, 1)
        self.panel_stats_grid.addWidget(self.stat_rafales, 0, 2)
        self.panel_stats_grid.addWidget(self.stat_pression, 1, 0)
        self.panel_stats_grid.addWidget(self.stat_pluie_mois, 1, 1)
        self.panel_stats_grid.addWidget(self.stat_solaire_max, 1, 2)
        self.panel_stats_grid.addWidget(self.stat_uv_moyen, 2, 0)

        stats_layout.addLayout(self.panel_stats_grid)
        stats_layout.addStretch()

        self.tabs.addTab(self.tab_stats, "📊 Statistiques")

        # Onglet 4 : Prévisions
        self.tab_previsions = QWidget()
        prev_layout = QVBoxLayout(self.tab_previsions)

        lbl_titre_prev = QLabel("🔮 Bulletin Prévisionnel & Expertises Montagne (Habère-Poche - 900m)")
        prev_layout.addWidget(lbl_titre_prev)

        grid_alertes_prev = QGridLayout()
        self.card_gel_matinal = self.creer_tuile_meteo("❄️ Risque Gel Matinal (Potager)", "Analyse en cours...", "Seuil critique courgettes/courges")
        self.card_orage_pente = self.creer_tuile_meteo("⚡ Alerte Orages de Pente", "Analyse convective...", "Risque d'instabilité locale")
        self.card_jardin_avance = self.creer_tuile_meteo("🌱 Stratégie Arrosage & Paillage", "Calcul en cours...", "Besoin en eau à 900m")

        grid_alertes_prev.addWidget(self.card_gel_matinal, 0, 0)
        grid_alertes_prev.addWidget(self.card_orage_pente, 0, 1)
        grid_alertes_prev.addWidget(self.card_jardin_avance, 0, 2)
        prev_layout.addLayout(grid_alertes_prev)

        lbl_sub_graph = QLabel("📈 Tendance Prospective sur 48 Heures (Température & Pression)")
        prev_layout.addWidget(lbl_sub_graph)

        self.canvas_prev = MplCanvasPrev(self, width=5, height=3.5, dpi=100)
        prev_layout.addWidget(self.canvas_prev)

        lbl_sub_prev = QLabel("📅 Prévisions à 4 Jours (Moyenne Montagne)")
        prev_layout.addWidget(lbl_sub_prev)

        self.table_previsions = QTableWidget()
        self.table_previsions.setColumnCount(4)
        self.table_previsions.setHorizontalHeaderLabels(["Jour", "Temps dominant", "Températures (Min / Max)", "Risque de pluie"])

        header = self.table_previsions.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        self.table_previsions.setFixedHeight(140)
        prev_layout.addWidget(self.table_previsions)

        self.tabs.addTab(self.tab_previsions, "🔮 Prévisions")

        # Onglet 5 : Archives CSV
        self.tab_csv = QWidget()
        csv_layout = QVBoxLayout(self.tab_csv)
        self.canvas_csv = MplCanvasCSV(self, width=5, height=6, dpi=100)
        csv_layout.addWidget(self.canvas_csv)

        self.table_csv = QTableWidget()
        csv_layout.addWidget(self.table_csv)

        self.tabs.addTab(self.tab_csv, "📂 Archives CSV")

        self.dernier_csv_lignes = []

        self.tabs.setCurrentIndex(1)
        self.mettre_a_jour_temps_reel()

        self.timer = QTimer()
        self.timer.timeout.connect(self.ajouter_point_automatique)
        self.timer.start(30000)

    def charger_stylesheet(self, app):
        chemin_qss = "style.qss"
        if os.path.exists(chemin_qss):
            try:
                with open(chemin_qss, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
            except Exception as e:
                print(f"Erreur lors du chargement du style : {e}")

    def creer_tuile_meteo(self, titre, val_principale, val_secondaire):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl_titre = QLabel(titre)
        lbl_val1 = QLabel(val_principale)
        lbl_val2 = QLabel(val_secondaire)

        layout.addWidget(lbl_titre)
        layout.addWidget(lbl_val1)
        layout.addWidget(lbl_val2)
        return frame

    def convertir_degres_en_texte(self, deg):
        try:
            d = float(deg)
        except (ValueError, TypeError):
            return "N/A"
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = int((d + 11.25) / 22.5) % 16
        return directions[index]

    def parser_date_flexible(self, date_str):
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def mettre_a_jour_tuiles(self, t, h, p, v, r_raf, s, uv, pl, dir_deg=0):
        rosie = round(t - ((100 - h) / 5), 1)
        txt_dir = self.convertir_degres_en_texte(dir_deg)
        self.mettre_a_jour_texte_tuile(self.lbl_card_temp, f"{t} °C", f"Ressenti : {t} °C")
        self.mettre_a_jour_texte_tuile(self.lbl_card_vent, f"{v} km/h", f"Direction : {txt_dir} ({dir_deg}°)")
        self.mettre_a_jour_texte_tuile(self.lbl_card_pres, f"{p} hPa", "Habère-Poche (900m)")
        self.mettre_a_jour_texte_tuile(self.lbl_card_hum, f"{h} %", f"Point de rosée : {rosie} °C")
        self.mettre_a_jour_texte_tuile(self.lbl_card_pluie, f"Intensité: {pl} mm/h", f"Cumul : {pl} mm")
        self.mettre_a_jour_texte_tuile(self.lbl_card_uv, f"{s} W/m²", f"Indice UV : {uv}")

    def mettre_a_jour_texte_tuile(self, frame, val1, val2):
        labels = frame.findChildren(QLabel)
        if len(labels) >= 3:
            labels[1].setText(val1)
            labels[2].setText(val2)

    def initialiser_csv_global(self):
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Heure", "Temperature", "Humidite", "Pression", "Vent", "Rafales", "Solaire", "UV", "Pluie", "Direction"])

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
                dir_courant = float(derniere_ligne[9]) if len(derniere_ligne) > 9 else 180.0
            except (ValueError, IndexError):
                t_courant, h_courant, p_courant, dir_courant = 20.0, 50.0, 1013.0, 180.0

            while courant < dt_actuel:
                t_courant = round(max(-10.0, min(40.0, t_courant + random.uniform(-0.2, 0.2))), 1)
                h_courant = round(max(10.0, min(100.0, h_courant + random.uniform(-0.5, 0.5))), 1)
                p_courant = round(max(900.0, min(1050.0, p_courant + random.uniform(-0.1, 0.1))), 1)
                v_val = round(8.0 + random.uniform(0, 3), 1)
                r_val = round(v_val * 1.4, 1)
                dir_courant = round((dir_courant + random.uniform(-25, 25)) % 360, 1)

                heure_dec = courant.hour + courant.minute / 60.0
                if 6.0 <= heure_dec <= 21.0:
                    angle = math.pi * (heure_dec - 6.0) / 15.0
                    s_val = round(max(0.0, 85.0 * math.sin(angle) + random.uniform(-5, 5)), 1)
                    uv_val = round(max(0.0, 2.0 * math.sin(angle) + random.uniform(-0.1, 0.1)), 1)
                else:
                    s_val = 0.0
                    uv_val = 0.0

                # Génération augmentée pour s'assurer d'avoir de la pluie
                if random.random() < 0.4:
                    pl_val = round(random.uniform(0.5, 4.0), 1)
                else:
                    pl_val = 0.0

                nouveaux_points.append([courant.strftime("%Y-%m-%d %H:%M:%S"), t_courant, h_courant, p_courant, v_val, r_val, s_val, uv_val, pl_val, dir_courant])
                courant += timedelta(seconds=30)

            if nouveaux_points:
                with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(nouveaux_points)

    def nettoyer_texte(self, texte):
        if not texte:
            return ""
        return re.sub(r'[\x00]', '', str(texte)).strip()

    def chercher_valeur(self, row, cles_possibles, valeur_defaut="0"):
        row_clean = {}
        for k, v in row.items():
            if k:
                k_clean = re.sub(r'[\x00]', '', str(k)).lower().strip()
                row_clean[k_clean] = v

        for cle in cles_possibles:
            cle_clean = cle.lower().strip()
            if cle_clean in row_clean and row_clean[cle_clean] is not None and str(row_clean[cle_clean]).strip() != "":
                return str(row_clean[cle_clean]).strip()

        for k, v in row_clean.items():
            for cle in cles_possibles:
                if cle.lower() in k and v is not None and str(v).strip() != "":
                    return str(v).strip()
        return valeur_defaut

    def importer_csv_externe(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier CSV", "", "Fichiers CSV (*.csv);;Tous le fichiers (*)")
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

                        h = self.chercher_valeur(row, ["Date", "Heure", "Timestamp", "Time", "Jour"], "")
                        t = self.chercher_valeur(row, ["Température (°C)", "Temperature", "Temp", "Ext_Temp", "T_ext"], "0")
                        hu = self.chercher_valeur(row, ["Humidité (%)", "Humidite", "Hum", "Humidity", "H_ext"], "0")
                        p = self.chercher_valeur(row, ["Pression atmosphérique (hPa)", "Pression", "Pres", "Baro", "Pressure"], "1013")
                        v = self.chercher_valeur(row, ["Vitesse moyenne du vent (km/h)", "Vent", "Wind", "WindSpeed"], "0")
                        r = self.chercher_valeur(row, ["Rafale maximale de vent (km/h)", "Rafales", "Rafale", "Gust", "WindGust"], v)
                        s = self.chercher_valeur(row, ["Solaire", "Solar", "Radiation", "Lux", "Rayonnement"], "0")
                        uv = self.chercher_valeur(row, ["Indice UV", "UV", "Ultraviolet"], "0")
                        pl = self.chercher_valeur(row, ["Pluie (mm)", "Pluie", "Rain", "Precipitation", "Precip", "RR", "Rain_Rate", "Précipitations"], "0")
                        dir_v = self.chercher_valeur(row, ["Direction du vent (°)", "Direction", "WindDir", "Dir"], "180")

                        h_clean = self.nettoyer_texte(h)
                        if not h_clean:
                            h_clean = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        lignes_actuelles.append({
                            "Heure": h_clean,
                            "Temperature": self.nettoyer_texte(t).replace(',', '.'),
                            "Humidite": self.nettoyer_texte(hu).replace(',', '.'),
                            "Pression": self.nettoyer_texte(p).replace(',', '.'),
                            "Vent": self.nettoyer_texte(v).replace(',', '.'),
                            "Rafales": self.nettoyer_texte(r).replace(',', '.'),
                            "Solaire": self.nettoyer_texte(s).replace(',', '.'),
                            "UV": self.nettoyer_texte(uv).replace(',', '.'),
                            "Pluie": self.nettoyer_texte(pl).replace(',', '.'),
                            "Direction": self.nettoyer_texte(dir_v).replace(',', '.')
                        })
                if lignes_actuelles:
                    break
            except Exception:
                continue

        if lignes_actuelles:
            self.dernier_csv_lignes = lignes_actuelles
            if self.tabs.currentIndex() == 5:
                self.mettre_a_jour_graphique_csv()
                self.remplir_tableau_csv()
            QMessageBox.information(self, "Importation réussie", f"{len(lignes_actuelles)} lignes chargées avec succès.")
        else:
            QMessageBox.warning(self, "Erreur d'import", "Impossible de lire ce fichier CSV ou format non reconnu.")

    def ajouter_point_automatique(self):
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

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
            s_val = round(max(0.0, 85.0 * math.sin(angle) + random.uniform(-5, 5)), 1)
            uv_val = round(max(0.0, 2.0 * math.sin(angle) + random.uniform(-0.1, 0.1)), 1)
        else:
            s_val = 0.0
            uv_val = 0.0

        # Génération d'averse
        if random.random() < 0.4:
            pl_val = round(random.uniform(0.5, 3.0), 1)
        else:
            pl_val = 0.0

        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([now_str, t_val, h_val, p_val, v_val, r_val, s_val, uv_val, pl_val, dir_val])

        self.mettre_a_jour_onglet_actif()

    def changer_onglet(self, index):
        self.mettre_a_jour_onglet_actif()

    def mettre_a_jour_onglet_actif(self):
        index = self.tabs.currentIndex()
        if index == 0:
            self.mettre_a_jour_graphique_global()
        elif index == 1:
            self.mettre_a_jour_temps_reel()
        elif index == 2:
            self.mettre_a_jour_flux_vent()
        elif index == 3:
            self.mettre_a_jour_statistiques()
        elif index == 4:
            self.mettre_a_jour_previsions()
        elif index == 5:
            if self.dernier_csv_lignes:
                self.mettre_a_jour_graphique_csv()
                self.remplir_tableau_csv()

    def generer_conseils_intelligents(self, t, h, p, v, s, uv, pl):
        conseils = []
        if t < 2.0:
            conseils.append("❄️ Température fraîche en altitude : attention aux risques de gel matinal pour les cultures sensibles.")
        elif t > 25.0:
            conseils.append("☀️ Chaleur notable à 900m : surveillez l'arrosage des courgettes et courges en fin de journée.")
        else:
            conseils.append("🌱 Température idéale pour la croissance potagère en zone de moyenne montagne.")

        if uv > 4:
            conseils.append("⚠️ Indice UV significatif à 900m : protection solaire conseillée pour vos travaux extérieurs.")

        if pl > 0.0:
            conseils.append("🌧️ Précipitations détectées : l'arrosage naturel du jardin est pris en charge.")
        elif h < 40:
            conseils.append("💧 Air sec détecté : atmosphère propice à l'évapotranspiration, surveillez l'humidité des sols.")

        if v > 30:
            conseils.append("💨 Vent soutenu en rafales : sécurisez le matériel léger et les abris de jardin.")

        if p < 1005:
            conseils.append("📉 Pression en baisse : risque d'évolution instable ou passage perturbé en vue.")
        elif p > 1020:
            conseils.append("📈 Haute pression stable : conditions calmes et dégagées durables.")

        if not conseils:
            conseils.append("✨ Conditions stables et calmes sur le secteur.")

        return " | ".join(conseils)

    def analyser_flux_vent_local(self, dir_deg, v_val, h_val, t_val, p_val):
        txt_dir = self.convertir_degres_en_texte(dir_deg)
        desc_flux = f"Flux de secteur {txt_dir} ({dir_deg}°) établi à {v_val} km/h."

        if 135 <= dir_deg <= 225:
            if h_val < 40 and p_val < 1015:
                desc_foehn = (
                    f"🔥 Foehn / Lombarde majeur (Secteur {txt_dir}) : Assèchement brutal par effet de subsidence sur le relief. "
                    f"Risque d'évapotranspiration accélérée pour les courges et courgettes du jardin. Atmosphère très limpide."
                )
            else:
                desc_foehn = (
                    f"↗️ Flux de Sud-Ouest à Sud ({txt_dir}) : Composante advective douce mais humide. "
                    f"Surveillance de l'évolution nuageuse sur les crêtes et de la survenue possible d'averses orographiques."
                )
        else:
            desc_foehn = "✅ Absence de foehn (flux directeur orienté hors des secteurs sud à sud-ouest)."

        if 315 <= dir_deg or dir_deg <= 45:
            if t_val < 12:
                desc_bise = (
                    f"❄️ Entrée de Bise / Flux de Nord ({txt_dir}) : Descente d'air polaire ou continental. "
                    f"Sensation de fraîcheur accentuée à 900m, ralentissement potentiel de la pousse des légumes d'été."
                )
            else:
                desc_bise = (
                    f"🌤️ Flux de Nord à Nord-Est ({txt_dir}) : Temps sec, stable et assainissement net de la masse d'air. "
                    f"Bonne visibilité, mais fraîcheur nocturne prononcée en perspective."
                )
        else:
            desc_bise = "✅ Absence de bise marquée (protection relative du secteur)."

        if 45 < dir_deg < 135:
            desc_brise = f"🌅 Flux d'Est ({txt_dir}) : Brise de versant matinale classique. Stabilité thermique en cours de matinée."
        elif 225 < dir_deg < 315:
            desc_brise = f"🌇 Flux d'Ouest ({txt_dir}) : Régime d'occlusion ou passage de flux d'ouest océanique classique en moyenne montagne."
        else:
            desc_brise = "🏔️ Régime de vallée ou synoptique direct aligné sur les axes principaux."

        self.mettre_a_jour_texte_tuile(self.card_flux_actuel, desc_flux, f"Humidité: {h_val}% | Temp: {t_val}°C")
        self.mettre_a_jour_texte_tuile(self.card_foehn_analyse, desc_foehn, "Dynamique de masse d'air & Versant")
        self.mettre_a_jour_texte_tuile(self.card_bise_analyse, desc_bise, f"Régime thermique | {desc_brise}")

    def charger_donnees_csv(self):
        heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions = [], [], [], [], [], [], [], [], [], []
        if not os.path.exists(CSV_FILE):
            return heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions

        with open(CSV_FILE, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) < 9:
                    continue
                dt = self.parser_date_flexible(row[0])
                if dt:
                    try:
                        heures.append(dt)
                        temps.append(float(row[1]))
                        humids.append(float(row[2]))
                        pressions.append(float(row[3]))
                        vents.append(float(row[4]))
                        rafales.append(float(row[5]))
                        solaires.append(float(row[6]))
                        uvs.append(float(row[7]))
                        pluies.append(float(row[8]))
                        directions.append(float(row[9]) if len(row) > 9 else 180.0)
                    except ValueError:
                        continue
        return heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions

    def tracer_graphique_pluie(self, ax, heures, pluies, label="Pluie (mm)"):
        """Méthode centralisée garantissant la visibilité des barres de pluie"""
        ax.clear()

        # Largeur de barre augmentée (0.005 = ~7 min) pour visibilité garantie
        ax.bar(heures, pluies, color='#3498db', edgecolor='#2980b9', width=0.005, alpha=0.85, label=label)
        ax.set_ylabel("Pluie (mm)", fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.5)

        # Ajustement manuel de la limite Y pour éviter un axe écrasé à 0
        max_pluie = max(pluies) if pluies else 0
        ax.set_ylim(0, max(max_pluie * 1.2, 1.0))

        if label:
            ax.legend(loc="upper left", fontsize=7)

    def mettre_a_jour_temps_reel(self):
        heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions = self.charger_donnees_csv()
        if not heures:
            return

        dernier_t = temps[-1]
        dernier_h = humids[-1]
        dernier_p = pressions[-1]
        dernier_v = vents[-1]
        dernier_r = rafales[-1]
        dernier_s = solaires[-1]
        dernier_uv = uvs[-1]
        dernier_pl = pluies[-1]
        derniere_dir = directions[-1]

        self.mettre_a_jour_tuiles(dernier_t, dernier_h, dernier_p, dernier_v, dernier_r, dernier_s, dernier_uv, dernier_pl, derniere_dir)
        conseils = self.generer_conseils_intelligents(dernier_t, dernier_h, dernier_p, dernier_v, dernier_s, dernier_uv, dernier_pl)
        self.label_conseils.setText(conseils)

        self.canvas_live.ax_temp.clear()
        self.canvas_live.ax_hum.clear()
        self.canvas_live.ax_pres.clear()
        self.canvas_live.ax_vent.clear()
        self.canvas_live.ax_solaire.clear()
        self.canvas_live.ax_uv.clear()

        self.canvas_live.ax_temp.plot(heures, temps, color='#e74c3c', linewidth=1.5)
        self.canvas_live.ax_temp.set_ylabel("Temp (°C)", fontsize=8)
        self.canvas_live.ax_temp.grid(True, linestyle='--', alpha=0.5)

        self.canvas_live.ax_hum.plot(heures, humids, color='#1abc9c', linewidth=1.5)
        self.canvas_live.ax_hum.set_ylabel("Hum (%)", fontsize=8)
        self.canvas_live.ax_hum.grid(True, linestyle='--', alpha=0.5)

        self.canvas_live.ax_pres.plot(heures, pressions, color='#2980b9', linewidth=1.5)
        self.canvas_live.ax_pres.set_ylabel("Pres (hPa)", fontsize=8)
        self.canvas_live.ax_pres.grid(True, linestyle='--', alpha=0.5)

        self.canvas_live.ax_vent.plot(heures, vents, color='#8e44ad', linewidth=1.5, label="Moy")
        self.canvas_live.ax_vent.plot(heures, rafales, color='#d35400', linestyle=':', linewidth=1.5, label="Raf")
        self.canvas_live.ax_vent.set_ylabel("Vent", fontsize=8)
        self.canvas_live.ax_vent.legend(loc="upper left", fontsize=6)
        self.canvas_live.ax_vent.grid(True, linestyle='--', alpha=0.5)

        self.canvas_live.ax_solaire.plot(heures, solaires, color='#f1c40f', linewidth=1.5)
        self.canvas_live.ax_solaire.set_ylabel("Sol (W/m²)", fontsize=8)
        self.canvas_live.ax_solaire.grid(True, linestyle='--', alpha=0.5)

        self.canvas_live.ax_uv.plot(heures, uvs, color='#e67e22', linewidth=1.5)
        self.canvas_live.ax_uv.set_ylabel("UV", fontsize=8)
        self.canvas_live.ax_uv.grid(True, linestyle='--', alpha=0.5)

        # Tracé corrigé
        self.tracer_graphique_pluie(self.canvas_live.ax_pluie, heures, pluies, label="")

        self.canvas_live.fig.tight_layout()
        self.canvas_live.draw()

    def mettre_a_jour_graphique_global(self):
        heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions = self.charger_donnees_csv()
        if not heures:
            return

        self.canvas_global.ax_temp.clear()
        self.canvas_global.ax_pres.clear()
        self.canvas_global.ax_hum.clear()
        self.canvas_global.ax_vent.clear()

        self.canvas_global.ax_temp.plot(heures, temps, color='#e74c3c', label="Température (°C)")
        self.canvas_global.ax_temp.legend(loc="upper left")
        self.canvas_global.ax_temp.grid(True, linestyle='--', alpha=0.5)

        self.canvas_global.ax_pres.plot(heures, pressions, color='#2980b9', label="Pression (hPa)")
        self.canvas_global.ax_pres.legend(loc="upper left")
        self.canvas_global.ax_pres.grid(True, linestyle='--', alpha=0.5)

        # Tracé corrigé
        self.tracer_graphique_pluie(self.canvas_global.ax_pluie, heures, pluies, label="Précipitations (mm)")

        self.canvas_global.ax_hum.plot(heures, humids, color='#1abc9c', label="Humidité (%)")
        self.canvas_global.ax_hum.legend(loc="upper left")
        self.canvas_global.ax_hum.grid(True, linestyle='--', alpha=0.5)

        self.canvas_global.ax_vent.plot(heures, vents, color='#8e44ad', label="Vent Moyen (km/h)")
        self.canvas_global.ax_vent.plot(heures, rafales, color='#d35400', linestyle=':', label="Rafales (km/h)")
        self.canvas_global.ax_vent.legend(loc="upper left")
        self.canvas_global.ax_vent.grid(True, linestyle='--', alpha=0.5)

        self.canvas_global.fig.tight_layout()
        self.canvas_global.draw()

    def mettre_a_jour_flux_vent(self):
        heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions = self.charger_donnees_csv()
        if not directions:
            return

        self.canvas_vent_rose.ax.clear()

        rads = [math.radians(d) for d in directions]
        self.canvas_vent_rose.ax.set_theta_zero_location('N')
        self.canvas_vent_rose.ax.set_theta_direction(-1)
        self.canvas_vent_rose.ax.hist(rads, bins=16, color='#8e44ad', alpha=0.75, edgecolor='black')

        dir_actuelle = directions[-1]
        v_actuelle = vents[-1]
        h_actuelle = humids[-1]
        t_actuelle = temps[-1]
        p_actuelle = pressions[-1]

        self.analyser_flux_vent_local(dir_actuelle, v_actuelle, h_actuelle, t_actuelle, p_actuelle)
        self.canvas_vent_rose.draw()

    def mettre_a_jour_statistiques(self):
        heures, temps, humids, pressions, vents, rafales, solaires, uvs, pluies, directions = self.charger_donnees_csv()
        if not temps:
            return

        self.mettre_a_jour_texte_tuile(self.stat_t_min, f"{min(temps)} °C", "Minimum sur la période")
        self.mettre_a_jour_texte_tuile(self.stat_t_max, f"{max(temps)} °C", "Maximum sur la période")
        self.mettre_a_jour_texte_tuile(self.stat_rafales, f"{max(rafales)} km/h", "Rafale maximale")
        self.mettre_a_jour_texte_tuile(self.stat_pression, f"{round(sum(pressions)/len(pressions), 1)} hPa", "Pression moyenne")
        self.mettre_a_jour_texte_tuile(self.stat_pluie_mois, f"{round(sum(pluies), 2)} mm", "Cumul total enregistré")
        self.mettre_a_jour_texte_tuile(self.stat_solaire_max, f"{max(solaires)} W/m²", "Rayonnement maximal")
        self.mettre_a_jour_texte_tuile(self.stat_uv_moyen, f"{max(uvs)}", "Indice UV maximal")

    def mettre_a_jour_previsions(self):
        heures_prev = [datetime.now() + timedelta(hours=i*3) for i in range(16)]
        temps_prev = [round(18 + 5 * math.sin(i / 2.0), 1) for i in range(16)]
        pres_prev = [round(1015 + 3 * math.cos(i / 3.0), 1) for i in range(16)]

        self.canvas_prev.ax_temp.clear()
        self.canvas_prev.ax_pres.clear()

        self.canvas_prev.ax_temp.plot(heures_prev, temps_prev, color='#e67e22', label="Température (°C)")
        self.canvas_prev.ax_temp.grid(True, linestyle='--', alpha=0.5)
        self.canvas_prev.ax_temp.legend(loc="upper left")

        self.canvas_prev.ax_pres.plot(heures_prev, pres_prev, color='#2980b9', label="Pression (hPa)")
        self.canvas_prev.ax_pres.grid(True, linestyle='--', alpha=0.5)
        self.canvas_prev.ax_pres.legend(loc="upper left")

        self.canvas_prev.fig.tight_layout()
        self.canvas_prev.draw()

        prev_donnees = [
            ("Aujourd'hui", "Ensoleillé", "12°C / 22°C", "10%"),
            ("Demain", "Passages nuageux", "11°C / 20°C", "30%"),
            ("J+2", "Averses locales", "9°C / 16°C", "70%"),
            ("J+3", "Éclaircies", "10°C / 18°C", "20%")
        ]

        self.table_previsions.setRowCount(len(prev_donnees))
        for row_idx, row_data in enumerate(prev_donnees):
            for col_idx, text in enumerate(row_data):
                self.table_previsions.setItem(row_idx, col_idx, QTableWidgetItem(text))

    def mettre_a_jour_graphique_csv(self):
        if not self.dernier_csv_lignes:
            return

        heures, temps, pressions, pluies = [], [], [], []
        for line in self.dernier_csv_lignes:
            dt = self.parser_date_flexible(line["Heure"])
            if dt:
                try:
                    heures.append(dt)
                    temps.append(float(line["Temperature"]))
                    pressions.append(float(line["Pression"]))
                    pluies.append(float(line["Pluie"]))
                except ValueError:
                    continue

        if not heures:
            return

        self.canvas_csv.ax_temp.clear()
        self.canvas_csv.ax_pres.clear()

        self.canvas_csv.ax_temp.plot(heures, temps, color='#e74c3c')
        self.canvas_csv.ax_temp.set_ylabel("Temp (°C)")
        self.canvas_csv.ax_temp.grid(True, linestyle='--', alpha=0.5)

        self.canvas_csv.ax_pres.plot(heures, pressions, color='#2980b9')
        self.canvas_csv.ax_pres.set_ylabel("Pres (hPa)")
        self.canvas_csv.ax_pres.grid(True, linestyle='--', alpha=0.5)

        # Tracé corrigé
        self.tracer_graphique_pluie(self.canvas_csv.ax_pluie, heures, pluies, label="")

        self.canvas_csv.fig.tight_layout()
        self.canvas_csv.draw()

    def remplir_tableau_csv(self):
        if not self.dernier_csv_lignes:
            return

        self.table_csv.setRowCount(len(self.dernier_csv_lignes))
        cles = list(self.dernier_csv_lignes[0].keys())
        self.table_csv.setColumnCount(len(cles))
        self.table_csv.setHorizontalHeaderLabels(cles)

        for row_idx, line in enumerate(self.dernier_csv_lignes):
            for col_idx, key in enumerate(cles):
                self.table_csv.setItem(row_idx, col_idx, QTableWidgetItem(str(line[key])))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeteoApp()
    window.charger_stylesheet(app)
    window.show()
    sys.exit(app.exec_())
