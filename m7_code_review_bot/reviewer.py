"""Deterministic PR checks. The checks deliberately prefer useful, line-level feedback."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable


@dataclass(frozen=True)
class ReviewFinding:
    rule: str
    path: str
    line: int
    level: str
    message: str
    suggestion: str

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Review:
    findings: tuple[ReviewFinding, ...]

    @property
    def clean(self) -> bool:
        return not self.findings

    def as_dict(self):
        return {"clean": self.clean, "findings": [f.as_dict() for f in self.findings]}


SECRET_PATTERNS = (
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("token", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']")),
)
INPUT_PATTERNS = (
    re.compile(r"(?i)\b(?:eval|exec)\s*\("),
    re.compile(r"(?i)\b(?:innerHTML|dangerouslySetInnerHTML)\s*="),
    re.compile(r"(?i)\b(?:sql|query)\s*=\s*[\"'].*\+"),
)


def _finding(rule, path, line, level, message, suggestion):
    return ReviewFinding(rule, path, line, level, message, suggestion)


def review_diff(files: Iterable[dict]) -> Review:
    """Review changed file contents. Each item is {path, content, additions?}."""
    findings: list[ReviewFinding] = []
    for file in files:
        path = str(file.get("path", ""))
        content = str(file.get("content", ""))
        if not content or path.endswith(('.lock', '.map', '.min.js')):
            continue
        lines = content.splitlines()
        function_starts: list[tuple[int, str]] = []
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line) and not _is_example(line):
                    findings.append(_finding("hard-coded-secret", path, number, "error",
                        f"Possible hard-coded {label} found in source.",
                        "Move it to the repository secret store or environment configuration."))
            if any(pattern.search(line) for pattern in INPUT_PATTERNS):
                findings.append(_finding("unsafe-input", path, number, "warning",
                    "User-controlled input may reach an unsafe operation without validation.",
                    "Validate and constrain input before using it; prefer a safe API over dynamic evaluation."))
            if re.search(r"(?m)^\s*(?:def|function|async\s+function)\s+([A-Za-z_$][\w$]*)", line):
                function_starts.append((number, stripped))
        for index, (start, declaration) in enumerate(function_starts):
            end = function_starts[index + 1][0] if index + 1 < len(function_starts) else len(lines) + 1
            if end - start > 50:
                findings.append(_finding("long-function", path, start, "warning",
                    f"Function spans about {end - start} lines and may be hard to maintain.",
                    "Split the function into small helpers with one responsibility each."))
        if _looks_like_code(path) and _has_executable_lines(lines) and not _has_error_handling(lines):
            findings.append(_finding("missing-error-handling", path, 1, "warning",
                "This changed source file has no visible error-handling path.",
                "Handle expected failures and return a useful error to the caller."))
    unique = {(f.rule, f.path, f.line, f.message): f for f in findings}
    return Review(tuple(sorted(unique.values(), key=lambda f: (f.path, f.line, f.rule))))


def _is_example(line):
    return bool(re.search(r"(?i)(example|test|fixture|dummy|changeme)", line))


def _looks_like_code(path):
    return path.endswith(('.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rb', '.php', '.cs'))


def _has_executable_lines(lines):
    return any(line.strip() and not line.lstrip().startswith(('#', '//', '/*', '*')) for line in lines)


def _has_error_handling(lines):
    text = '\n'.join(lines)
    return bool(re.search(r"(?i)\b(try|catch|except|raise|throw|onerror|error\s*=>|\.catch\()\b", text))
