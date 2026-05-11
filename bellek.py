#!/usr/bin/env python3

import sys
import json
import random
import os
import uuid
import tempfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from PyQt5.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QMessageBox, QAction,
    QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QLineEdit, QFrame, QLayout
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap, QPen, QIcon, QLinearGradient
import base64


# ===================== ICON / DIALOG HELPERS =====================


def load_icon(path):
    """Load icon from file (icons folder and current directory)."""
    base = Path(__file__).resolve().parent
    for folder in [base / "icons", base]:
        p = folder / path
        if p.exists():
            pix = QPixmap(str(p))
            if not pix.isNull():
                return pix.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None


def load_app_icon():
    """Load app icon from bellek.png next to this file (and PyInstaller _MEIPASS)."""
    bellek_py = Path(__file__).resolve()
    icon_path = bellek_py.parent / "bellek.png"
    if icon_path.exists():
        return QIcon(str(icon_path))

    # PyInstaller bundle fallback
    try:
        if getattr(sys, 'frozen', False):
            base_path = getattr(sys, '_MEIPASS', None)
            if base_path:
                png_path = os.path.join(base_path, 'bellek.png')
                if os.path.exists(png_path):
                    return QIcon(png_path)
    except Exception:
        pass

    return QIcon()


def get_icon():
    """Get app icon for dialogs (same as app icon)."""
    return load_app_icon()


def input_dialog(parent, title, label, default_text=""):
    """Custom input dialog with app icon."""
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowIcon(get_icon())
    dialog.setFixedSize(350, 150)
    layout = QVBoxLayout(dialog)

    icon_label = QLabel()
    icon_label.setPixmap(get_icon().pixmap(48, 48))
    icon_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(icon_label)

    label_w = QLabel(label)
    label_w.setAlignment(Qt.AlignCenter)
    layout.addWidget(label_w)

    edit = QLineEdit(default_text)
    layout.addWidget(edit)

    btn_layout = QHBoxLayout()
    ok_btn = QPushButton("Tamam")
    cancel_btn = QPushButton("İptal")
    btn_layout.addStretch()
    btn_layout.addWidget(ok_btn)
    btn_layout.addWidget(cancel_btn)
    layout.addLayout(btn_layout)

    ok_btn.clicked.connect(lambda: dialog.done(1))
    cancel_btn.clicked.connect(lambda: dialog.done(0))
    edit.returnPressed.connect(lambda: dialog.done(1))

    if dialog.exec_() == 1:
        return edit.text(), True
    return "", False


# ===================== UI WIDGETS =====================

class RibbonBar(QWidget):
    """Toolbar widget (UI unchanged)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.setStyleSheet("""
            QWidget { background-color: white; }
            QFrame#box {
                background: white;
                border: 1px solid #cccccc;
                border-radius: 8px;
            }
            QPushButton {
                border: none;
                background: white;
                color: #333333;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #eaeaea; }
            QLineEdit, QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px 8px;
                background: white;
            }
            QLineEdit:hover, QComboBox:hover { background: #eaeaea; }
            QComboBox::drop-down { border: none; background: transparent; width: 16px; }
            QComboBox { border: 1px solid #cccccc; background: white; color: black; }
            QComboBox QAbstractItemView { background: white; border: 1px solid #cccccc; color: black; }
            QComboBox QListView { background: white; border: 1px solid #cccccc; }
            QComboBox QListView::item { background: white; color: black; }
            QComboBox QListView::item:selected { background: #eaeaea !important; color: black; }
            QComboBox QListView::item:hover { background: #eaeaea !important; color: black; }
            QLabel { color: #333333; }
            #toolbar_btn { background: white; }
            #toolbar_btn:hover { background: #eaeaea; }
        """)


@dataclass
class Card:
    id: int
    pair_id: int
    icon: str
    is_flipped: bool = False
    is_matched: bool = False
    rect: QRect = field(default_factory=QRect)


SELECTED_ICONS = [
    '🦁', '🐯', '🐻', '🐼', '🍎', '🍊', '⚽', '🏀',
    '🎵', '🎸', '🚗', '✈️', '☀️', '❄️', '⌚', '💻',
    '🌲', '🌸', '🎮', '🎯', '📱', '🎬', '🧩', '🎭'
]


# ===================== STATE MACHINE =====================

class GameState(Enum):
    READY = 1          # hiçbir kart seçili değil
    ONE_FLIPPED = 2    # 1 kart açık
    CHECKING = 3       # 2 kart açıldı, kontrol bekleniyor (tıklama kilit)
    FINISHED = 4       # oyun bitti


# ===================== SCORE MANAGER =====================

class ScoreManager:
    """Skor sistemi - her kart adedi için ayrı skor."""
    DEFAULT_GRIDS = ('4x4', '4x6', '5x6', '4x8', '6x8')

    def __init__(self):
        self.scores_file = Path.home() / '.local' / 'share' / 'memory-game' / 'scores_steps.json'
        self.scores_file.parent.mkdir(parents=True, exist_ok=True)
        self.leaderboard = self.load_scores()

    def load_scores(self):
        if self.scores_file.exists():
            try:
                with open(self.scores_file, 'r', encoding='utf-8') as f:
                    data = json.load(f) or {}
                    for grid in self.DEFAULT_GRIDS:
                        data.setdefault(grid, [])
                    return data
            except (json.JSONDecodeError, OSError):
                return {grid: [] for grid in self.DEFAULT_GRIDS}
        return {grid: [] for grid in self.DEFAULT_GRIDS}

    def add_score(self, player_name, score, moves, matched_pairs, grid_size, duration_seconds, timestamp=None):
        """Skor ekle. UI mantığı değişmeden: top25'te mi kontrolü döndürür."""
        if grid_size not in self.leaderboard:
            self.leaderboard[grid_size] = []

        entry_id = uuid.uuid4().hex
        ts = float(timestamp) if timestamp is not None else datetime.now().timestamp()

        entry = {
            'id': entry_id,
            'name': player_name,
            'moves': int(moves),
            'matched': int(matched_pairs),
            'duration': int(duration_seconds),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'timestamp': ts
        }

        self.leaderboard[grid_size].append(entry)

        self.leaderboard[grid_size] = sorted(
            self.leaderboard[grid_size],
            key=lambda x: (x.get('moves', 10**9), x.get('duration', 10**9))
        )[:25]

        is_in_top = any(e.get('id') == entry_id for e in self.leaderboard[grid_size])

        try:
            with open(self.scores_file, 'w', encoding='utf-8') as f:
                json.dump(self.leaderboard, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Skor kaydında hata: {e}")

        return self.leaderboard[grid_size], is_in_top, entry_id

    def get_top_scores(self, grid_size='6x8'):
        return self.leaderboard.get(grid_size, [])


class RoundedBox(QFrame):
    """Yuvarlak kenarlı kutu."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rounded_box")
        self.setStyleSheet("QFrame#rounded_box { background: white; border: 1px solid #cccccc; border-radius: 8px; }")


# ===================== GAME WIDGET =====================

class GameWidget(QWidget):
    stats_changed = pyqtSignal()     # MainWindow update_stats bağlanır

    def __init__(self, player_name, score_manager, grid_size='6x8'):
        super().__init__()

        self.player_name = player_name
        self.score_manager = score_manager
        self.grid_size = grid_size

        self.rows, self.cols = self.parse_grid(grid_size)
        self.total_pairs = (self.rows * self.cols) // 2

        self.cards = []
        self.first_flipped = -1
        self.second_flipped = -1

        self.moves = 0
        self.matched_pairs = 0
        self.elapsed_seconds = 0

        self.state = GameState.READY

        # Sidebar / UI state
        self.reset_btn_rect = QRect()
        self.reset_btn_hover = False
        self.sidebar_width = 340
        self.sidebar_min_width = 250
        self.sidebar_max_width = 560
        self.sidebar_resize_margin = 20
        self.sidebar_resizing = False
        self.sidebar_collapsed = False
        self.top_panel_height = 9

        # leaderboard scroll (init)
        self.scroll_offset = 0
        self.max_scroll = 0

        # Background
        self.background_image = None
        self.blurred_background = None
        self.load_or_create_background()

        # Timers
        self.check_timer = QTimer(self)
        self.check_timer.setSingleShot(True)
        self.check_timer.timeout.connect(self.check_match)

        self.game_timer = QTimer(self)
        self.game_timer.setInterval(1000)
        self.game_timer.timeout.connect(self.tick_time)

        self.timer_running = False

        self.initialize_cards()
        self.setMinimumSize(1400, 900)

    def parse_grid(self, grid_size):
        sizes = {'4x4': (4, 4), '4x6': (4, 6), '5x6': (5, 6), '4x8': (4, 8), '6x8': (6, 8)}
        return sizes.get(grid_size, (6, 8))

    def load_or_create_background(self):
        pixmap = QPixmap(1200, 900)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        gradient = QLinearGradient(0, 0, 1200, 900)
        gradient.setColorAt(0.0, QColor(248, 250, 252))
        gradient.setColorAt(1.0, QColor(234, 240, 246))
        painter.fillRect(0, 0, 1200, 900, gradient)
        painter.end()
        self.background_image = pixmap
        self.blurred_background = pixmap.copy()

    def tick_time(self):
        self.elapsed_seconds += 1
        self.stats_changed.emit()
        self.update()

    def format_time(self):
        minutes, seconds = divmod(self.elapsed_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def initialize_cards(self):
        self.cards = []
        total_cards = self.rows * self.cols
        needed_pairs = total_cards // 2

        pair_ids = list(range(needed_pairs)) * 2
        random.shuffle(pair_ids)

        self.total_pairs = needed_pairs

        for i, pid in enumerate(pair_ids):
            icon = SELECTED_ICONS[pid]
            self.cards.append(Card(i, pid, icon))

        self.first_flipped = -1
        self.second_flipped = -1
        self.state = GameState.READY

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # sidebar
        if not self.sidebar_collapsed:
            bg_x = self.sidebar_width
            parent = self.window()
            hl_name = getattr(parent, 'highlight_name', None) if parent else None
            self.draw_modern_sidebar(painter, bg_x, hl_name)

        # cards
        bg_x = self.sidebar_width
        cols = self.cols
        rows = self.rows
        outer_padding = 9
        card_gap = 6
        cards_area_x = bg_x + outer_padding
        cards_area_y = self.top_panel_height + outer_padding
        cards_area_w = (self.width() - bg_x) - (outer_padding * 2)
        cards_area_h = (self.height() - self.top_panel_height) - (outer_padding * 2)

        card_w = max(10, (cards_area_w - (card_gap * (cols - 1))) // cols)
        card_h = max(10, (cards_area_h - (card_gap * (rows - 1))) // rows)
        start_x = cards_area_x
        start_y = cards_area_y

        for i, card in enumerate(self.cards):
            row, col = i // cols, i % cols
            x = start_x + col * (card_w + card_gap)
            y = start_y + row * (card_h + card_gap)

            card.rect = QRect(x, y, card_w, card_h)

            if card.is_matched:
                painter.setBrush(QColor(76, 175, 80))
            elif card.is_flipped:
                painter.setBrush(QColor(25, 118, 210))
            else:
                painter.setBrush(QColor("#ffffff"))

            painter.setPen(QPen(QColor("#cccccc"), 1))
            painter.drawRoundedRect(card.rect, 8, 8)

            if card.is_flipped or card.is_matched:
                painter.setFont(QFont("Arial", 48))
                painter.setPen(Qt.white)
                painter.drawText(card.rect, Qt.AlignCenter, card.icon)

        self.draw_top_panel(painter, bg_x)

    def draw_modern_sidebar(self, painter, width, highlight_name=None):
        if width > 0:
            bg_rect = QRect(0, 0, width, self.height())
            painter.setBrush(QColor("#f3f3f3"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bg_rect, 8, 8)

        leaderboard_box = QRect(4, 17, width - 8, self.height() - 29)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.drawRoundedRect(leaderboard_box, 8, 8)

        painter.setPen(QColor(25, 103, 210))
        painter.setFont(QFont("Segoe UI", 14, QFont.Bold))
        painter.drawText(15, 40, f"🏆 Sıralama ({self.grid_size})")

        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.drawLine(15, 48, width - 15, 48)

        painter.setPen(QColor(100, 100, 100))
        painter.setFont(QFont("Segoe UI", 9, QFont.Normal))
        moves_col_x = 190
        duration_col_x = 240
        painter.drawText(15, 66, "Sıra")
        painter.drawText(50, 66, "Oyuncu")
        painter.drawText(moves_col_x, 66, "Adım")
        painter.drawText(duration_col_x, 66, "Süre")

        scores = self.score_manager.get_top_scores(self.grid_size)

        visible_h = (self.height() - 29) - 86
        content_h = len(scores[:25]) * 25
        self.max_scroll = max(0, content_h - visible_h)
        self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))

        y_pos = 86 - self.scroll_offset

        painter.setFont(QFont("Segoe UI", 10, QFont.Normal))
        for rank, entry in enumerate(scores[:25], 1):
            if y_pos > self.height():
                break
            if y_pos < 70:
                y_pos += 25
                continue

            highlight_ts = entry.get('timestamp')
            if highlight_ts and highlight_name == highlight_ts:
                painter.fillRect(10, y_pos - 12, width - 20, 20, QColor("#4caf50"))
            elif rank % 2 == 0:
                painter.fillRect(10, y_pos - 12, width - 20, 20, QColor("#f3f3f3"))

            medals = ['🥇', '🥈', '🥉']
            medal = medals[rank - 1] if rank <= 3 else f"{rank}."

            painter.setPen(QColor(33, 33, 33))
            painter.drawText(15, y_pos, medal)

            name = entry.get('name', '')[:15]
            painter.drawText(50, y_pos, name)

            painter.setPen(QColor(25, 103, 210))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(moves_col_x, y_pos, str(entry.get('moves', '-')))

            painter.setPen(QColor(120, 120, 120))
            painter.setFont(QFont("Segoe UI", 9, QFont.Normal))
            painter.drawText(duration_col_x, y_pos, f"{entry.get('duration', 0)}sn")

            painter.setFont(QFont("Segoe UI", 10, QFont.Normal))
            painter.setPen(QColor(33, 33, 33))

            y_pos += 25

    def wheelEvent(self, event):
        if self.sidebar_collapsed:
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.scroll_offset = max(0, self.scroll_offset - 25)
        else:
            self.scroll_offset = min(self.max_scroll, self.scroll_offset + 25)
        self.update()

    def clamp_sidebar_width(self, desired_width):
        max_width = min(self.sidebar_max_width, self.width() - 360)
        max_width = max(max_width, self.sidebar_min_width)
        return max(self.sidebar_min_width, min(desired_width, max_width))

    def is_on_sidebar_edge(self, pos):
        if self.sidebar_collapsed:
            return False
        return abs(pos.x() - self.sidebar_width) <= self.sidebar_resize_margin

    def draw_top_panel(self, painter, bg_x):
        panel_height = self.top_panel_height
        if self.sidebar_collapsed:
            painter.fillRect(0, 0, self.width(), panel_height, QColor("#f3f3f3"))
        else:
            painter.fillRect(bg_x, 0, self.width() - bg_x, panel_height, QColor("#f3f3f3"))

    # ===== Input / Game flow =====

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_on_sidebar_edge(event.pos()):
            self.sidebar_resizing = True
            self.setCursor(Qt.SizeHorCursor)
            return

        if self.reset_btn_rect.contains(event.pos()):
            self.reset_game()
            return

        if self.state in (GameState.CHECKING, GameState.FINISHED):
            return

        for i, card in enumerate(self.cards):
            if card.rect.contains(event.pos()) and not card.is_flipped and not card.is_matched:
                card.is_flipped = True

                if self.state == GameState.READY:
                    self.first_flipped = i
                    self.state = GameState.ONE_FLIPPED

                elif self.state == GameState.ONE_FLIPPED:
                    self.second_flipped = i
                    self.moves += 1

                    if not self.timer_running:
                        self.game_timer.start()
                        self.timer_running = True

                    self.state = GameState.CHECKING
                    self.check_timer.start(1000)

                self.stats_changed.emit()
                self.update()
                return

    def mouseMoveEvent(self, event):
        if self.sidebar_resizing:
            self.sidebar_width = self.clamp_sidebar_width(event.pos().x())
            self.update()
            return

        if self.is_on_sidebar_edge(event.pos()):
            self.setCursor(Qt.SizeHorCursor)
            return

        hover = self.reset_btn_rect.contains(event.pos())
        if hover != self.reset_btn_hover:
            self.reset_btn_hover = hover
            self.setCursor(Qt.PointingHandCursor if hover else Qt.ArrowCursor)
            self.update()
        elif not hover:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.sidebar_resizing:
            self.sidebar_resizing = False
            self.setCursor(Qt.ArrowCursor)

    def check_match(self):
        if self.state != GameState.CHECKING:
            return
        if self.first_flipped == -1 or self.second_flipped == -1:
            self.state = GameState.READY
            return

        first_card = self.cards[self.first_flipped]
        second_card = self.cards[self.second_flipped]

        if first_card.pair_id == second_card.pair_id:
            first_card.is_matched = True
            second_card.is_matched = True
            self.matched_pairs += 1

            if self.matched_pairs == self.total_pairs:
                self.finish_game()
        else:
            first_card.is_flipped = False
            second_card.is_flipped = False

        self.first_flipped = -1
        self.second_flipped = -1

        if self.state != GameState.FINISHED:
            self.state = GameState.READY

        self.stats_changed.emit()
        self.update()

    def finish_game(self):
        self.state = GameState.FINISHED
        if self.timer_running:
            self.game_timer.stop()
            self.timer_running = False
        self.save_and_show_result()

    def save_and_show_result(self):
        game_timestamp = datetime.now().timestamp()

        _, is_in_top, _entry_id = self.score_manager.add_score(
            self.player_name,
            0,
            self.moves,
            self.matched_pairs,
            self.grid_size,
            self.elapsed_seconds,
            game_timestamp
        )

        if is_in_top:
            result_text = f"""
Tebrikler {self.player_name}!

🎯 Toplam Adımlar: {self.moves}
✨ Eşleştirmeler: {self.matched_pairs}/{self.total_pairs}
⏱ Süre: {self.format_time()}

📊 {self.grid_size} Sıralamaya Kaydedildi!
"""
        else:
            result_text = f"""
Tebrikler {self.player_name}!

🎯 Toplam Adımlar: {self.moves}
✨ Eşleştirmeler: {self.matched_pairs}/{self.total_pairs}
⏱ Süre: {self.format_time()}

⚠️ {self.grid_size} Sıralamasına Giremedin!
"""

        parent = self.window()
        if parent:
            if is_in_top:
                parent.highlight_name = game_timestamp
                parent.update()
            parent.show_completion(result_text)

    def reset_game(self):
        self.moves = 0
        self.matched_pairs = 0
        self.elapsed_seconds = 0

        self.state = GameState.READY

        if self.timer_running:
            self.game_timer.stop()
            self.timer_running = False

        if self.check_timer.isActive():
            self.check_timer.stop()

        self.first_flipped = -1
        self.second_flipped = -1

        self.initialize_cards()
        self.stats_changed.emit()
        self.update()


# ===================== MAIN WINDOW =====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.grid_size = '6x8'

        self.player_name = self.get_player_name()
        if not self.player_name:
            sys.exit(0)

        self.setWindowTitle(f"Bellek Oyunu - {self.player_name} - {self.grid_size}")
        self.setGeometry(50, 50, 1400, 900)
        self.setWindowIcon(load_app_icon())
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QMenuBar { background-color: #f3f3f3; border-bottom: 1px solid #cccccc; }
            QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
            QMenuBar::item:selected { background: #e6e6e6; }
            QMenu { background-color: #f3f3f3; border: 1px solid #cccccc; }
            QMenu::item { padding: 6px 18px; }
            QMenu::item:selected { background-color: #e6e6e6; color: #222222; }
        """)

        # skor / sidebar state
        self.score_manager = ScoreManager()
        self.sidebar_collapsed = False
        self.sidebar_width = 340
        self.highlight_name = None

        self.info_panel = self.create_info_panel()
        self.game_widget = GameWidget(self.player_name, self.score_manager, self.grid_size)

        self.game_widget.sidebar_collapsed = self.sidebar_collapsed
        self.game_widget.sidebar_width = self.sidebar_width

        # sağlam stats update: signal
        self.game_widget.stats_changed.connect(self.update_stats)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.info_panel)
        main_layout.addWidget(self.game_widget)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        self.update_stats()

    def create_info_panel(self):
        ribbon = RibbonBar(self)

        # hover helper (sip-safe: event handler void döner)
        def set_hover(w, on):
            w.setStyleSheet("background: #eaeaea; border-radius: 4px;" if on else "background: white; border-radius: 4px;")
            w.update()

        def bind_hover(widget, on_enter, on_leave):
            def _enter(e):
                on_enter()
                e.accept()
            def _leave(e):
                on_leave()
                e.accept()
            widget.enterEvent = _enter
            widget.leaveEvent = _leave
            widget.setAttribute(Qt.WA_Hover)

        # ---- 1. kutu: butonlar + grid ----
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setStretch(0, 1)
        btn_layout.setStretch(1, 1)
        btn_layout.setStretch(2, 1)
        btn_layout.setStretch(3, 1)

        # Yeni Oyun
        btn1 = QWidget()
        btn1.setObjectName("toolbar_btn")
        btn1.setFixedHeight(50)
        v = QVBoxLayout(btn1)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("1.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("▶")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        txt = QLabel("Yeni Oyun")
        txt.setAlignment(Qt.AlignCenter)
        txt.setFixedHeight(16)
        txt.setStyleSheet("font-size: 10px;")
        v.addWidget(lbl)
        v.addWidget(txt)
        btn1.mousePressEvent = lambda e: self.new_game()
        bind_hover(btn1, lambda: set_hover(btn1, True), lambda: set_hover(btn1, False))
        btn_layout.addWidget(btn1)

        # Yeniden
        item2 = QWidget()
        item2.setObjectName("toolbar_btn")
        item2.setFixedHeight(50)
        v = QVBoxLayout(item2)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("2.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("↻")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        txt = QLabel("Yeniden")
        txt.setAlignment(Qt.AlignCenter)
        txt.setFixedHeight(16)
        txt.setStyleSheet("font-size: 10px;")
        v.addWidget(lbl)
        v.addWidget(txt)
        item2.mousePressEvent = lambda e: self.restart_game()
        bind_hover(item2, lambda: set_hover(item2, True), lambda: set_hover(item2, False))
        btn_layout.addWidget(item2)

        # Skorları Sıfırla
        item3 = QWidget()
        item3.setObjectName("toolbar_btn")
        item3.setFixedHeight(50)
        v = QVBoxLayout(item3)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("3.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("✕")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        txt = QLabel("Skorları Sıfırla")
        txt.setAlignment(Qt.AlignCenter)
        txt.setFixedHeight(16)
        txt.setStyleSheet("font-size: 10px;")
        v.addWidget(lbl)
        v.addWidget(txt)
        item3.mousePressEvent = lambda e: self.reset_scores()
        bind_hover(item3, lambda: set_hover(item3, True), lambda: set_hover(item3, False))
        btn_layout.addWidget(item3)

        # Kart Adedi
        btn4 = QWidget()
        btn4.setMinimumHeight(50)
        btn4.setMaximumHeight(50)
        v = QVBoxLayout(btn4)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("4.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("▦")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)

        self.grid_combo = QComboBox()
        self.grid_combo.setFixedHeight(22)
        self.grid_combo.setStyleSheet("font-size: 12px; background: white;")
        self.grid_combo.addItems(["4x4", "4x6", "5x6", "4x8", "6x8"])
        self.grid_combo.setCurrentText(self.grid_size)
        self.grid_combo.currentTextChanged.connect(self.change_grid_size)

        v.addWidget(lbl)
        v.addWidget(self.grid_combo)
        bind_hover(btn4, lambda: set_hover(btn4, True), lambda: set_hover(btn4, False))
        btn_layout.addWidget(btn4)

        # ---- Player + stats kutusu ----
        player_btn = QWidget()
        player_btn.setObjectName("toolbar_btn")
        player_btn.setFixedHeight(50)
        v = QVBoxLayout(player_btn)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("5.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("👤")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        self.name_edit = QLineEdit()
        self.name_edit.setText(self.player_name)
        self.name_edit.setFixedHeight(22)
        self.name_edit.setStyleSheet("padding: 0 2px; font-size: 12px; background: white;")
        self.name_edit.returnPressed.connect(lambda: self.change_name(self.name_edit.text()))
        v.addWidget(lbl)
        v.addWidget(self.name_edit)
        bind_hover(player_btn, lambda: set_hover(player_btn, True), lambda: set_hover(player_btn, False))

        # Moves
        moves_btn = QWidget()
        moves_btn.setObjectName("toolbar_btn")
        moves_btn.setFixedHeight(50)
        moves_btn.setFixedWidth(70)
        v = QVBoxLayout(moves_btn)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("6.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("👣")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        self.lbl_moves = QLabel("0")
        self.lbl_moves.setAlignment(Qt.AlignCenter)
        self.lbl_moves.setFixedHeight(22)
        self.lbl_moves.setStyleSheet("font-size: 12px;")
        v.addWidget(lbl)
        v.addWidget(self.lbl_moves)
        bind_hover(moves_btn, lambda: set_hover(moves_btn, True), lambda: set_hover(moves_btn, False))

        # Matches
        matches_btn = QWidget()
        matches_btn.setObjectName("toolbar_btn")
        matches_btn.setFixedHeight(50)
        matches_btn.setFixedWidth(70)
        v = QVBoxLayout(matches_btn)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("7.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("✓")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        self.lbl_matches = QLabel("0/0")
        self.lbl_matches.setAlignment(Qt.AlignCenter)
        self.lbl_matches.setFixedHeight(22)
        self.lbl_matches.setStyleSheet("font-size: 12px;")
        v.addWidget(lbl)
        v.addWidget(self.lbl_matches)
        bind_hover(matches_btn, lambda: set_hover(matches_btn, True), lambda: set_hover(matches_btn, False))

        # Time
        time_btn = QWidget()
        time_btn.setObjectName("toolbar_btn")
        time_btn.setFixedHeight(50)
        time_btn.setFixedWidth(70)
        v = QVBoxLayout(time_btn)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("8.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("⏱")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        self.lbl_time = QLabel("00:00")
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.lbl_time.setFixedHeight(22)
        self.lbl_time.setStyleSheet("font-size: 12px;")
        v.addWidget(lbl)
        v.addWidget(self.lbl_time)
        bind_hover(time_btn, lambda: set_hover(time_btn, True), lambda: set_hover(time_btn, False))

        # Toggle sidebar
        toggle_btn = QWidget()
        toggle_btn.setObjectName("toolbar_btn")
        toggle_btn.setFixedHeight(50)
        toggle_btn.setFixedWidth(50)
        v = QVBoxLayout(toggle_btn)
        v.setSpacing(2)
        v.setContentsMargins(4, 2, 4, 2)
        icon = load_icon("9.svg")
        lbl = QLabel()
        if icon and not icon.isNull():
            lbl.setPixmap(icon)
        else:
            lbl.setText("◀")
            lbl.setStyleSheet("font-size: 20px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(22)
        txt = QLabel("Sıralama")
        txt.setAlignment(Qt.AlignCenter)
        txt.setFixedHeight(16)
        txt.setStyleSheet("font-size: 10px;")
        v.addWidget(lbl)
        v.addWidget(txt)

        def toggle_sidebar():
            self.sidebar_collapsed = not self.sidebar_collapsed
            if self.sidebar_collapsed:
                self.sidebar_width = 0
                set_hover(toggle_btn, True)
            else:
                self.sidebar_width = 340
                set_hover(toggle_btn, False)

            if hasattr(self, 'game_widget') and self.game_widget:
                self.game_widget.sidebar_collapsed = self.sidebar_collapsed
                self.game_widget.sidebar_width = self.sidebar_width
                self.game_widget.update()

            self.update()

        toggle_btn.mousePressEvent = lambda e: toggle_sidebar()

        def toggle_enter():
            set_hover(toggle_btn, True)

        def toggle_leave():
            # collapsed ise hover açık kalsın
            set_hover(toggle_btn, True if self.sidebar_collapsed else False)

        bind_hover(toggle_btn, toggle_enter, toggle_leave)

        # ---- Ana layout (3 kutu) ----
        layout = QHBoxLayout(ribbon)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addWidget(self.create_kutu(btn_container))

        player_stats = QHBoxLayout()
        player_stats.setSpacing(8)
        player_stats.addWidget(player_btn)
        player_stats.addWidget(moves_btn)
        player_stats.addWidget(matches_btn)
        player_stats.addWidget(time_btn)

        content = QWidget()
        content.setLayout(player_stats)
        layout.addWidget(self.create_kutu(content))

        layout.addWidget(self.create_kutu(toggle_btn))
        layout.addStretch()

        return ribbon

    def create_kutu(self, widget):
        box = RoundedBox()
        if widget:
            v_layout = QVBoxLayout(box)
            v_layout.setContentsMargins(4, 0, 4, 2)
            v_layout.setSpacing(0)
            if isinstance(widget, QLayout):
                content = QWidget()
                content.setLayout(widget)
                v_layout.addWidget(content)
            else:
                v_layout.addWidget(widget)
        return box

    def update_stats(self):
        if self.game_widget:
            gw = self.game_widget
            self.lbl_moves.setText(str(gw.moves))
            self.lbl_matches.setText(f"{gw.matched_pairs}/{gw.total_pairs}")
            self.lbl_time.setText(gw.format_time())

    def new_game(self):
        name, ok = input_dialog(self, "🆕 Yeni Oyun", "Oyuncu adı:", self.player_name)
        if ok and name.strip():
            self.player_name = name.strip()
            self.restart_game()

    def restart_game(self):
        self.highlight_name = None
        self.update()

        main = self.centralWidget().layout()
        old = main.itemAt(1).widget()
        if old:
            old.deleteLater()

        self.game_widget = GameWidget(self.player_name, self.score_manager, self.grid_size)
        self.game_widget.sidebar_collapsed = self.sidebar_collapsed
        self.game_widget.sidebar_width = self.sidebar_width
        self.game_widget.stats_changed.connect(self.update_stats)

        main.insertWidget(1, self.game_widget)

        self.name_edit.setText(self.player_name)
        self.setWindowTitle(f"Bellek Oyunu - {self.player_name} - {self.grid_size}")
        self.update_stats()

    def reset_scores(self):
        reply = QMessageBox.question(
            self, "Skorları Sıfırla",
            "Tüm skorları silmek istediğinize emin misiniz?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.score_manager.leaderboard = {grid: [] for grid in self.score_manager.DEFAULT_GRIDS}
            try:
                with open(self.score_manager.scores_file, 'w', encoding='utf-8') as f:
                    json.dump(self.score_manager.leaderboard, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            self.highlight_name = None
            self.update()
            if self.game_widget:
                self.game_widget.update()

    def change_grid_size(self, grid_size):
        self.grid_size = grid_size
        self.restart_game()

    def change_name(self, new_name=None):
        if new_name is None:
            name, ok = input_dialog(self, "👤 Oyuncu", "Yeni isminiz:", self.player_name)
            if ok and name.strip():
                new_name = name.strip()

        if new_name and new_name.strip():
            self.player_name = new_name.strip()
            self.setWindowTitle(f"Bellek Oyunu - {self.player_name} - {self.grid_size}")
            self.name_edit.setText(self.player_name)
            if self.game_widget:
                self.game_widget.player_name = self.player_name
                self.game_widget.update()

    def get_player_name(self):
        name, ok = input_dialog(None, "🎮 Hoş Geldiniz", "Adınızı girin:", "Oyuncu")
        if ok and name.strip():
            return name.strip()
        return None

    def show_completion(self, message):
        QMessageBox.information(self, "✅ Oyun Bitti!", message)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
