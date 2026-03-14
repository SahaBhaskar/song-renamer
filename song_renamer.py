#!/usr/bin/env python3
"""
song_renamer.py — Analyze audio files and rename them with BPM, key, and energy.
              — Build a 120-min DJ set with a musical journey arc.
"""

import sys
import re
import math
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTreeWidget,
    QTreeWidgetItem, QFileDialog, QMessageBox, QHeaderView,
    QTabWidget, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

try:
    import librosa
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "librosa"])
    import librosa

try:
    import soundfile as sf
except ImportError:
    sf = None

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg", ".m4a"}
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A",  "3A", "10A"]

_KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_TP_MAJ = np.array([5.0,  2.0,  3.5,  2.0,  4.5,  4.0,  2.0,  4.5,  2.0,  3.5,  1.5,  4.0])
_TP_MIN = np.array([5.0,  2.0,  3.5,  4.5,  2.0,  4.0,  2.0,  4.5,  3.5,  2.0,  1.5,  4.0])
_SH_MAJ = np.array([6.6,  2.0,  3.5,  2.3,  4.6,  3.9,  2.3,  5.4,  2.3,  3.7,  2.3,  3.4])
_SH_MIN = np.array([6.5,  2.7,  3.5,  5.4,  2.6,  3.5,  2.5,  5.1,  4.0,  2.7,  3.0,  3.2])
PROFILES = [(_KS_MAJ, _KS_MIN), (_TP_MAJ, _TP_MIN), (_SH_MAJ, _SH_MIN)]

ANALYSIS_SR  = 22050
INTRO_SKIP   = 15
MAX_DURATION = 90


# ── Audio analysis ─────────────────────────────────────────────────────────────

def get_file_duration(file):
    """Fast duration read from file metadata (no audio decode)."""
    try:
        if sf is not None:
            return sf.info(str(file)).duration
        return float(librosa.get_duration(path=str(file)))
    except Exception:
        return 360.0  # fallback: 6 min


def load_audio(file):
    return librosa.load(str(file), sr=ANALYSIS_SR, mono=True,
                        offset=INTRO_SKIP, duration=MAX_DURATION)


def detect_bpm(y_perc, sr):
    onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr, aggregate=np.median)
    tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
    return int(round(float(np.atleast_1d(tempo)[0])))


def _profile_vote(chroma_mean):
    votes = np.zeros((12, 2))
    for maj_prof, min_prof in PROFILES:
        maj_scores = np.array([
            np.corrcoef(np.roll(chroma_mean, -i), maj_prof)[0, 1]
            for i in range(12)
        ])
        min_scores = np.array([
            np.corrcoef(np.roll(chroma_mean, -i), min_prof)[0, 1]
            for i in range(12)
        ])
        bm = int(np.argmax(maj_scores))
        bn = int(np.argmax(min_scores))
        if maj_scores[bm] >= min_scores[bn]:
            votes[bm, 0] += maj_scores[bm]
        else:
            votes[bn, 1] += min_scores[bn]
    pc, mode = np.unravel_index(np.argmax(votes), votes.shape)
    confidence = float(votes[pc, mode]) / (votes.sum() or 1)
    return int(pc), int(mode), confidence


def detect_key(y_harm, sr):
    hop = 512
    chroma_full = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop)
    frames_per_seg = int(30 * sr / hop)
    n_frames = chroma_full.shape[1]
    segments = [np.mean(chroma_full[:, s:s + frames_per_seg], axis=1)
                for s in range(0, n_frames, frames_per_seg)
                if chroma_full[:, s:s + frames_per_seg].shape[1] >= frames_per_seg // 4]
    segments.append(np.mean(chroma_full, axis=1))

    vote_accum = np.zeros((12, 2))
    for chroma_mean in segments:
        pc, mode, conf = _profile_vote(chroma_mean)
        vote_accum[pc, mode] += conf

    pc, mode = np.unravel_index(np.argmax(vote_accum), vote_accum.shape)
    pc, mode = int(pc), int(mode)

    if mode == 0:
        return CAMELOT_MAJOR[pc], f"{KEY_NAMES[pc]}maj"
    return CAMELOT_MINOR[pc], f"{KEY_NAMES[pc]}min"


def detect_energy(y, sr):
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    peak_rms = float(np.percentile(rms, 90))
    energy = np.clip(peak_rms / 0.25 * 10, 1.0, 10.0)
    return int(round(energy))


def build_new_name(stem, suffix, bpm, camelot, energy):
    clean = re.sub(r"_\d+bpm_\d+[AB]_E\d+$", "", stem)
    clean = re.sub(r"_\d+bpm_[A-Gb#]+(?:maj|min)_E\d+$", "", clean)
    return f"{clean}_{bpm}bpm_{camelot}_E{energy}{suffix}"


# ── DJ Set Builder logic ────────────────────────────────────────────────────────

def _parse_camelot(key):
    """Returns (number, letter) or None."""
    try:
        return int(key[:-1]), key[-1].upper()
    except (ValueError, IndexError, TypeError):
        return None


def camelot_score(k1, k2):
    """0.0–1.0 harmonic compatibility score based on Camelot Wheel rules."""
    p1, p2 = _parse_camelot(k1), _parse_camelot(k2)
    if not p1 or not p2:
        return 0.5
    n1, l1 = p1
    n2, l2 = p2
    if n1 == n2 and l1 == l2:          return 1.00  # same key
    if n1 == n2:                        return 0.88  # relative major/minor (A↔B same number)
    diff = min(abs(n1 - n2), 12 - abs(n1 - n2))
    if l1 == l2 and diff == 1:          return 0.82  # adjacent on wheel (energy boost/lift)
    if l1 == l2 and diff == 7 % 12:    return 0.70  # dominant/subdominant
    if l1 == l2 and diff == 2:          return 0.55  # two steps
    if diff == 1:                       return 0.45  # close but mode change
    return 0.15


def bpm_score(b1, b2):
    """0.0–1.0 BPM compatibility score."""
    try:
        b1, b2 = int(b1), int(b2)
    except (ValueError, TypeError):
        return 0.5
    diff = abs(b1 - b2)
    if diff == 0:   return 1.00
    if diff <= 3:   return 0.92
    if diff <= 6:   return 0.80
    if diff <= 10:  return 0.65
    if diff <= 15:  return 0.45
    # Check half/double tempo (common DJ technique)
    ratio = b1 / b2 if b2 != 0 else 0
    if abs(ratio - 2.0) < 0.08 or abs(ratio - 0.5) < 0.08:
        return 0.60
    return max(0.0, 1.0 - diff / 60.0)


def energy_target(progress):
    """Target energy (1–10) at a given set progress (0.0–1.0).

    Arc:  warm-up → build → peak → sustain → outro
          3→5       5→8     8→10    10→7      7→3
    """
    if progress < 0.15:
        return 3 + (progress / 0.15) * 2          # 3 → 5
    if progress < 0.40:
        return 5 + ((progress - 0.15) / 0.25) * 3 # 5 → 8
    if progress < 0.65:
        return 8 + ((progress - 0.40) / 0.25) * 2 # 8 → 10
    if progress < 0.85:
        return 10 - ((progress - 0.65) / 0.20) * 3 # 10 → 7
    return 7 - ((progress - 0.85) / 0.15) * 4     # 7 → 3


def phase_label(progress):
    if progress < 0.15: return "Warm-up"
    if progress < 0.40: return "Build"
    if progress < 0.65: return "Peak"
    if progress < 0.85: return "Sustain"
    return "Outro"


def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def build_dj_set(tracks, target_secs=7200):
    """
    Greedy set builder:
    Score = 0.40 × energy_match + 0.38 × harmonic_compat + 0.22 × bpm_compat
    Each track is used at most once. Arc is scaled to actual library duration
    so the full Warm-up→Outro journey plays out regardless of library size.
    """
    pool = [t for t in tracks if t["error"] is None]
    if not pool:
        return []

    # Scale the energy arc to actual available music (capped at target)
    actual_total = sum(t.get("duration", 360.0) for t in pool)
    arc_duration = min(actual_total, float(target_secs))

    set_list = []
    total    = 0.0
    used     = set()

    while len(used) < len(pool):
        progress   = min(total / arc_duration, 1.0) if arc_duration > 0 else 0.0
        target_e   = energy_target(progress)
        prev       = set_list[-1] if set_list else None

        candidates = [t for t in pool if id(t) not in used]
        if not candidates:
            break

        best_score, best_track = -1.0, None

        for t in candidates:
            try:
                e = int(t["energy"])
            except (ValueError, TypeError):
                e = 5
            e_score = 1.0 - abs(e - target_e) / 9.0

            if prev:
                h_score = camelot_score(prev["camelot"], t["camelot"])
                b_score = bpm_score(prev["bpm"], t["bpm"])
            else:
                h_score = b_score = 0.8

            score = 0.40 * e_score + 0.38 * h_score + 0.22 * b_score
            if score > best_score:
                best_score, best_track = score, t

        if best_track is None:
            break

        dur = best_track.get("duration", 360.0)
        set_list.append({
            **best_track,
            "set_start": total,
            "phase":     phase_label(progress),
            "compat":    round(best_score * 100),
        })
        total += dur
        used.add(id(best_track))

    return set_list


# ── Background worker ──────────────────────────────────────────────────────────

class AnalyzeWorker(QThread):
    row_ready    = pyqtSignal(dict)
    progress     = pyqtSignal(int)
    status       = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, files):
        super().__init__()
        self._files = files

    def run(self):
        for i, file in enumerate(self._files):
            self.status.emit(f"Analyzing {i+1}/{len(self._files)}: {file.name}")
            try:
                duration           = get_file_duration(file)
                y, sr              = load_audio(file)
                y_harm, y_perc     = librosa.effects.hpss(y, margin=3)
                bpm                = detect_bpm(y_perc, sr)
                camelot, note      = detect_key(y_harm, sr)
                energy             = detect_energy(y, sr)
                new                = build_new_name(file.stem, file.suffix, bpm, camelot, energy)
                result = {
                    "file": file, "bpm": bpm, "camelot": camelot,
                    "note": note, "energy": energy, "new_name": new,
                    "duration": duration, "error": None,
                }
            except Exception as e:
                result = {
                    "file": file, "bpm": "?", "camelot": "?", "note": "?",
                    "energy": "?", "new_name": file.name,
                    "duration": 360.0, "error": str(e),
                }
            self.row_ready.emit(result)
            self.progress.emit(i + 1)
        self.finished_all.emit()


# ── Styles ─────────────────────────────────────────────────────────────────────

DARK   = "#1e1e2e"
PANEL  = "#2a2a3e"
ACCENT = "#89b4fa"
TEXT   = "#cdd6f4"
MUTED  = "#6c7086"
GREEN  = "#a6e3a1"
RED    = "#f38ba8"
AMBER  = "#f9e2af"
ORANGE = "#fab387"
PURPLE = "#cba6f7"
ALT    = "#313244"

# Phase colours for the set builder
PHASE_COLORS = {
    "Warm-up": ACCENT,
    "Build":   AMBER,
    "Peak":    ORANGE,
    "Sustain": RED,
    "Outro":   PURPLE,
}

QSS = f"""
QMainWindow, QWidget#root {{ background: {DARK}; }}
QTabWidget::pane {{ border: none; background: {DARK}; }}
QTabBar::tab {{
    background: {PANEL}; color: {MUTED};
    padding: 7px 20px; border: none;
    font-family: Menlo, monospace; font-size: 12px;
}}
QTabBar::tab:selected {{ background: {DARK}; color: {TEXT}; font-weight: bold; }}
QLabel {{ color: {TEXT}; font-family: Menlo, monospace; font-size: 13px; }}
QLabel#status {{ color: {MUTED}; font-size: 11px; padding: 2px 14px; }}
QLineEdit {{
    background: {PANEL}; color: {TEXT}; border: none;
    border-radius: 6px; padding: 5px 8px;
    font-family: Menlo, monospace; font-size: 12px;
}}
QPushButton {{
    border: none; border-radius: 6px; padding: 6px 14px;
    font-family: Menlo, monospace; font-size: 12px; font-weight: bold;
}}
QPushButton#browse   {{ background: {ACCENT};  color: {DARK}; }}
QPushButton#analyze  {{ background: {GREEN};   color: {DARK}; }}
QPushButton#sel_all  {{ background: {PANEL};   color: {TEXT}; font-weight: normal; }}
QPushButton#desel    {{ background: {PANEL};   color: {TEXT}; font-weight: normal; }}
QPushButton#rename   {{ background: {RED};     color: {DARK}; }}
QPushButton#build    {{ background: {PURPLE};  color: {DARK}; }}
QPushButton#export   {{ background: {AMBER};   color: {DARK}; }}
QPushButton:disabled {{ opacity: 0.4; }}
QProgressBar {{
    background: {PANEL}; border: none; border-radius: 4px; height: 6px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QTreeWidget {{
    background: {PANEL}; color: {TEXT}; border: none;
    font-family: Menlo, monospace; font-size: 12px;
    alternate-background-color: {ALT};
}}
QTreeWidget::item {{ padding: 4px 0; }}
QTreeWidget::item:selected {{ background: {ALT}; color: {TEXT}; }}
QHeaderView::section {{
    background: {DARK}; color: {ACCENT}; border: none;
    padding: 5px 8px; font-family: Menlo, monospace;
    font-size: 12px; font-weight: bold;
}}
QScrollBar:vertical {{
    background: {DARK}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {MUTED}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


# ── Rename tab ─────────────────────────────────────────────────────────────────

class RenameTab(QWidget):
    analysis_done = pyqtSignal(list)   # emits results to Set Builder tab

    def __init__(self):
        super().__init__()
        self._results = []
        self._checked = []
        self._worker  = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Top bar
        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(QLabel("Folder:"))
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select a folder…")
        top.addWidget(self._folder_edit, stretch=1)

        browse_btn = QPushButton("Browse"); browse_btn.setObjectName("browse")
        browse_btn.clicked.connect(self._browse)
        top.addWidget(browse_btn)

        self._analyze_btn = QPushButton("Analyze"); self._analyze_btn.setObjectName("analyze")
        self._analyze_btn.clicked.connect(self._start_analysis)
        top.addWidget(self._analyze_btn)
        layout.addLayout(top)

        self._status_lbl = QLabel("Browse to a folder and click Analyze.")
        self._status_lbl.setObjectName("status")
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        # Table
        self._tree = QTreeWidget()
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["", "Original filename", "BPM", "Key (Camelot)", "Energy", "New filename"])
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(0, 30)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive); self._tree.setColumnWidth(1, 280)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(2, 60)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(3, 120)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(4, 75)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._tree.itemClicked.connect(self._toggle_check)
        layout.addWidget(self._tree, stretch=1)

        # Bottom bar
        bot = QHBoxLayout(); bot.setSpacing(8)
        sel_btn = QPushButton("Select All"); sel_btn.setObjectName("sel_all")
        sel_btn.clicked.connect(self._select_all); bot.addWidget(sel_btn)
        desel_btn = QPushButton("Deselect All"); desel_btn.setObjectName("desel")
        desel_btn.clicked.connect(self._deselect_all); bot.addWidget(desel_btn)
        bot.addStretch()
        self._rename_btn = QPushButton("Rename Selected"); self._rename_btn.setObjectName("rename")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._rename_selected)
        bot.addWidget(self._rename_btn)
        layout.addLayout(bot)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select music folder")
        if folder:
            self._folder_edit.setText(folder)

    def _start_analysis(self):
        folder = Path(self._folder_edit.text().strip()).expanduser()
        if not folder.is_dir():
            QMessageBox.critical(self, "Invalid folder", f"Not a directory:\n{folder}"); return
        files = sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS)
        if not files:
            QMessageBox.information(self, "No files", "No audio files found."); return

        self._tree.clear(); self._results.clear(); self._checked.clear()
        self._progress.setMaximum(len(files)); self._progress.setValue(0)
        self._analyze_btn.setEnabled(False); self._rename_btn.setEnabled(False)

        self._worker = AnalyzeWorker(files)
        self._worker.row_ready.connect(self._add_row)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.status.connect(self._status_lbl.setText)
        self._worker.finished_all.connect(self._on_done)
        self._worker.start()

    def _add_row(self, r):
        ok = r["error"] is None
        self._results.append(r); self._checked.append(ok)
        energy_str = f"{r['energy']}/10" if ok else "err"
        key_str    = f"{r['camelot']} ({r['note']})" if ok else "?"
        new_disp   = r["new_name"] if ok else f"[ERROR] {r['error']}"
        item = QTreeWidgetItem(["☑" if ok else "☐", r["file"].name,
                                str(r["bpm"]), key_str, energy_str, new_disp])
        item.setTextAlignment(0, Qt.AlignmentFlag.AlignCenter)
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)
        item.setTextAlignment(4, Qt.AlignmentFlag.AlignCenter)
        if not ok:
            for col in range(6): item.setForeground(col, QColor(RED))
        self._tree.addTopLevelItem(item)

    def _toggle_check(self, item, column):
        if column != 0: return
        idx = self._tree.indexOfTopLevelItem(item)
        if self._results[idx]["error"] is not None: return
        self._checked[idx] = not self._checked[idx]
        item.setText(0, "☑" if self._checked[idx] else "☐")

    def _select_all(self):
        for i, r in enumerate(self._results):
            if r["error"] is None:
                self._checked[i] = True
                self._tree.topLevelItem(i).setText(0, "☑")

    def _deselect_all(self):
        for i in range(len(self._checked)):
            self._checked[i] = False
            self._tree.topLevelItem(i).setText(0, "☐")

    def _rename_selected(self):
        selected = [(r, i) for i, (r, c) in enumerate(zip(self._results, self._checked))
                    if c and r["error"] is None]
        if not selected:
            QMessageBox.information(self, "Nothing selected", "No files checked."); return
        reply = QMessageBox.question(self, "Confirm rename",
            f"Rename {len(selected)} file(s)?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        errors = []
        for r, _ in selected:
            try:
                new_path = r["file"].parent / r["new_name"]
                if new_path != r["file"]:
                    r["file"].rename(new_path); r["file"] = new_path
            except Exception as e:
                errors.append(f"{r['file'].name}: {e}")
        if errors:
            QMessageBox.critical(self, "Some renames failed", "\n".join(errors))
        else:
            QMessageBox.information(self, "Done", f"{len(selected)} file(s) renamed.")
        self._rename_btn.setEnabled(False); self._analyze_btn.setEnabled(True)

    def _on_done(self):
        self._status_lbl.setText(
            f"Analysis complete — {len(self._results)} file(s). "
            "Check/uncheck rows, then click Rename Selected.")
        self._analyze_btn.setEnabled(True)
        self._rename_btn.setEnabled(True)
        self.analysis_done.emit(list(self._results))


# ── Set Builder tab ────────────────────────────────────────────────────────────

class SetBuilderTab(QWidget):
    def __init__(self):
        super().__init__()
        self._tracks  = []
        self._set     = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        # Header row
        hdr = QHBoxLayout(); hdr.setSpacing(10)

        info = QLabel("Build a 120-min DJ set with an automatic energy journey.")
        info.setObjectName("status")
        hdr.addWidget(info, stretch=1)

        self._build_btn = QPushButton("Build 120-min Set")
        self._build_btn.setObjectName("build")
        self._build_btn.setEnabled(False)
        self._build_btn.clicked.connect(self._on_build_clicked)
        hdr.addWidget(self._build_btn)

        self._export_btn = QPushButton("Export Set List")
        self._export_btn.setObjectName("export")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export)
        hdr.addWidget(self._export_btn)

        self._rename_set_btn = QPushButton("Rename by Set Order")
        self._rename_set_btn.setObjectName("rename")
        self._rename_set_btn.setEnabled(False)
        self._rename_set_btn.clicked.connect(self._rename_set_order)
        hdr.addWidget(self._rename_set_btn)

        layout.addLayout(hdr)

        # Legend
        legend_row = QHBoxLayout(); legend_row.setSpacing(16)
        for phase, color in PHASE_COLORS.items():
            dot = QLabel(f"● {phase}")
            dot.setStyleSheet(f"color: {color}; font-size: 11px; font-family: Menlo, monospace;")
            legend_row.addWidget(dot)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Set list table
        self._tree = QTreeWidget()
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self._tree.setColumnCount(7)
        self._tree.setHeaderLabels(["#", "Track", "BPM", "Key", "Energy", "Phase", "Time"])
        hdr2 = self._tree.header()
        hdr2.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(0, 35)
        hdr2.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr2.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(2, 60)
        hdr2.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(3, 80)
        hdr2.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(4, 70)
        hdr2.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(5, 90)
        hdr2.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed);       self._tree.setColumnWidth(6, 70)
        layout.addWidget(self._tree, stretch=1)

        # Footer
        self._footer_lbl = QLabel("Run Analyze on a folder first, then come here to build the set.")
        self._footer_lbl.setObjectName("status")
        layout.addWidget(self._footer_lbl)

    def set_tracks(self, tracks):
        self._tracks = tracks
        n_ok = sum(1 for t in tracks if t["error"] is None)
        self._build_btn.setEnabled(n_ok > 0)
        self._footer_lbl.setText(
            f"{n_ok} track(s) available. Click 'Build 120-min Set' to generate the set.")

    def _on_build_clicked(self):
        n_ok = sum(1 for t in self._tracks if t["error"] is None)
        total_dur = sum(t.get("duration", 360) for t in self._tracks if t["error"] is None)
        total_min = int(total_dur / 60)

        set_min  = min(total_min, 120)
        arc_note = (
            f"Set will be ~{set_min} min (all {n_ok} tracks, no repeats)."
            if total_min < 120 else
            f"Set will be ~120 min from {n_ok} tracks, no repeats."
        )

        reply = QMessageBox.question(
            self, "Build DJ Set",
            f"{arc_note}\n\n"
            "Tracks are arranged into a full musical journey:\n"
            "  Warm-up → Build → Peak → Sustain → Outro\n\n"
            "Selection uses energy arc, Camelot harmonic\n"
            "compatibility, and BPM flow. No song is repeated.\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set = build_dj_set(self._tracks, target_secs=7200)
        self._display_set()

    def _display_set(self):
        self._tree.clear()
        if not self._set:
            self._footer_lbl.setText("Could not build a set — no valid tracks.")
            return

        total_secs = self._set[-1]["set_start"] + self._set[-1].get("duration", 360)

        for i, t in enumerate(self._set):
            phase  = t["phase"]
            color  = PHASE_COLORS.get(phase, TEXT)
            e_str  = f"{t['energy']}/10" if t['energy'] != "?" else "?"
            k_str  = f"{t['camelot']}"   if t['camelot'] != "?" else "?"

            item = QTreeWidgetItem([
                str(i + 1),
                t["file"].name,
                str(t["bpm"]),
                k_str,
                e_str,
                phase,
                format_time(t["set_start"]),
            ])
            for col in range(7):
                item.setForeground(col, QColor(color))
            item.setTextAlignment(0, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(4, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(5, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(6, Qt.AlignmentFlag.AlignCenter)
            self._tree.addTopLevelItem(item)

        self._footer_lbl.setText(
            f"Set: {len(self._set)} tracks  ·  "
            f"Total duration: ~{format_time(total_secs)}  ·  "
            "Export or rename files by set order.")
        self._export_btn.setEnabled(True)
        self._rename_set_btn.setEnabled(True)

    def _rename_set_order(self):
        if not self._set:
            return

        total = len(self._set)
        pad   = len(str(total))   # e.g. 2 digits for ≤99 tracks

        PHASE_SHORT = {
            "Warm-up": "WRM",
            "Build":   "BLD",
            "Peak":    "PEK",
            "Sustain": "SUS",
            "Outro":   "OUT",
        }

        # Preview the new names
        previews = []
        for i, t in enumerate(self._set):
            phase_slug = PHASE_SHORT.get(t["phase"], t["phase"][:3].upper())
            # Strip any existing order prefix: "01_WRM_" pattern
            stem = re.sub(r"^\d+_[A-Z]{3}_", "", t["file"].stem)
            new_name = f"{i+1:0{pad}d}_{phase_slug}_{stem}{t['file'].suffix}"
            previews.append((t, new_name))

        # Show confirmation with a few examples
        examples = "\n".join(
            f"  {p[1]}" for p in previews[:5]
        ) + ("\n  …" if total > 5 else "")

        reply = QMessageBox.question(
            self, "Rename by Set Order",
            f"Rename {total} file(s) with set position and phase prefix?\n\n"
            f"Format:  {{pos}}_{{Phase}}_{{original name}}\n\n"
            f"Examples:\n{examples}\n\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        errors = []
        for t, new_name in previews:
            try:
                new_path = t["file"].parent / new_name
                if new_path != t["file"]:
                    t["file"].rename(new_path)
                    t["file"] = new_path
            except Exception as e:
                errors.append(f"{t['file'].name}: {e}")

        if errors:
            QMessageBox.critical(self, "Some renames failed", "\n".join(errors))
        else:
            QMessageBox.information(self, "Done", f"{total} file(s) renamed.")

        # Refresh the table with updated filenames
        self._display_set()

    def _export(self):
        if not self._set:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save set list", "dj_set.txt",
            "Text file (*.txt);;M3U playlist (*.m3u)")
        if not path:
            return
        try:
            if path.endswith(".m3u"):
                lines = ["#EXTM3U"]
                for t in self._set:
                    dur = int(t.get("duration", -1))
                    lines.append(f"#EXTINF:{dur},{t['file'].stem}")
                    lines.append(str(t["file"]))
            else:
                lines = [
                    "DJ SET — 120 min",
                    "=" * 60,
                    f"{'#':<4} {'BPM':<6} {'Key':<6} {'E':<4} {'Phase':<10} {'Time':<8} Track",
                    "-" * 60,
                ]
                for i, t in enumerate(self._set):
                    lines.append(
                        f"{i+1:<4} {str(t['bpm']):<6} {str(t['camelot']):<6} "
                        f"{str(t['energy']):<4} {t['phase']:<10} "
                        f"{format_time(t['set_start']):<8} {t['file'].name}"
                    )
                total = self._set[-1]["set_start"] + self._set[-1].get("duration", 360)
                lines += ["", f"Total: {len(self._set)} tracks · ~{format_time(total)}"]

            Path(path).write_text("\n".join(lines))
            QMessageBox.information(self, "Exported", f"Set list saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))


# ── Main window ────────────────────────────────────────────────────────────────

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Song Renamer + DJ Set Builder")
        self.resize(1100, 680)
        self.setStyleSheet(QSS)

        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        self._rename_tab  = RenameTab()
        self._set_tab     = SetBuilderTab()

        tabs.addTab(self._rename_tab, "  Rename Tracks  ")
        tabs.addTab(self._set_tab,    "  DJ Set Builder  ")

        self._rename_tab.analysis_done.connect(self._set_tab.set_tracks)

        layout.addWidget(tabs)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
