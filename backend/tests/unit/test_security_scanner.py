"""Unit tests for the security scanner modules.

Tests secrets detector, IaC scanner, aggregator, and fingerprinting.
No external services required — all in-process.
"""

from __future__ import annotations

import uuid

import pytest

from app.scanner.aggregator import fingerprint, normalize, severity_counts
from app.scanner.iac import scan_file_iac
from app.scanner.secrets import (
    RawFinding,
    _is_likely_placeholder,
    _shannon_entropy,
    _should_skip_path,
    scan_file_for_secrets,
)


# ── Shannon entropy ────────────────────────────────────────────────────────────


class TestShannonEntropy:
    def test_low_entropy_repeated_chars(self) -> None:
        assert _shannon_entropy("aaaaaaaaaa") < 1.0

    def test_high_entropy_random_string(self) -> None:
        # Random-looking base64
        assert _shannon_entropy("aB3kQ7mZpX9wVrTn2Ys4Cu8LdEo1Fg6") > 4.0

    def test_empty_string(self) -> None:
        assert _shannon_entropy("") == 0.0


# ── Placeholder detection ──────────────────────────────────────────────────────


class TestIsLikelyPlaceholder:
    def test_known_placeholder(self) -> None:
        assert _is_likely_placeholder("your_api_key_here") is True

    def test_changeme(self) -> None:
        assert _is_likely_placeholder("changeme") is True

    def test_real_looking_key(self) -> None:
        assert _is_likely_placeholder("AKIAIOSFODNN7EXAMPLE") is False

    def test_empty_string(self) -> None:
        assert _is_likely_placeholder("") is True

    def test_all_same_char(self) -> None:
        assert _is_likely_placeholder("xxxxxxxxxx") is True


# ── Skip path detection ────────────────────────────────────────────────────────


class TestShouldSkipPath:
    def test_example_file(self) -> None:
        assert _should_skip_path("config.example") is True

    def test_sample_file(self) -> None:
        assert _should_skip_path("env.sample") is True

    def test_normal_python_file(self) -> None:
        assert _should_skip_path("app/config.py") is False

    def test_template_file(self) -> None:
        assert _should_skip_path("settings.template") is True


# ── Secrets scanner ────────────────────────────────────────────────────────────


class TestSecretsScanner:
    def test_detects_aws_access_key(self) -> None:
        source = 'aws_key = "AKIAIOSFODNN7EXAMPLEKEY"\n'
        findings = scan_file_for_secrets("config.py", source)
        rule_ids = [f.rule_id for f in findings]
        assert any("aws_access_key" in r for r in rule_ids)

    def test_detects_private_key_header(self) -> None:
        source = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n"
        findings = scan_file_for_secrets("id_rsa", source)
        assert any("private_key" in f.rule_id for f in findings)

    def test_detects_github_token(self) -> None:
        source = 'token = "ghp_' + "A" * 36 + '"\n'
        findings = scan_file_for_secrets("deploy.py", source)
        assert any("github" in f.rule_id for f in findings)

    def test_skips_placeholder_password(self) -> None:
        source = 'password = "changeme"\n'
        findings = scan_file_for_secrets("app.py", source)
        # Should not flag since "changeme" is in allowlist
        pw_findings = [f for f in findings if "generic_password" in f.rule_id]
        assert len(pw_findings) == 0

    def test_skips_example_file(self) -> None:
        source = 'API_KEY = "AKIAIOSFODNN7EXAMPLE123456"\n'
        findings = scan_file_for_secrets("config.example", source)
        assert findings == []

    def test_detects_high_entropy(self) -> None:
        # 32-char random-looking string that isn't a known placeholder
        source = 'token = "aB3kQ7mZpX9wVrTn2Ys4Cu8LdEo1Fg6"\n'
        findings = scan_file_for_secrets("auth.py", source)
        assert any("high_entropy" in f.rule_id for f in findings)

    def test_skips_test_file_medium_findings(self) -> None:
        source = 'password = "supersecret123"\n'
        # generic_password is medium/low — should be skipped in test files
        findings = scan_file_for_secrets("tests/test_auth.py", source)
        pw_findings = [f for f in findings if "generic_password" in f.rule_id]
        assert len(pw_findings) == 0

    def test_empty_source_returns_empty(self) -> None:
        assert scan_file_for_secrets("app.py", "") == []

    def test_critical_finding_has_correct_severity(self) -> None:
        source = "-----BEGIN OPENSSH PRIVATE KEY-----\ndata\n"
        findings = scan_file_for_secrets("key.pem", source)
        critical = [f for f in findings if f.severity == "critical"]
        assert len(critical) > 0


# ── IaC scanner ────────────────────────────────────────────────────────────────


class TestDockerfileScanner:
    def test_detects_latest_tag(self) -> None:
        source = "FROM python:latest\nRUN pip install flask\n"
        findings = scan_file_iac("Dockerfile", source)
        assert any("latest_tag" in f.rule_id for f in findings)

    def test_detects_no_user_directive(self) -> None:
        source = "FROM python:3.12\nRUN pip install flask\n"
        findings = scan_file_iac("Dockerfile", source)
        assert any("no_user_directive" in f.rule_id for f in findings)

    def test_detects_user_root(self) -> None:
        source = "FROM python:3.12\nUSER root\nRUN pip install flask\n"
        findings = scan_file_iac("Dockerfile", source)
        assert any("user_root" in f.rule_id for f in findings)

    def test_detects_secret_in_env(self) -> None:
        source = "FROM python:3.12\nUSER app\nENV API_KEY=sk-secret123\n"
        findings = scan_file_iac("Dockerfile", source)
        assert any("secret_in_env" in f.rule_id for f in findings)

    def test_detects_no_healthcheck(self) -> None:
        source = "FROM python:3.12\nUSER app\n"
        findings = scan_file_iac("Dockerfile", source)
        assert any("no_healthcheck" in f.rule_id for f in findings)

    def test_clean_dockerfile_minimal_findings(self) -> None:
        source = (
            "FROM python:3.12-slim\n"
            "USER app\n"
            "COPY . /app\n"
            "HEALTHCHECK CMD curl -f http://localhost/ || exit 1\n"
        )
        findings = scan_file_iac("Dockerfile", source)
        # Only info/low findings allowed
        high_plus = [f for f in findings if f.severity in ("critical", "high")]
        assert len(high_plus) == 0


class TestK8sScanner:
    def test_detects_privileged_container(self) -> None:
        source = (
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test\n"
            "spec:\n  containers:\n  - name: app\n    securityContext:\n      privileged: true\n"
        )
        findings = scan_file_iac("pod.yaml", source)
        assert any("privileged" in f.rule_id for f in findings)

    def test_detects_host_network(self) -> None:
        source = (
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test\n"
            "spec:\n  hostNetwork: true\n  containers: []\n"
        )
        findings = scan_file_iac("pod.yaml", source)
        assert any("host_network" in f.rule_id for f in findings)

    def test_non_k8s_yaml_skipped(self) -> None:
        source = "name: My App\nversion: 1.0\n"
        findings = scan_file_iac("config.yaml", source)
        assert findings == []


class TestTerraformScanner:
    def test_detects_rds_public(self) -> None:
        source = 'resource "aws_db_instance" "main" {\n  publicly_accessible = true\n}\n'
        findings = scan_file_iac("main.tf", source)
        assert any("rds_public" in f.rule_id for f in findings)

    def test_detects_ebs_unencrypted(self) -> None:
        source = 'resource "aws_ebs_volume" "data" {\n  encrypted = false\n}\n'
        findings = scan_file_iac("storage.tf", source)
        assert any("ebs_unencrypted" in f.rule_id for f in findings)


# ── Aggregator ────────────────────────────────────────────────────────────────


class TestAggregator:
    def _make_finding(self, rule_id: str = "test.rule", file_path: str = "app.py") -> RawFinding:
        return RawFinding(
            rule_id=rule_id,
            title="Test finding",
            description="A test finding.",
            severity="high",
            cvss_score=7.5,
            file_path=file_path,
            start_line=10,
            end_line=10,
            snippet="some code",
            category="test",
        )

    def test_fingerprint_is_deterministic(self) -> None:
        f = self._make_finding()
        assert fingerprint(f) == fingerprint(f)

    def test_fingerprint_differs_by_line(self) -> None:
        f1 = self._make_finding()
        f2 = RawFinding(**{**f1.__dict__, "start_line": 99, "end_line": 99})
        assert fingerprint(f1) != fingerprint(f2)

    def test_normalize_deduplicates(self) -> None:
        f = self._make_finding()
        rows = normalize(
            [f, f],  # duplicate
            scan_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            scanner="secrets",
        )
        assert len(rows) == 1

    def test_normalize_adds_required_fields(self) -> None:
        f = self._make_finding()
        scan_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        rows = normalize([f], scan_id=scan_id, repo_id=repo_id, scanner="secrets")
        assert rows[0]["scan_id"] == scan_id
        assert rows[0]["repo_id"] == repo_id
        assert rows[0]["scanner"] == "secrets"
        assert len(rows[0]["fingerprint"]) == 64

    def test_severity_counts(self) -> None:
        findings = [
            {"severity": "critical"},
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
            {"severity": "info"},
        ]
        counts = severity_counts(findings)
        assert counts["critical"] == 2
        assert counts["high"] == 1
        assert counts["total"] == 6
