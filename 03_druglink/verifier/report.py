"""The check report: every check named, printed and counted. Silence is not a pass."""
from __future__ import annotations

from typing import Any


class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: Any, detail: str = "") -> bool:
        self.checks.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def failures(self) -> list[tuple[str, str]]:
        return [(n, d) for n, ok, d in self.checks if not ok]

    def render(self) -> str:
        out = [f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d and not ok else "")
               for n, ok, d in self.checks]
        out += ["", f"{len(self.checks) - len(self.failures)}/{len(self.checks)} "
                    "checks passed"]
        return "\n".join(out)

    def as_dict(self, **extra: Any) -> dict[str, Any]:
        return {"schema_version": "spot.stage03_verification.v1",
                "n_checks": len(self.checks),
                "n_failed": len(self.failures),
                "all_pass": not self.failures,
                "checks": [{"name": n, "pass": ok, "detail": d}
                           for n, ok, d in self.checks],
                **extra}
