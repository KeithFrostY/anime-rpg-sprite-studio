"""All automated tests are offline, including provider tests."""
import socket
import sys
import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not access the network")
    for name in ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg"):
        if hasattr(socket.socket, name):
            monkeypatch.setattr(socket.socket, name, forbidden)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    if sys.platform == "win32":
        from keyring.backends.Windows import WinVaultKeyring
        for method in ("get_password", "set_password", "delete_password"):
            monkeypatch.setattr(WinVaultKeyring, method, forbidden)
