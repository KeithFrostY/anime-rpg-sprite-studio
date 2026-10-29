"""Lazy, explicit Windows Credential Manager backend; never plaintext fallback."""
import os


class WindowsCredentialManager:
    def __init__(self, backend=None):
        self._backend = backend

    def _vault(self):
        if self._backend is None:
            if os.name != "nt":
                raise ValueError("需要 Windows Credential Manager")
            try:
                from keyring.backends.Windows import WinVaultKeyring
                self._backend = WinVaultKeyring()
            except Exception:
                raise ValueError("Windows 安全憑證儲存不可用；不會改用明文") from None
        return self._backend

    def _check(self, provider_id):
        if provider_id != "fal":
            raise ValueError("憑證僅供指定的 fal.ai Provider 使用")

    def set_key(self, provider_id, secret):
        self._check(provider_id)
        if not isinstance(secret, str) or not secret.strip() or any(c.isspace() for c in secret):
            raise ValueError("Key 不可空白或包含空白字元")
        try:
            self._vault().set_password("AnimeRpgSpriteStudio.fal", "api", secret)
        except Exception:
            raise ValueError("無法安全儲存 Key；不會改用明文") from None

    def get_key_for_provider(self, provider_id):
        self._check(provider_id)
        try:
            value = self._vault().get_password("AnimeRpgSpriteStudio.fal", "api")
        except Exception:
            raise ValueError("無法讀取 Windows 安全憑證") from None
        if not value:
            raise ValueError("尚未設定 fal.ai Key")
        return value

    def has_key(self, provider_id):
        self._check(provider_id)
        try:
            return bool(self._vault().get_password("AnimeRpgSpriteStudio.fal", "api"))
        except Exception:
            raise ValueError("無法讀取 Windows 安全憑證") from None

    def delete_key(self, provider_id):
        self._check(provider_id)
        try:
            vault = self._vault()
            if vault.get_password("AnimeRpgSpriteStudio.fal", "api"):
                vault.delete_password("AnimeRpgSpriteStudio.fal", "api")
        except Exception:
            raise ValueError("無法刪除 Windows 安全憑證") from None
