import pytest


class FakeVault:
    def __init__(self):
        self.value = None
    def set_password(self, service, username, password):
        self.value = password
    def get_password(self, service, username):
        return self.value
    def delete_password(self, service, username):
        self.value = None


def test_credential_operations_and_provider_binding():
    from anime_rpg_sprite_studio.security.credentials import WindowsCredentialManager
    vault = FakeVault()
    c = WindowsCredentialManager(backend=vault)
    c.set_key("fal", "FAKE-KEY-FOR-TEST")
    assert c.has_key("fal")
    assert c.get_key_for_provider("fal") == "FAKE-KEY-FOR-TEST"
    with pytest.raises(ValueError):
        c.get_key_for_provider("other")
    c.delete_key("fal")
    assert not c.has_key("fal")


def test_vault_errors_never_echo_secret():
    from anime_rpg_sprite_studio.security.credentials import WindowsCredentialManager
    class Broken(FakeVault):
        def set_password(self, *args):
            raise RuntimeError("FAKE-SECRET-IN-EXCEPTION")
    with pytest.raises(ValueError) as exc:
        WindowsCredentialManager(backend=Broken()).set_key("fal", "FAKE-SECRET-IN-EXCEPTION")
    assert "FAKE-SECRET" not in str(exc.value)


@pytest.mark.parametrize("url,auth", [("http://api.fal.ai/a", True), ("https://evil.test/a", True),
    ("https://api.fal.ai.evil.test/a", True), ("https://api.fal.ai@evil.test/a", True),
    ("https://fal.media/a", True), ("https://evil.test/a", False), ("https://api.fal.ai:444/a", True)])
def test_transport_rejects_unsafe_urls_before_network(url, auth):
    from anime_rpg_sprite_studio.ai.http import validate_url
    with pytest.raises(ValueError):
        validate_url(url, authenticated=auth)


def test_http_redirect_is_not_followed_and_error_does_not_echo_key(monkeypatch):
    import anime_rpg_sprite_studio.ai.http as module
    from urllib.error import HTTPError
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise HTTPError("https://evil.test/FAKE-SECRET", 302, "FAKE-SECRET", {}, None)
    monkeypatch.setattr(module, "build_opener", lambda *a: Opener())
    with pytest.raises(ValueError) as exc:
        module.SafeHttp().json("GET", "https://api.fal.ai/v1/models/pricing", key="FAKE-SECRET")
    assert len(calls) == 1 and "FAKE-SECRET" not in str(exc.value)
    assert module.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test") is None
