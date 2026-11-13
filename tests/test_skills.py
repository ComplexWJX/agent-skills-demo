from pathlib import Path

import pytest

from app.config import PROJECT_ROOT
from app.skills import SkillRegistry, MAX_TEXT_BYTES


def test_progressive_loading():
    registry = SkillRegistry(PROJECT_ROOT / "skills")
    catalog = str(registry.catalog())
    assert "device-triage" in catalog
    assert "references/offline-rules.md" not in catalog
    assert "references/offline-rules.md" in registry.load("device-triage")
    assert "业务心跳超时" in registry.read_reference("device-triage", "references/offline-rules.md")


@pytest.mark.parametrize("path", ["../../.env", "/etc/passwd", "references/../../.env",
                                  "references/..\\..\\.env", "scripts/run.py"])
def test_reference_paths_are_restricted(path):
    registry = SkillRegistry(PROJECT_ROOT / "skills")
    with pytest.raises(ValueError):
        registry.read_reference("device-triage", path)


def make_skill(root: Path):
    folder = root / "test-skill"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: Test only\n---\nInstructions", encoding="utf-8")
    return folder


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "skills"
    folder = make_skill(root)
    (folder / "references").mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("private", encoding="utf-8")
    try:
        (folder / "references/escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink permission is unavailable on this platform")
    registry = SkillRegistry(root)
    with pytest.raises(ValueError):
        registry.read_reference("test-skill", "references/escape.md")


def test_unknown_skill():
    registry = SkillRegistry(PROJECT_ROOT / "skills")
    with pytest.raises(ValueError, match="Unknown skill"):
        registry.load("../../anything")


def test_invalid_metadata_fails_startup(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "SKILL.md").write_text("---\nname: wrong-name\ndescription: x\n---\nbody")
    with pytest.raises(ValueError, match="match its directory"):
        SkillRegistry(tmp_path)


def test_reference_size_limit(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "references").mkdir()
    (folder / "references/large.md").write_bytes(b"x" * (MAX_TEXT_BYTES + 1))
    registry = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="64 KiB"):
        registry.read_reference("test-skill", "references/large.md")

