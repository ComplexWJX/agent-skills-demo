"""Parse skills, advertise metadata, and load text only when requested.

This intentionally implements a small subset of the Agent Skills format:
name/description + SKILL.md + references/*.md. It is not a script sandbox
or a full Agent Skills runtime. Only deploy trusted, reviewed skill packages.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

import yaml

MAX_TEXT_BYTES = 64 * 1024


def read_text(path: Path) -> str:
    # Bound bytes before decoding; do not read an arbitrarily large file first.
    with path.open("rb") as stream:
        raw = stream.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("Skill text exceeds 64 KiB")
    return raw.decode("utf-8-sig")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    directory: Path


class SkillRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.skills: dict[str, Skill] = {}
        for entry in sorted(self.root.iterdir()):
            if not entry.is_dir():
                continue
            directory = entry.resolve()
            if not directory.is_relative_to(self.root):
                raise ValueError("Skill directory must stay inside the skills root")
            file = directory / "SKILL.md"
            if not file.is_file():
                continue
            if not file.resolve().is_relative_to(directory):
                raise ValueError("SKILL.md symlink escapes the skill directory")
            text = read_text(file).replace("\r\n", "\n")
            parts = text.split("\n---\n", 1)
            if not text.startswith("---\n") or len(parts) != 2:
                raise ValueError(f"Missing YAML frontmatter: {entry.name}")
            metadata = yaml.safe_load(parts[0][4:])
            if not isinstance(metadata, dict):
                raise ValueError(f"Invalid YAML metadata: {entry.name}")
            name, description = metadata.get("name"), metadata.get("description")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
                raise ValueError(f"Invalid skill name: {entry.name}")
            if len(name) > 64 or name != entry.name:
                raise ValueError("Skill name must match its directory and be <=64 characters")
            if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
                raise ValueError(f"Invalid skill description: {name}")
            if name in self.skills:
                raise ValueError(f"Duplicate skill: {name}")
            if not parts[1].strip():
                raise ValueError(f"Empty skill body: {name}")
            self.skills[name] = Skill(name, description.strip(), directory)
        if not self.skills:
            raise ValueError("No SKILL.md files found")

    def catalog(self) -> list[dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in self.skills.values()]

    def _get(self, name: str) -> Skill:
        try:
            return self.skills[name]
        except KeyError:
            raise ValueError(f"Unknown skill: {name}") from None

    def load(self, name: str) -> str:
        skill = self._get(name)
        file = (skill.directory / "SKILL.md").resolve(strict=True)
        if not file.is_relative_to(skill.directory):
            raise ValueError("Skill file escapes its directory")
        return read_text(file)

    def read_reference(self, name: str, relative_path: str) -> str:
        skill = self._get(name)
        # Portable paths; reject Windows-style traversal on Linux as well.
        if "\\" in relative_path:
            raise ValueError("Reference paths must use forward slashes")
        relative = PurePosixPath(relative_path)
        if (relative.is_absolute() or ".." in relative.parts or
                not relative.parts or relative.parts[0] != "references" or
                relative.suffix != ".md"):
            raise ValueError("Only references/*.md files are available")
        target = (skill.directory / relative_path).resolve(strict=True)
        if not target.is_relative_to(skill.directory) or not target.is_file():
            raise ValueError("Reference escapes the skill directory")
        return read_text(target)

