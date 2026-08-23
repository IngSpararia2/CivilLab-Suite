from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class StartupSplash(QWidget):
    """Two-stage startup presentation for the Concretos Lab brand."""

    def __init__(self, logo_path: Path):
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("StartupSplash")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 560)

        panel = QFrame()
        panel.setObjectName("SplashPanel")
        panel.setStyleSheet(
            "QFrame#SplashPanel { background:#050607; border:1px solid #4b5563; "
            "border-radius:24px; }"
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 24)
        panel_layout.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setAccessibleName("Logo de Concretos Lab")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(
                pixmap.scaled(
                    450,
                    450,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.credit = QLabel("Developed by Ing. Samuel Parariá")
        self.credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.credit.setStyleSheet(
            "color:#f8fafc; font-size:13pt; font-weight:600; padding:8px;"
        )
        self.credit_effect = QGraphicsOpacityEffect(self.credit)
        self.credit_effect.setOpacity(0.0)
        self.credit.setGraphicsEffect(self.credit_effect)

        self.credit_animation = QPropertyAnimation(
            self.credit_effect, b"opacity", self
        )
        self.credit_animation.setDuration(650)
        self.credit_animation.setStartValue(0.0)
        self.credit_animation.setEndValue(1.0)
        self.credit_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        panel_layout.addWidget(logo, 1)
        panel_layout.addWidget(self.credit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

    def show_centered(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self.show()
        self.raise_()

    def reveal_credit(self) -> None:
        self.credit_animation.start()
