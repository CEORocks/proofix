from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "CASE-02"


class Case02FixtureContractTest(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        required = {
            "namespace.yaml", "dns-upstreams.yaml", "app.yaml", "corefile.py",
            "common.sh", "install.sh", "inject.sh", "reset.sh",
            "rollback-recovery.sh", "verify.sh", "smoke.sh", "load.py", "README.md",
        }
        self.assertTrue(required.issubset({path.name for path in FIXTURE.iterdir()}))

    def test_all_images_are_digest_pinned_and_nodeport_is_fixed(self) -> None:
        manifests = "\n".join(
            (FIXTURE / name).read_text(encoding="utf-8")
            for name in ("dns-upstreams.yaml", "app.yaml")
        )
        images = re.findall(r"^\s*image:\s*(\S+)", manifests, re.MULTILINE)
        self.assertEqual(len(images), 3)
        for image in images:
            self.assertRegex(image, r"^[^\s]+@sha256:[0-9a-f]{64}$")
        self.assertIn("nodePort: 30072", manifests)

    def test_fault_is_real_delayed_nxdomain(self) -> None:
        upstream = (FIXTURE / "dns-upstreams.yaml").read_text(encoding="utf-8")
        self.assertIn('value: "0.350"', upstream)
        self.assertIn("0x8183", upstream)
        load = (FIXTURE / "load.py").read_text(encoding="utf-8")
        self.assertIn('evidence.get("rcode") == 3', load)
        self.assertIn('evidence.get("latency_ms", 0) >= 300.0', load)

    def test_workload_uses_pod_cluster_dns(self) -> None:
        app = (FIXTURE / "app.yaml").read_text(encoding="utf-8")
        self.assertIn('open("/etc/resolv.conf"', app)
        self.assertIn('sock.sendto(packet, (cluster_dns(), 53))', app)
        self.assertIn('QUERY_NAME = "backend.bench.proofix"', app)
        self.assertIn('200 if evidence["ok"] else 503', app)

    def test_corefile_edit_is_isolated_and_idempotent(self) -> None:
        spec = importlib.util.spec_from_file_location("case02_corefile", FIXTURE / "corefile.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = ".:53 {\n    forward . /etc/resolv.conf\n}\n"
        once = module.render(original, "10.43.1.2:5353")
        twice = module.render(once, "10.43.1.3:5353")
        self.assertEqual(twice.count("BEGIN PROOFIX CASE-02"), 1)
        self.assertIn("bench.proofix:53", twice)
        self.assertIn("forward . 10.43.1.3:5353", twice)
        self.assertNotIn("10.43.1.2:5353", twice)
        self.assertIn("forward . /etc/resolv.conf", twice)

    def test_general_dns_and_strict_slo_are_enforced(self) -> None:
        common = (FIXTURE / "common.sh").read_text(encoding="utf-8")
        load = (FIXTURE / "load.py").read_text(encoding="utf-8")
        self.assertIn("kubernetes.default.svc.cluster.local", common)
        self.assertIn('"http_5xx_rate_lt": 0.001', load)
        self.assertIn('"p95_latency_ms_lt": 200.0', load)
        self.assertIn('"consecutive_windows": 3', load)
        self.assertIn("failures == 0 and rate < 0.001 and p95 < 200.0", load)

    def test_scripts_use_strict_shell_mode(self) -> None:
        for script in FIXTURE.glob("*.sh"):
            content = script.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"))


if __name__ == "__main__":
    unittest.main()

