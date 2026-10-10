"""A routed profile scope must not warn about a launch-dotenv key it withheld.

The miss is by design (#84079): ``get_secret`` returns the default rather than
the launch process environment, and the literal stays. The warning text tells
the operator to check ``~/.hermes/.env``, which already contains the key, so
the WARNING line is noise.

This is not the import-time miss (#89199, owned by #89218 / #101770 / #117476).
Those leave scoped reads unchanged. An unscoped miss, a launch-scope miss, an
unstamped scope, and a key absent from the launch dotenv still warn.
"""
from __future__ import annotations

import logging
import re

import hermes_constants
from agent import secret_scope as ss
from hermes_cli.config import _env_expand_match

_NAME = "ROUTED_SCOPE_WARN_PROBE"
_REF = "${env:" + _NAME + "}"


def _expand() -> str:
    match = re.match(r"\$\{([^}]+)\}", _REF)
    assert match is not None
    return _env_expand_match(match)


def _warnings(caplog, name: str = _NAME) -> list:
    return [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and name in record.getMessage()
    ]


def _install(monkeypatch, home: str, *, keys: frozenset[str], multiplex: bool):
    monkeypatch.delenv(_NAME, raising=False)
    monkeypatch.setattr(
        "hermes_cli.env_loader.launch_dotenv_keys",
        lambda: keys,
    )
    was_active = ss.is_multiplex_active()
    ss.set_multiplex_active(multiplex)
    token = ss.set_secret_scope({"UNRELATED": "x"}, profile_home=home)
    return was_active, token


def _restore(was_active, token) -> None:
    ss.reset_secret_scope(token)
    ss.set_multiplex_active(was_active)


def test_foreign_profile_scope_does_not_warn_for_a_launch_dotenv_key(
    tmp_path, monkeypatch, caplog
):
    launch = tmp_path / "launch"
    profile = tmp_path / "profiles" / "served"
    launch.mkdir()
    profile.mkdir(parents=True)
    hermes_constants.pin_process_hermes_home(launch)
    was_active, token = _install(
        monkeypatch,
        str(profile),
        keys=frozenset({_NAME}),
        multiplex=True,
    )
    try:
        with caplog.at_level(logging.DEBUG, logger="hermes_cli.config"):
            assert _expand() == _REF
        assert _warnings(caplog) == []
        assert any(
            record.levelno == logging.DEBUG and "withheld" in record.getMessage()
            for record in caplog.records
        )
    finally:
        _restore(was_active, token)
        hermes_constants.pin_process_hermes_home(None)


def test_foreign_profile_scope_still_warns_when_the_launch_dotenv_lacks_the_key(
    tmp_path, monkeypatch, caplog
):
    launch = tmp_path / "launch"
    profile = tmp_path / "profiles" / "served"
    launch.mkdir()
    profile.mkdir(parents=True)
    hermes_constants.pin_process_hermes_home(launch)
    was_active, token = _install(
        monkeypatch, str(profile), keys=frozenset(), multiplex=False
    )
    try:
        with caplog.at_level(logging.WARNING, logger="hermes_cli.config"):
            assert _expand() == _REF
        assert _warnings(caplog)
    finally:
        _restore(was_active, token)
        hermes_constants.pin_process_hermes_home(None)


def test_launch_scope_miss_still_warns(tmp_path, monkeypatch, caplog):
    launch = tmp_path / "launch"
    launch.mkdir()
    hermes_constants.pin_process_hermes_home(launch)
    was_active, token = _install(
        monkeypatch, str(launch), keys=frozenset({_NAME}), multiplex=False
    )
    try:
        with caplog.at_level(logging.WARNING, logger="hermes_cli.config"):
            assert _expand() == _REF
        assert _warnings(caplog)
    finally:
        _restore(was_active, token)
        hermes_constants.pin_process_hermes_home(None)


def test_unscoped_miss_still_warns_even_if_the_launch_dotenv_has_the_key(
    monkeypatch, caplog
):
    """The import-time path stays owned by #89199. This patch must not quiet it."""
    monkeypatch.delenv(_NAME, raising=False)
    monkeypatch.setattr(
        "hermes_cli.env_loader.launch_dotenv_keys",
        lambda: frozenset({_NAME}),
    )
    assert ss.current_secret_scope() is None
    with caplog.at_level(logging.WARNING, logger="hermes_cli.config"):
        assert _expand() == _REF
    assert _warnings(caplog)


def test_unstamped_multiplex_scope_still_warns(monkeypatch, caplog):
    """No stamped home: we cannot prove the miss is by design, so we still warn."""
    monkeypatch.delenv(_NAME, raising=False)
    monkeypatch.setattr(
        "hermes_cli.env_loader.launch_dotenv_keys",
        lambda: frozenset({_NAME}),
    )
    was_active = ss.is_multiplex_active()
    ss.set_multiplex_active(True)
    token = ss.set_secret_scope({"UNRELATED": "x"})
    try:
        with caplog.at_level(logging.WARNING, logger="hermes_cli.config"):
            assert _expand() == _REF
        assert _warnings(caplog)
    finally:
        _restore(was_active, token)


def test_profile_scope_value_still_resolves_without_a_warning(
    tmp_path, monkeypatch, caplog
):
    launch = tmp_path / "launch"
    profile = tmp_path / "profiles" / "served"
    launch.mkdir()
    profile.mkdir(parents=True)
    hermes_constants.pin_process_hermes_home(launch)
    monkeypatch.setattr(
        "hermes_cli.env_loader.launch_dotenv_keys",
        lambda: frozenset({_NAME}),
    )
    was_active = ss.is_multiplex_active()
    ss.set_multiplex_active(True)
    token = ss.set_secret_scope({_NAME: "from-profile"}, profile_home=str(profile))
    try:
        with caplog.at_level(logging.WARNING, logger="hermes_cli.config"):
            assert _expand() == "from-profile"
        assert _warnings(caplog) == []
    finally:
        _restore(was_active, token)
        hermes_constants.pin_process_hermes_home(None)
