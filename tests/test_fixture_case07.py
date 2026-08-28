from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "CASE-07"


class Case07FixtureContractTest(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        required = {
            "namespace.yaml",
            "app.yaml",
            "fault-patch.yaml",
            "recovery-patch.yaml",
            "rollback-recovery-patch.yaml",
            "install.sh",
            "inject.sh",
            "reset.sh",
            "rollback-recovery.sh",
            "verify.sh",
            "smoke.sh",
            "load.py",
            "README.md",
        }
        self.assertTrue(required.issubset({path.name for path in FIXTURE.iterdir()}))

    def test_image_is_digest_pinned_and_nodeport_is_fixed(self) -> None:
        manifest = (FIXTURE / "app.yaml").read_text(encoding="utf-8")
        self.assertRegex(manifest, r"image: eclipse-temurin:[^\s]+@sha256:[0-9a-f]{64}")
        self.assertIn("type: NodePort", manifest)
        self.assertIn("nodePort: 30077", manifest)

    def test_fault_is_the_authoritative_memory_mismatch(self) -> None:
        app = (FIXTURE / "app.yaml").read_text(encoding="utf-8")
        fault = (FIXTURE / "fault-patch.yaml").read_text(encoding="utf-8")
        self.assertIn("memory: 256Mi", app)
        self.assertIn("- -Xmx512m", fault)
        self.assertIn("fault-sequence", (FIXTURE / "load.py").read_text(encoding="utf-8"))

    def test_recovery_is_safe_and_rollback_is_exact(self) -> None:
        recovery = (FIXTURE / "recovery-patch.yaml").read_text(encoding="utf-8")
        rollback = (FIXTURE / "rollback-recovery-patch.yaml").read_text(encoding="utf-8")
        self.assertIn("- -Xmx128m", recovery)
        self.assertIn("- -Xmx512m", rollback)
        self.assertNotIn("memory: 0", recovery)
        self.assertNotIn("privileged", recovery)

    def test_slo_is_not_weakened(self) -> None:
        load = (FIXTURE / "load.py").read_text(encoding="utf-8")
        readme = (FIXTURE / "README.md").read_text(encoding="utf-8")
        self.assertIn('"http_5xx_rate_lt": 0.001', load)
        self.assertIn('"p95_latency_ms_lt": 200.0', load)
        self.assertIn('"consecutive_windows": 3', load)
        self.assertIn("rate < 0.001 and p95 < 200.0", load)
        self.assertIn("HTTP 5xx rate `< 0.001`", readme)
        self.assertIn("p95 latency `< 200ms`", readme)

    def test_scripts_use_strict_shell_mode(self) -> None:
        for script in FIXTURE.glob("*.sh"):
            content = script.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"))

    def test_java_load_touches_pages_and_keeps_heap_references(self) -> None:
        manifest = (FIXTURE / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("private static final List<byte[]> CACHE", manifest)
        self.assertIn("offset += 4096", manifest)
        self.assertIn("CACHE.add(chunk)", manifest)
        self.assertIsNotNone(re.search(r"RETAIN_FRACTION\s*=\s*0\.70", manifest))


if __name__ == "__main__":
    unittest.main()
