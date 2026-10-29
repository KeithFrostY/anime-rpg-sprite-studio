from pathlib import Path


class Vault:
    def __init__(self):
        self.value = None
    def get_password(self, *args):
        return self.value
    def set_password(self, service, name, value):
        self.value = value
    def delete_password(self, *args):
        self.value = None


def session(tmp_path):
    from anime_rpg_sprite_studio.ai.session import AISession
    from anime_rpg_sprite_studio.security.credentials import WindowsCredentialManager
    return AISession(tmp_path, credentials=WindowsCredentialManager(Vault()))


def test_mock_dialog_is_offline_and_does_not_require_key(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ai_dialog import AIDialog
    s = session(tmp_path)
    d = AIDialog(s)
    qtbot.addWidget(d)
    d.show()
    assert d.provider.currentIndex() == 0
    d.prompt.setPlainText("hero")
    d.generate_mock()
    qtbot.waitUntil(lambda: not d.busy)
    assert d.candidate is not None and s.budget.list_requests() == []
    assert "Mock" in d.candidate_label.text()
    assert not d.submit_button.isEnabled()
    d.reject()


def test_key_dialog_is_masked_and_only_uses_injected_vault(qtbot, tmp_path):
    from PySide6.QtWidgets import QLineEdit
    from anime_rpg_sprite_studio.ui.credentials_dialog import CredentialsDialog
    s = session(tmp_path)
    d = CredentialsDialog(s)
    qtbot.addWidget(d)
    assert d.key_input.echoMode() == QLineEdit.EchoMode.Password
    d.key_input.setText("FAKE-GUI-KEY")
    d.save_key()
    assert not d.key_input.text()
    assert s.credentials.has_key("fal")
    d.delete_key()
    assert not s.credentials.has_key("fal")
    assert not any("FAKE-GUI-KEY" in p.read_text(errors="ignore") for p in Path(tmp_path).rglob("*") if p.is_file())


def test_paid_gui_requires_yes_and_never_reuses_confirmation(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.ai_dialog import AIDialog
    from anime_rpg_sprite_studio.ai.session import AISession
    from anime_rpg_sprite_studio.security.credentials import WindowsCredentialManager
    from test_phase5_provider import FakeHttp
    vault = Vault()
    vault.value = "FAKE-GUI-KEY"
    http = FakeHttp()
    s = AISession(tmp_path, credentials=WindowsCredentialManager(vault), http=http)
    d = AIDialog(s)
    qtbot.addWidget(d)
    d.provider.setCurrentIndex(1)
    d.prompt.setPlainText("test hero")
    d.get_quote()
    qtbot.waitUntil(lambda: not d.busy)
    assert d.submit_button.isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    d.submit_paid()
    assert not s.budget.list_requests() and not any(c[0] == "POST" for c in http.calls)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    d.submit_paid()
    qtbot.waitUntil(lambda: not d.busy)
    assert len(s.budget.list_requests()) == 1
    assert s.budget.list_requests()[0]["actual"] is None
    d.submit_paid()
    assert len([c for c in http.calls if c[0] == "POST"]) == 1
    d.prompt.setPlainText("new prompt")
    assert d.quote is None and not d.submit_button.isEnabled()
    d.reject()
