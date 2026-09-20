"""
VideoCutPub - Secure Multi-Account Manager (Étape 10)
Stores non-sensitive metadata in accounts.json and encrypts secrets (client_secret,
access_token, refresh_token) securely via Windows Credential Manager (keyring)
or local machine-bound encrypted vault. Never stores plaintext secrets.
"""

import json
import os
import sys
import base64
import ctypes
from pathlib import Path
from typing import Optional, List, Dict, Any

from publishing.publishing_models import PublishPlatform, AccountMetadata, AccountCredentials

KEYRING_SERVICE_NAME = "VideoCutPub_Publishing"


class SecureVaultFallback:
    """
    Fallback de chiffrement local lié à la machine Windows (DPAPI)
    utilisé si le backend keyring principal est indisponible.
    """
    @staticmethod
    def _dpapi_protect(data_bytes: bytes) -> bytes:
        if sys.platform == "win32":
            try:
                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

                crypt32 = ctypes.windll.crypt32
                kernel32 = ctypes.windll.kernel32

                in_blob = DATA_BLOB(len(data_bytes), ctypes.create_string_buffer(data_bytes, len(data_bytes)))
                out_blob = DATA_BLOB()

                if crypt32.CryptProtectData(ctypes.byref(in_blob), "VideoCutPub", None, None, None, 0, ctypes.byref(out_blob)):
                    encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                    kernel32.LocalFree(out_blob.pbData)
                    return encrypted
            except Exception:
                pass
        # Fallback basique avec masque machine
        mask = (os.environ.get("COMPUTERNAME", "VCP") + os.environ.get("USERNAME", "USER")).encode("utf-8")
        return bytes(b ^ mask[i % len(mask)] for i, b in enumerate(data_bytes))

    @staticmethod
    def _dpapi_unprotect(data_bytes: bytes) -> bytes:
        if sys.platform == "win32":
            try:
                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

                crypt32 = ctypes.windll.crypt32
                kernel32 = ctypes.windll.kernel32

                in_blob = DATA_BLOB(len(data_bytes), ctypes.create_string_buffer(data_bytes, len(data_bytes)))
                out_blob = DATA_BLOB()

                if crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
                    decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                    kernel32.LocalFree(out_blob.pbData)
                    return decrypted
            except Exception:
                pass
        mask = (os.environ.get("COMPUTERNAME", "VCP") + os.environ.get("USERNAME", "USER")).encode("utf-8")
        return bytes(b ^ mask[i % len(mask)] for i, b in enumerate(data_bytes))


class AccountManager:
    """
    Gestionnaire sécurisé des comptes multi-plateformes.
    Sépare strictement les métadonnées publiques des secrets sensibles.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd() / ".credentials"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.base_dir / "accounts.json"
        self._ensure_gitignore_protection()
        self._init_metadata_file()

    def _ensure_gitignore_protection(self) -> None:
        """Garantit la présence d'un .gitignore local dans le répertoire des credentials."""
        local_gitignore = self.base_dir / ".gitignore"
        if not local_gitignore.exists():
            local_gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    def _init_metadata_file(self) -> None:
        if not self.metadata_file.exists():
            self.metadata_file.write_text("[]", encoding="utf-8")

    def _load_metadata_list(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.metadata_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_metadata_list(self, items: List[Dict[str, Any]]) -> None:
        self.metadata_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    def _store_secrets(self, account_id: str, secrets_dict: Dict[str, Any]) -> None:
        """Enregistre les secrets dans Windows Credential Manager ou vault chiffré."""
        payload_str = json.dumps(secrets_dict, ensure_ascii=False)
        saved = False
        try:
            import keyring
            keyring.set_password(KEYRING_SERVICE_NAME, account_id, payload_str)
            saved = True
        except Exception:
            saved = False

        if not saved:
            # Fallback vers DPAPI chiffré
            vault_file = self.base_dir / f".vault_{account_id}.bin"
            enc = SecureVaultFallback._dpapi_protect(payload_str.encode("utf-8"))
            vault_file.write_bytes(enc)

    def _retrieve_secrets(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Récupère et déchiffre les secrets d'un compte."""
        try:
            import keyring
            pw = keyring.get_password(KEYRING_SERVICE_NAME, account_id)
            if pw:
                return json.loads(pw)
        except Exception:
            pass

        vault_file = self.base_dir / f".vault_{account_id}.bin"
        if vault_file.exists():
            try:
                dec = SecureVaultFallback._dpapi_unprotect(vault_file.read_bytes())
                return json.loads(dec.decode("utf-8"))
            except Exception:
                pass
        return None

    def _delete_secrets(self, account_id: str) -> None:
        """Supprime définitivement les secrets du gestionnaire d'identification."""
        try:
            import keyring
            keyring.delete_password(KEYRING_SERVICE_NAME, account_id)
        except Exception:
            pass

        vault_file = self.base_dir / f".vault_{account_id}.bin"
        if vault_file.exists():
            try:
                vault_file.unlink(missing_ok=True)
            except Exception:
                pass

    def add_account(
        self,
        credentials: AccountCredentials,
        is_active: bool = True,
        extra_info: Optional[Dict[str, Any]] = None
    ) -> AccountMetadata:
        """
        Enregistre un compte : sépare secrets et métadonnées.
        """
        meta_list = self._load_metadata_list()
        # Supprimer ancienne entrée si existante
        meta_list = [m for m in meta_list if m.get("account_id") != credentials.account_id]

        meta = AccountMetadata(
            account_id=credentials.account_id,
            platform=credentials.platform,
            display_name=credentials.display_name,
            is_active=is_active,
            extra_info=extra_info or {}
        )
        meta_list.append(meta.model_dump())
        self._save_metadata_list(meta_list)

        # Sauvegarde sécurisée des secrets sensibles
        secrets = {
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "access_token": credentials.access_token,
            "refresh_token": credentials.refresh_token,
            "token_expiry": credentials.token_expiry,
            "scopes": credentials.scopes
        }
        self._store_secrets(credentials.account_id, secrets)

        return meta

    def get_account_credentials(self, account_id: str) -> Optional[AccountCredentials]:
        """
        Reconstitue les credentials complètes d'un compte à partir de ses métadonnées
        et de ses secrets déchiffrés.
        """
        meta_list = self._load_metadata_list()
        meta_dict = next((m for m in meta_list if m.get("account_id") == account_id), None)
        if not meta_dict:
            return None

        secrets = self._retrieve_secrets(account_id) or {}

        return AccountCredentials(
            account_id=meta_dict["account_id"],
            platform=PublishPlatform(meta_dict["platform"]),
            display_name=meta_dict["display_name"],
            client_id=secrets.get("client_id"),
            client_secret=secrets.get("client_secret"),
            access_token=secrets.get("access_token"),
            refresh_token=secrets.get("refresh_token"),
            token_expiry=secrets.get("token_expiry"),
            scopes=secrets.get("scopes", [])
        )

    def update_tokens(
        self,
        account_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[str] = None
    ) -> bool:
        """Met à jour les jetons OAuth2 sans toucher aux autres propriétés."""
        secrets = self._retrieve_secrets(account_id)
        if secrets is None:
            return False

        secrets["access_token"] = access_token
        if refresh_token:
            secrets["refresh_token"] = refresh_token
        if token_expiry:
            secrets["token_expiry"] = token_expiry

        self._store_secrets(account_id, secrets)
        return True

    def list_accounts(self, platform: Optional[PublishPlatform] = None) -> List[AccountMetadata]:
        """Liste tous les comptes enregistrés, filtrables par plateforme."""
        meta_list = self._load_metadata_list()
        result = []
        for m in meta_list:
            if platform is None or m.get("platform") == platform.value:
                result.append(AccountMetadata(**m))
        return result

    def remove_account(self, account_id: str) -> bool:
        """Supprime un compte et ses secrets sécurisés."""
        meta_list = self._load_metadata_list()
        initial_len = len(meta_list)
        meta_list = [m for m in meta_list if m.get("account_id") != account_id]
        if len(meta_list) < initial_len:
            self._save_metadata_list(meta_list)
            self._delete_secrets(account_id)
            return True
        return False
