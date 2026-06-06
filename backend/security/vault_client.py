"""
Vault Client — Sketch to Story platform, Phase 5.

Reads platform secrets from HashiCorp Vault (KV v2).

Called in app/config.py during app startup.  Returns a dict that the
Settings object uses to override defaults.

Secret path: ``secret/data/comic-platform/config``
Expected keys: minio_access_key, minio_secret_key, db_password, jwt_secret,
               webhook_secret

Dev fallback: if VAULT_ADDR is not set (CI, local dev without Vault running),
all values fall back to the corresponding environment variables.  This is
documented behaviour — do not rely on it in production.

Security rules:
  - Never log secret values — log key names only.
  - Never write secrets to globals or env vars (return dict only).
  - Root token is read from VAULT_TOKEN env var — never hardcoded.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expected secret keys
# ---------------------------------------------------------------------------
_SECRET_KEYS = (
    "minio_access_key",
    "minio_secret_key",
    "db_password",
    "jwt_secret",
    "webhook_secret",
)

# ---------------------------------------------------------------------------
# VaultClient
# ---------------------------------------------------------------------------


class VaultClient:
    """
    Reads secrets from HashiCorp Vault (KV v2, dev mode).

    Parameters
    ----------
    vault_addr:
        Vault server address.  Defaults to ``VAULT_ADDR`` env var or
        ``http://localhost:8200``.
    vault_token:
        Dev root token.  Defaults to ``VAULT_TOKEN`` env var.
    secret_path:
        KV v2 secret path (without ``secret/data/`` prefix).
        Defaults to ``comic-platform/config``.
    """

    def __init__(
        self,
        vault_addr: str | None = None,
        vault_token: str | None = None,
        secret_path: str = "comic-platform/config",
    ) -> None:
        self._vault_addr = vault_addr or os.environ.get(
            "VAULT_ADDR", "http://localhost:8200"
        )
        self._vault_token = vault_token or os.environ.get("VAULT_TOKEN", "")
        self._secret_path = secret_path

    def get_secrets(self) -> dict:
        """
        Fetch secrets from Vault.

        Returns a dict with keys from ``_SECRET_KEYS``.

        Falls back to environment variables if Vault is unreachable (dev
        convenience — document this in deployment runbook).  In production,
        VAULT_ADDR must be set and Vault must be reachable; if fallback is
        used in prod, a WARNING is logged.
        """
        if not os.environ.get("VAULT_ADDR"):
            logger.warning(
                "VaultClient: VAULT_ADDR not set — falling back to env vars. "
                "This is acceptable in CI/local-dev but must NOT happen in production."
            )
            return self._env_fallback()

        try:
            return self._fetch_from_vault()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "VaultClient: Vault unreachable (%s) — falling back to env vars. "
                "Ensure Vault is running in production.",
                exc,
            )
            return self._env_fallback()

    def _fetch_from_vault(self) -> dict:
        """Read the KV v2 secret via hvac."""
        try:
            import hvac
        except ImportError as exc:
            raise RuntimeError(
                "hvac is not installed. Add 'hvac' to requirements.txt."
            ) from exc

        if not self._vault_token:
            raise RuntimeError(
                "VAULT_TOKEN environment variable is not set. "
                "Cannot authenticate with Vault."
            )

        client = hvac.Client(url=self._vault_addr, token=self._vault_token)

        if not client.is_authenticated():
            raise RuntimeError(
                f"Vault authentication failed at {self._vault_addr}. "
                "Check VAULT_TOKEN."
            )

        response = client.secrets.kv.v2.read_secret_version(
            path=self._secret_path,
            mount_point="secret",
        )
        data: dict = response["data"]["data"]

        # Log key names only — never values.
        found_keys = [k for k in _SECRET_KEYS if k in data]
        missing_keys = [k for k in _SECRET_KEYS if k not in data]
        logger.info(
            "VaultClient: loaded keys=%s", found_keys
        )
        if missing_keys:
            logger.warning(
                "VaultClient: missing keys in Vault secret — %s", missing_keys
            )

        return {k: data.get(k, "") for k in _SECRET_KEYS}

    def _env_fallback(self) -> dict:
        """
        Read secrets from environment variables as a fallback.

        Env var names are upper-cased versions of the secret key names.
        e.g. ``minio_access_key`` → ``MINIO_ACCESS_KEY``.
        """
        result = {}
        for key in _SECRET_KEYS:
            env_name = key.upper()
            value = os.environ.get(env_name, "")
            if value:
                logger.debug("VaultClient: env fallback key=%s", key)
            else:
                logger.debug("VaultClient: env fallback key=%s (empty)", key)
            result[key] = value
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_vault_client: VaultClient | None = None


def get_vault_client() -> VaultClient:
    """Return the module-level VaultClient singleton."""
    global _vault_client
    if _vault_client is None:
        _vault_client = VaultClient()
    return _vault_client
