import flet as ft

from app.ui.app import main

if __name__ == "__main__":
    # flet 0.28 uses ft.app; newer releases renamed it to ft.run
    (ft.run if hasattr(ft, "run") else ft.app)(main)
