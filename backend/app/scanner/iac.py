"""IaC scanner — rule-based analysis for Dockerfile, Kubernetes, and Terraform.

Implements all rules specified in the PRD for:
- Dockerfile security misconfigurations
- Kubernetes manifest security issues
- Terraform resource misconfigurations
"""

from __future__ import annotations

import re
from pathlib import Path

from app.scanner.secrets import RawFinding

# ── File classifiers ──────────────────────────────────────────────────────────

_DOCKERFILE_NAMES = frozenset({"dockerfile", "dockerfile.dev", "dockerfile.prod", "dockerfile.test"})
_K8S_EXTENSIONS = frozenset({".yaml", ".yml"})
_TERRAFORM_EXTENSIONS = frozenset({".tf"})

_K8S_KEYWORDS = frozenset({"kind:", "apiVersion:", "metadata:", "spec:"})


def _is_dockerfile(file_path: str) -> bool:
    return Path(file_path).name.lower() in _DOCKERFILE_NAMES


def _is_k8s_manifest(file_path: str, source: str) -> bool:
    if Path(file_path).suffix.lower() not in _K8S_EXTENSIONS:
        return False
    return any(kw in source for kw in _K8S_KEYWORDS)


def _is_terraform(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in _TERRAFORM_EXTENSIONS


# ── Dockerfile rules ──────────────────────────────────────────────────────────


def _scan_dockerfile(file_path: str, source: str) -> list[RawFinding]:
    """Apply Dockerfile security rules.

    Args:
        file_path: Relative file path.
        source: Dockerfile content.

    Returns:
        List of RawFinding instances.
    """
    findings: list[RawFinding] = []
    lines = source.splitlines()
    has_user_directive = False
    has_healthcheck = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        upper = stripped.upper()

        # USER directive present
        if upper.startswith("USER "):
            has_user_directive = True
            if re.match(r"USER\s+root\b", stripped, re.IGNORECASE):
                findings.append(_make(
                    "iac.dockerfile.user_root",
                    "Container runs as root",
                    "Running as root inside a container elevates the impact of any compromise.",
                    "high", 7.5, file_path, i, i,
                    stripped, "iac_dockerfile",
                ))

        # HEALTHCHECK present
        if upper.startswith("HEALTHCHECK"):
            has_healthcheck = True

        # Latest tag in FROM
        if upper.startswith("FROM ") and ":latest" in upper:
            findings.append(_make(
                "iac.dockerfile.latest_tag",
                "Docker image uses 'latest' tag",
                "Using 'latest' makes builds non-reproducible and may pull insecure images.",
                "medium", 5.0, file_path, i, i,
                stripped, "iac_dockerfile",
            ))

        # ADD instead of COPY
        if upper.startswith("ADD ") and not re.search(r"ADD\s+https?://", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.dockerfile.add_vs_copy",
                "ADD instruction used instead of COPY",
                "ADD can fetch remote URLs and auto-extract archives. Use COPY unless this is intentional.",
                "medium", 4.5, file_path, i, i,
                stripped, "iac_dockerfile",
            ))

        # Secrets in ENV
        if upper.startswith("ENV ") and re.search(
            r"(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)\s*=\s*\S+",
            stripped, re.IGNORECASE,
        ):
            findings.append(_make(
                "iac.dockerfile.secret_in_env",
                "Secret in Dockerfile ENV instruction",
                "Secrets in ENV are baked into the image layer and visible to anyone with image access.",
                "critical", 9.0, file_path, i, i,
                re.sub(r"=\S+", "=[REDACTED]", stripped), "iac_dockerfile",
            ))

        # Secrets in ARG
        if upper.startswith("ARG ") and re.search(
            r"(PASSWORD|SECRET|TOKEN|API_KEY)\s*=",
            stripped, re.IGNORECASE,
        ):
            findings.append(_make(
                "iac.dockerfile.secret_in_arg",
                "Secret default in Dockerfile ARG",
                "ARG default values are stored in image history and are not truly secret.",
                "high", 7.0, file_path, i, i,
                stripped, "iac_dockerfile",
            ))

        # wget/curl with --no-check-certificate
        if re.search(r"(wget|curl).*--no-check-certificate", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.dockerfile.no_cert_check",
                "TLS certificate verification disabled",
                "--no-check-certificate disables TLS validation, enabling man-in-the-middle attacks.",
                "high", 7.5, file_path, i, i,
                stripped, "iac_dockerfile",
            ))

    # File-level checks
    if not has_user_directive:
        findings.append(_make(
            "iac.dockerfile.no_user_directive",
            "No USER directive in Dockerfile",
            "Without a USER directive the container runs as root by default.",
            "high", 7.0, file_path, 1, len(lines),
            "", "iac_dockerfile",
        ))

    if not has_healthcheck:
        findings.append(_make(
            "iac.dockerfile.no_healthcheck",
            "No HEALTHCHECK defined",
            "Without a HEALTHCHECK, orchestrators cannot detect unhealthy containers.",
            "low", 2.0, file_path, 1, len(lines),
            "", "iac_dockerfile",
        ))

    return findings


# ── Kubernetes rules ──────────────────────────────────────────────────────────


def _scan_k8s(file_path: str, source: str) -> list[RawFinding]:
    """Apply Kubernetes manifest security rules.

    Args:
        file_path: Relative file path.
        source: Manifest YAML content.

    Returns:
        List of RawFinding instances.
    """
    findings: list[RawFinding] = []
    lines = source.splitlines()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        if re.search(r"privileged\s*:\s*true", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.k8s.privileged_container",
                "Privileged container",
                "privileged: true grants the container nearly all capabilities of the host.",
                "critical", 9.5, file_path, i, i,
                stripped, "iac_k8s",
            ))

        if re.search(r"hostNetwork\s*:\s*true", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.k8s.host_network",
                "hostNetwork: true",
                "Sharing the host network namespace exposes all host ports to the container.",
                "high", 8.0, file_path, i, i,
                stripped, "iac_k8s",
            ))

        if re.search(r"hostPID\s*:\s*true", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.k8s.host_pid",
                "hostPID: true",
                "Sharing the host PID namespace allows the container to inspect and kill host processes.",
                "high", 8.0, file_path, i, i,
                stripped, "iac_k8s",
            ))

        if re.search(r"allowPrivilegeEscalation\s*:\s*true", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.k8s.privilege_escalation",
                "allowPrivilegeEscalation: true",
                "Allows processes to gain more privileges than their parent process.",
                "high", 7.5, file_path, i, i,
                stripped, "iac_k8s",
            ))

        if re.search(r"runAsUser\s*:\s*0\b", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.k8s.run_as_root",
                "Container configured to run as root (runAsUser: 0)",
                "Running as UID 0 (root) inside a Kubernetes pod amplifies the impact of any breakout.",
                "high", 7.5, file_path, i, i,
                stripped, "iac_k8s",
            ))

    # Check for missing resource limits (look for 'resources:' without 'limits:')
    if "resources:" in source and "limits:" not in source:
        findings.append(_make(
            "iac.k8s.no_resource_limits",
            "No resource limits defined",
            "Containers without CPU/memory limits can starve other pods on the same node.",
            "medium", 5.0, file_path, 1, len(lines),
            "", "iac_k8s",
        ))

    # Missing readiness/liveness probes
    if "kind: Deployment" in source or "kind: StatefulSet" in source:
        if "livenessProbe:" not in source and "readinessProbe:" not in source:
            findings.append(_make(
                "iac.k8s.no_probes",
                "No liveness or readiness probes defined",
                "Without health probes, Kubernetes cannot detect and restart unhealthy pods.",
                "low", 2.5, file_path, 1, len(lines),
                "", "iac_k8s",
            ))

    return findings


# ── Terraform rules ───────────────────────────────────────────────────────────


def _scan_terraform(file_path: str, source: str) -> list[RawFinding]:
    """Apply Terraform resource security rules.

    Args:
        file_path: Relative file path.
        source: Terraform HCL content.

    Returns:
        List of RawFinding instances.
    """
    findings: list[RawFinding] = []
    lines = source.splitlines()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # S3 public access
        if re.search(r"acl\s*=\s*['\"]public-read", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.terraform.s3_public_acl",
                "S3 bucket is publicly readable",
                "Public-read ACL exposes all bucket objects to the internet.",
                "high", 8.0, file_path, i, i,
                stripped, "iac_terraform",
            ))

        # Security group open SSH
        if re.search(r"cidr_blocks\s*=\s*\[?['\"]0\.0\.0\.0/0['\"]", stripped) and \
           re.search(r"from_port\s*=\s*22", source, re.IGNORECASE):
            findings.append(_make(
                "iac.terraform.sg_open_ssh",
                "Security group allows SSH from 0.0.0.0/0",
                "Unrestricted SSH access exposes instances to brute force and exploitation.",
                "critical", 9.0, file_path, i, i,
                stripped, "iac_terraform",
            ))

        # RDS publicly accessible
        if re.search(r"publicly_accessible\s*=\s*true", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.terraform.rds_public",
                "RDS instance is publicly accessible",
                "Publicly accessible RDS instances expose the database to the internet.",
                "high", 8.5, file_path, i, i,
                stripped, "iac_terraform",
            ))

        # EBS unencrypted
        if re.search(r"encrypted\s*=\s*false", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.terraform.ebs_unencrypted",
                "EBS volume encryption disabled",
                "Unencrypted EBS volumes expose data at rest if disks are compromised.",
                "medium", 6.0, file_path, i, i,
                stripped, "iac_terraform",
            ))

        # IAM wildcard
        if re.search(r'"Action"\s*:\s*"\*"', stripped) and re.search(r'"Resource"\s*:\s*"\*"', stripped):
            findings.append(_make(
                "iac.terraform.iam_wildcard",
                "IAM policy with Action:* and Resource:*",
                "Wildcard IAM policies grant unrestricted access to all AWS resources.",
                "critical", 9.5, file_path, i, i,
                stripped, "iac_terraform",
            ))

        # CloudTrail disabled
        if re.search(r"enable_logging\s*=\s*false", stripped, re.IGNORECASE):
            findings.append(_make(
                "iac.terraform.cloudtrail_disabled",
                "CloudTrail logging disabled",
                "Disabled CloudTrail removes the audit trail needed for incident response.",
                "medium", 5.5, file_path, i, i,
                stripped, "iac_terraform",
            ))

    return findings


# ── IaC entry point ───────────────────────────────────────────────────────────


def scan_file_iac(file_path: str, source: str) -> list[RawFinding]:
    """Dispatch IaC scanning to the appropriate module based on file type.

    Args:
        file_path: Relative file path.
        source: File content.

    Returns:
        List of RawFinding instances.
    """
    if _is_dockerfile(file_path):
        return _scan_dockerfile(file_path, source)
    if _is_k8s_manifest(file_path, source):
        return _scan_k8s(file_path, source)
    if _is_terraform(file_path):
        return _scan_terraform(file_path, source)
    return []


# ── Helper ────────────────────────────────────────────────────────────────────


def _make(
    rule_id: str,
    title: str,
    description: str,
    severity: str,
    cvss: float,
    file_path: str,
    start_line: int,
    end_line: int,
    snippet: str,
    category: str,
) -> RawFinding:
    return RawFinding(
        rule_id=rule_id,
        title=title,
        description=description,
        severity=severity,
        cvss_score=cvss,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
        category=category,
        extra={"engine": "iac"},
    )
