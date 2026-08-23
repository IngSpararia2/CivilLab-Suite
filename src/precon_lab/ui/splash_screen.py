"""Pantalla de presentación de Prefabricados Lab."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QWidget,
)

from ..config import APP_NAME, BRAND_SOURCE_PATH


class AppSplashScreen(QWidget):
    """Presenta la marca durante dos segundos y anima el crédito a mitad del tiempo."""

    DISPLAY_DURATION_MS = 2000
    CREDIT_DELAY_MS = 1000
    CREDIT_ANIMATION_MS = 650
    WIDTH = 560
    HEIGHT = 630

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("AppSplashScreen")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet("QWidget#AppSplashScreen { background: #0b2948; }")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.logo_label = QLabel(self)
        self.logo_label.setGeometry(25, 20, 510, 510)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setAccessibleName(f"Logo de {APP_NAME}")
        if BRAND_SOURCE_PATH.exists():
            logo = QPixmap(str(BRAND_SOURCE_PATH))
            self.logo_label.setPixmap(
                logo.scaled(
                    self.logo_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.credit_label = QLabel("Developed by Ing. Samuel Parariá", self)
        self.credit_label.setGeometry(30, 548, 500, 48)
        self.credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.credit_label.setStyleSheet(
            "color: #ffffff; font-size: 14pt; font-weight: 600; "
            "background: transparent; letter-spacing: 0.3px;"
        )
        self.credit_label.setAccessibleName("Crédito del desarrollador")

        self.credit_opacity = QGraphicsOpacityEffect(self.credit_label)
        self.credit_opacity.setOpacity(0.0)
        self.credit_label.setGraphicsEffect(self.credit_opacity)
        self.credit_animation = QPropertyAnimation(self.credit_opacity, b"opacity", self)
        self.credit_animation.setDuration(self.CREDIT_ANIMATION_MS)
        self.credit_animation.setStartValue(0.0)
        self.credit_animation.setEndValue(1.0)
        self.credit_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def start_credit_animation(self) -> None:
        self.credit_animation.start()

    def schedule_credit_animation(self) -> None:
        QTimer.singleShot(self.CREDIT_DELAY_MS, self.start_credit_animation)

    def showEvent(self, event) -> None:  # noqa: N802
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())
        super().showEvent(event)

    def finish(self, _main_window: QWidget) -> None:
        self.close()
