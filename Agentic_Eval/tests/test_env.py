"""The tiny .env loader (aah.env.load_dotenv)."""

from __future__ import annotations

from aah.env_loader import load_dotenv


def test_parses_keys_comments_export_and_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "ANTHROPIC_API_KEY=sk-ant-123\n"
        "export GEMINI_API_KEY=g-456\n"
        'QUOTED="has spaces"\n',
        encoding="utf-8",
    )
    loaded = load_dotenv(env)
    assert loaded["ANTHROPIC_API_KEY"] == "sk-ant-123"
    assert loaded["GEMINI_API_KEY"] == "g-456"      # export prefix stripped
    assert loaded["QUOTED"] == "has spaces"         # quotes stripped


def test_missing_file_is_not_an_error(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}


def test_existing_env_wins_unless_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")

    import os

    load_dotenv(env)                          # default override=False
    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"
    load_dotenv(env, override=True)
    assert os.environ["ANTHROPIC_API_KEY"] == "from-file"
