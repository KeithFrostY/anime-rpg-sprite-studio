from pathlib import Path
import sys


def resource_path(relative):
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Resource path escapes application")
    return path


def install_exception_handler():
    def handle(exc_type, value, traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "操作未完成", "發生未預期錯誤。請保留目前專案並重新開啟程式。\n若涉及 AI 請求，請先檢查未決帳本，不要直接重新生成。")
    sys.excepthook = handle
