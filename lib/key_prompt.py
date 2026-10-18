"""Runtime API-key entry — for keys that must never be stored.

The key is typed at the prompt, held in ``os.environ`` for the lifetime of the
process, and gone when it exits. It is never written to ``.env``, never passed
as a CLI argument (which would land in shell history and ``ps`` output), and
never echoed to the terminal.

A short liveness check runs before the caller starts work, so a typo fails in
two seconds rather than after a long job has already begun.
"""

from __future__ import annotations

import getpass
import os
import sys

# env var name → (human label, where to get one)
PROVIDER_KEYS: dict[str, tuple[str, str]] = {
    "gemini":     ("GEMINI_API_KEY",     "https://aistudio.google.com/app/apikey"),
    "groq":       ("GROQ_API_KEY",       "https://console.groq.com/keys"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/settings/keys"),
    "openai":     ("OPENAI_API_KEY",     "https://platform.openai.com/api-keys"),
}

_VALIDATION_TIMEOUT = 20.0


class KeyPromptError(RuntimeError):
    """Raised when a key cannot be obtained or fails validation."""


def _has_terminal() -> bool:
    """True when a hidden prompt is possible.

    getpass falls back to /dev/tty when stdin is redirected, so stdin alone is
    not the whole story — but some sandboxes have no controlling terminal at
    all, and there opening /dev/tty fails outright.
    """
    if sys.stdin.isatty():
        return True
    try:
        with open("/dev/tty"):
            return True
    except OSError:
        return False


def read_key_from_stdin(provider: str) -> str:
    """Read a key piped on stdin — for non-interactive contexts.

    Usable where no terminal exists. The caller is responsible for getting the
    key to stdin without leaking it into shell history.
    """
    env_name, _ = PROVIDER_KEYS[provider]
    key = sys.stdin.readline().strip()
    if not key:
        raise KeyPromptError(f"No {env_name} received on stdin.")
    os.environ[env_name] = key
    error = validate_key(provider, key)
    if error:
        os.environ.pop(env_name, None)
        raise KeyPromptError(f"{env_name} rejected: {error}")
    return key


def prompt_for_key(provider: str, *, validate: bool = True) -> str:
    """Ask for *provider*'s API key on stdin and export it for this process only.

    Returns the key. Raises KeyPromptError if stdin is not a terminal, the input
    is empty, or validation fails.
    """
    if provider not in PROVIDER_KEYS:
        raise KeyPromptError(
            f"Unknown provider {provider!r}. Expected one of: {', '.join(PROVIDER_KEYS)}"
        )

    env_name, signup_url = PROVIDER_KEYS[provider]

    if not _has_terminal():
        raise KeyPromptError(
            f"Cannot prompt for {env_name}: no controlling terminal.\n"
            f"  This happens when the command is run without a TTY — including "
            f"Claude Code's '!' prefix, cron, and most CI runners.\n"
            f"  Fix: run the same command directly in a terminal window.\n"
            f"  Alternative: pipe the key in with --key-stdin, or set {env_name} "
            f"in the environment."
        )

    print(f"\n{provider} API key required — get one at {signup_url}")
    print("Input is hidden. The key is kept in memory only and never written to disk.")

    key = getpass.getpass(f"{env_name}: ").strip()
    if not key:
        raise KeyPromptError(f"No {env_name} entered — aborting.")

    os.environ[env_name] = key

    if validate:
        error = validate_key(provider, key)
        if error:
            # Do not leave a known-bad key where a later call would use it.
            os.environ.pop(env_name, None)
            raise KeyPromptError(f"{env_name} rejected: {error}")
        print(f"[OK] {env_name} accepted — it will be discarded when this process exits.\n")

    return key


def validate_key(provider: str, key: str) -> str | None:
    """Cheap liveness check. Returns None when the key works, else an error string."""
    import httpx

    try:
        if provider == "gemini":
            resp = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": key},
                timeout=_VALIDATION_TIMEOUT,
            )
        elif provider == "openrouter":
            resp = httpx.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {key}"},
                timeout=_VALIDATION_TIMEOUT,
            )
        elif provider == "groq":
            resp = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=_VALIDATION_TIMEOUT,
            )
        elif provider == "openai":
            resp = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=_VALIDATION_TIMEOUT,
            )
        else:  # pragma: no cover - guarded by prompt_for_key
            return f"no validator for {provider}"
    except Exception as exc:
        return f"could not reach {provider} ({type(exc).__name__})"

    if resp.status_code == 200:
        return None
    if resp.status_code in (401, 403):
        return "authentication failed — check the key was pasted in full"
    return f"HTTP {resp.status_code}"


def ensure_provider_key(provider: str, *, ask: bool = False) -> str | None:
    """Return the provider's key, prompting only when needed.

    An existing environment variable always wins, so CI and server deployments
    are unaffected. Prompts when *ask* is set, or when the key is simply absent
    and a terminal is available.
    """
    env_name, _ = PROVIDER_KEYS[provider]
    existing = os.environ.get(env_name, "").strip()

    if existing and not ask:
        return existing
    if not ask and not sys.stdin.isatty():
        return existing or None

    return prompt_for_key(provider)
