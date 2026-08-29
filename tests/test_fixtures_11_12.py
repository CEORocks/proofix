from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE11 = ROOT / "fixtures" / "CASE-11"
CASE12 = ROOT / "fixtures" / "CASE-12"


class KafkaFixtureContractTest(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        case11 = {
            "namespace.yaml", "broker.yaml", "workloads.yaml", "common.sh",
            "install.sh", "inject.sh", "reset.sh", "rollback-recovery.sh",
            "verify.sh", "smoke.sh", "lag_probe.py", "load.py", "README.md",
        }
        case12 = {
            "namespace.yaml", "cluster.yaml", "override-healthy.yaml",
            "override-fault.yaml", "common.sh", "safety-guard.sh", "install.sh",
            "inject.sh", "reset.sh", "rollback-recovery.sh", "verify.sh",
            "smoke.sh", "partition_probe.py", "record_probe.py", "load.py",
            "README.md",
        }
        self.assertTrue(case11.issubset({path.name for path in CASE11.iterdir()}))
        self.assertTrue(case12.issubset({path.name for path in CASE12.iterdir()}))

    def test_all_container_images_are_digest_pinned(self) -> None:
        manifests = (CASE11 / "broker.yaml").read_text() + (CASE11 / "workloads.yaml").read_text()
        manifests += (CASE12 / "cluster.yaml").read_text()
        images = re.findall(r"(?m)^\s+image:\s+(\S+)$", manifests)
        self.assertGreaterEqual(len(images), 4)
        for image in images:
            self.assertRegex(image, r":[^@\s]+@sha256:[0-9a-f]{64}$")

    def test_case11_is_real_six_partition_group_lag(self) -> None:
        workload = (CASE11 / "workloads.yaml").read_text()
        install = (CASE11 / "install.sh").read_text()
        inject = (CASE11 / "inject.sh").read_text()
        recovery = (CASE11 / "reset.sh").read_text()
        probe = (CASE11 / "lag_probe.py").read_text()
        self.assertIn("--partitions 6", install)
        self.assertIn('value: "42"', workload)
        self.assertIn('value: "0.04"', workload)
        self.assertIn("KafkaConsumer(", workload)
        self.assertIn("enable_auto_commit=False", workload)
        self.assertIn("consumer.commit()", workload)
        self.assertIn("--require-hashes", workload)
        self.assertIn("--replicas=1", inject)
        self.assertIn("--replicas=3", recovery)
        self.assertIn('rpk("group", "describe", GROUP)', probe)
        self.assertIn("all(later > earlier", probe)

    def test_case11_forbidden_recovery_shortcuts_absent(self) -> None:
        scripts = "\n".join(path.read_text() for path in CASE11.glob("*.sh"))
        scripts += (CASE11 / "lag_probe.py").read_text()
        self.assertNotRegex(scripts, r"rpk\s+group\s+(seek|delete)")
        self.assertNotRegex(scripts, r"rpk\s+topic\s+delete")
        self.assertNotIn("kubectl scale deployment/orders-producer", scripts)

    def test_case12_is_persistent_three_broker_rf3_fixture(self) -> None:
        cluster = (CASE12 / "cluster.yaml").read_text()
        install = (CASE12 / "install.sh").read_text()
        self.assertIn("replicas: 3", cluster)
        self.assertIn("podManagementPolicy: Parallel", cluster)
        self.assertIn("persistentVolumeClaimRetentionPolicy", cluster)
        self.assertIn("whenDeleted: Retain", cluster)
        self.assertIn("storage: 4Gi", cluster)
        self.assertIn("--replicas 3", install)
        self.assertIn("write_caching_default false", install)
        self.assertIn("write_caching_default false", install)
        self.assertIn("retention.ms=-1", install)

    def test_case12_fault_and_recovery_preserve_pvc(self) -> None:
        inject = (CASE12 / "inject.sh").read_text()
        reset = (CASE12 / "reset.sh").read_text()
        probe = (CASE12 / "partition_probe.py").read_text()
        fault = (CASE12 / "override-fault.yaml").read_text()
        self.assertIn("--proofix-invalid-startup-flag", fault)
        self.assertIn("pvc/data-kafka-2", inject)
        self.assertIn("--acks=-1", (CASE12 / "common.sh").read_text())
        self.assertIn("pvc_identity_preserved", probe)
        self.assertIn("under_replicated_partitions", probe)
        self.assertIn("override-healthy.yaml", reset)
        self.assertNotIn("delete pvc", inject.lower() + reset.lower())

    def test_case12_guard_rejects_every_forbidden_action(self) -> None:
        guard = str(CASE12 / "safety-guard.sh")
        safe = subprocess.run([guard, "--", "true"], check=False, capture_output=True)
        self.assertEqual(safe.returncode, 0)
        forbidden = [
            ["rpk", "topic", "delete", "proofix-replicated"],
            ["kubectl", "delete", "pvc", "data-kafka-2"],
            ["rpk", "topic", "alter-config", "x", "--set", "min.insync.replicas=1"],
            ["rpk", "cluster", "partitions", "force-recover", "x"],
            ["tool", "unclean.leader.election.enable=true"],
            ["tool", "partition", "reassign", "x"],
        ]
        for command in forbidden:
            with self.subTest(command=command):
                result = subprocess.run([guard, "--", *command], check=False, capture_output=True)
                self.assertEqual(result.returncode, 64)
                self.assertIn(b"FORBIDDEN", result.stderr)

    def test_case12_action_scripts_contain_no_destructive_commands(self) -> None:
        action_files = ["install.sh", "inject.sh", "reset.sh", "rollback-recovery.sh", "verify.sh", "smoke.sh"]
        scripts = "\n".join((CASE12 / name).read_text().lower() for name in action_files)
        self.assertNotRegex(scripts, r"rpk\s+topic\s+(delete|trim-prefix)")
        self.assertNotRegex(scripts, r"kubectl\s+delete\s+(pvc|persistentvolumeclaim|pv)")
        self.assertNotRegex(scripts, r"min\.insync\.replicas[=:][01](?:\D|$)")
        self.assertNotIn("unclean.leader.election.enable=true", scripts)

    def test_slo_contract_is_exact_and_conjunctive(self) -> None:
        for fixture in (CASE11, CASE12):
            load = (fixture / "load.py").read_text()
            verify = (fixture / "verify.sh").read_text()
            self.assertIn('"http_5xx_rate_lt": 0.001', load)
            self.assertIn('"p95_latency_ms_lt": 200.0', load)
            self.assertIn('"consecutive_windows": 3', load)
            self.assertIn("rate < 0.001 and p95 < 200.0", load)
            self.assertIn("load.py", verify)

    def test_shell_scripts_are_strict_and_syntax_valid(self) -> None:
        for fixture in (CASE11, CASE12):
            for script in fixture.glob("*.sh"):
                content = script.read_text()
                self.assertTrue(content.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"))
                result = subprocess.run(["bash", "-n", str(script)], check=False, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_yaml_parses_when_pyyaml_is_available(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        for fixture in (CASE11, CASE12):
            for manifest in fixture.glob("*.yaml"):
                with self.subTest(manifest=manifest.name):
                    self.assertTrue(list(yaml.safe_load_all(manifest.read_text())))

    def test_case11_workload_document_boundaries_and_embedded_python(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        documents = list(yaml.safe_load_all((CASE11 / "workloads.yaml").read_text()))
        self.assertEqual([document["kind"] for document in documents],
                         ["ConfigMap", "Deployment", "Deployment", "Service"])
        programs = documents[0]["data"]
        self.assertEqual(set(programs), {"producer.py", "consumer.py", "requirements.txt"})
        with tempfile.TemporaryDirectory() as directory:
            for name in ("producer.py", "consumer.py"):
                source = programs[name]
                path = Path(directory) / name
                path.write_text(source)
                result = subprocess.run(
                    ["python3", "-m", "py_compile", str(path)],
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
