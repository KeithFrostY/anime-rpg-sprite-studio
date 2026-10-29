import sys
from PySide6.QtWidgets import QApplication
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Anime RPG Sprite Studio")
    from .runtime import install_exception_handler
    install_exception_handler()
    if "--self-test-report" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--self-test-report", required=True)
        parser.add_argument("--self-test-screenshot")
        options = parser.parse_args()
        from .selftest import run_self_test
        return run_self_test(app, options.self_test_report, options.self_test_screenshot)
    window = MainWindow()
    window.show()
    return app.exec()
