from renegade_ai.memory import melonds_config
from renegade_ai.memory.melonds_config import patch_melonds_toml


def test_patch_melonds_toml_is_idempotent(tmp_path):
    path = tmp_path / "melonDS.toml"
    path.write_text("[JIT]\nEnable = true\n\n[Gdb]\nEnabled = false\n", encoding="utf-8")

    assert patch_melonds_toml(path) is True
    text = path.read_text(encoding="utf-8")
    assert "[JIT]" in text
    assert "Enable = false" in text
    assert "[Gdb]" in text
    assert "Enabled = true" in text
    assert "[Instance0.Gdb.ARM9]" in text
    assert "Port = 3333" in text
    assert "BreakOnStartup = false" in text
    assert path.with_suffix(".toml.renegadeai.bak").exists()

    assert patch_melonds_toml(path) is False


def test_configure_defers_changes_while_melonds_is_running(tmp_path, monkeypatch):
    path = tmp_path / "melonDS.toml"
    original = "[JIT]\nEnable = true\n\n[Gdb]\nEnabled = false\n"
    path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(melonds_config, "discover_melonds_toml", lambda: [path])
    monkeypatch.setattr(
        melonds_config,
        "_running_melonds_executable",
        lambda: tmp_path / "melonDS.exe",
    )

    result = melonds_config.configure_melonds_debugger()
    assert result.changed == ()
    assert result.deferred == (path,)
    assert result.restart_required is False
    assert path.read_text(encoding="utf-8") == original
