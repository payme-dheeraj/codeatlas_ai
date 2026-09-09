"""Security scanner endpoints.

Routes:
  POST   /security/scans                  — trigger a scan
  GET    /security/scans/{scan_id}        — get scan status/summary
  GET    /repos/{repo_id}/scans           — list scans for a repo
  GET    /security/scans/{scan_id}/findings — list findings
  POST   /security/findings/{id}/suppress — suppress a finding
  GET    /security/scans/{scan_id}/report — export report
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_optional_current_user_id as get_current_user_id, get_security_service
from app.schemas.security import (
    FindingListResponse,
    ReportFormat,
    ScanDetailResponse,
    ScanRequest,
    ScanSummaryResponse,
    SuppressFindingRequest,
)
from app.services.security_service import SecurityService

router = APIRouter(tags=["security"])


@router.post(
    "/security/scans",
    response_model=ScanSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a security scan",
    responses={
        202: {"description": "Scan accepted and queued"},
        401: {"description": "Not authenticated"},
    },
)
async def trigger_scan(
    request: ScanRequest,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> ScanSummaryResponse:
    """Queue a new security scan for a repository.

    Args:
        request: Scan parameters (repo_id, scan_types, options).
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        ScanSummaryResponse with the queued scan's metadata.
    """
    return await service.trigger_scan(request)


@router.get(
    "/security/scans/{scan_id}",
    response_model=ScanSummaryResponse,
    summary="Get scan status",
    responses={
        200: {"description": "Scan summary"},
        401: {"description": "Not authenticated"},
        404: {"description": "Scan not found"},
    },
)
async def get_scan(
    scan_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> ScanSummaryResponse:
    """Retrieve status and summary for a security scan.

    Args:
        scan_id: UUID of the scan.
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        ScanSummaryResponse.

    Raises:
        HTTPException 404: If the scan does not exist.
    """
    result = await service.get_scan(scan_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )
    return result


@router.get(
    "/repos/{repo_id}/scans",
    response_model=list[ScanSummaryResponse],
    summary="List security scans for a repository",
    responses={
        200: {"description": "List of scans"},
        401: {"description": "Not authenticated"},
    },
)
async def list_scans(
    repo_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> list[ScanSummaryResponse]:
    """Return paginated security scans for a repository.

    Args:
        repo_id: UUID of the repository.
        page: Page number.
        limit: Page size.
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        List of ScanSummaryResponse.
    """
    scans, _ = await service.list_scans(repo_id, page=page, limit=limit)
    return scans


@router.get(
    "/security/scans/{scan_id}/findings",
    response_model=FindingListResponse,
    summary="List findings for a scan",
    responses={
        200: {"description": "Paginated findings"},
        401: {"description": "Not authenticated"},
        404: {"description": "Scan not found"},
    },
)
async def list_findings(
    scan_id: uuid.UUID,
    severity: str | None = Query(default=None, description="Filter: critical|high|medium|low|info"),
    scanner: str | None = Query(default=None, description="Filter: secrets|sast|iac"),
    file_path: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> FindingListResponse:
    """Return paginated, filtered findings for a security scan.

    Args:
        scan_id: UUID of the scan.
        severity: Optional severity filter.
        scanner: Optional scanner module filter.
        file_path: Optional file path filter.
        page: Page number.
        limit: Page size.
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        FindingListResponse with paginated items.
    """
    return await service.list_findings(
        scan_id,
        severity=severity,
        scanner=scanner,
        file_path=file_path,
        page=page,
        limit=limit,
    )


@router.post(
    "/security/findings/{finding_id}/suppress",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Suppress a finding (false positive or accepted risk)",
    responses={
        204: {"description": "Finding suppressed"},
        401: {"description": "Not authenticated"},
        404: {"description": "Finding not found"},
    },
)
async def suppress_finding(
    finding_id: uuid.UUID,
    body: SuppressFindingRequest,
    is_fp: bool = Query(default=False, alias="false_positive", description="Mark as false positive"),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> Response:
    """Suppress a finding as a false positive or accepted risk.

    Args:
        finding_id: UUID of the finding to suppress.
        body: Suppression reason.
        is_fp: If true, marks as false positive.
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException 404: If the finding does not exist.
    """
    found = await service.suppress_finding(finding_id, is_false_positive=is_fp)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/security/scans/{scan_id}/report",
    summary="Export scan report",
    description=(
        "Download the full security scan report in JSON, SARIF 2.1, CSV, or Markdown format. "
        "SARIF is compatible with GitHub Code Scanning and VS Code."
    ),
    responses={
        200: {"description": "Report file content"},
        401: {"description": "Not authenticated"},
        404: {"description": "Scan not found"},
    },
)
async def export_report(
    scan_id: uuid.UUID,
    fmt: ReportFormat = Query(default=ReportFormat.json, alias="format"),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: SecurityService = Depends(get_security_service),
) -> Response:
    """Download the security report in the specified format.

    Args:
        scan_id: UUID of the scan.
        fmt: Report format (json | sarif | csv | markdown).
        _: Authenticated user UUID.
        service: Injected SecurityService.

    Returns:
        File download response with appropriate Content-Type.

    Raises:
        HTTPException 404: If the scan does not exist.
    """
    content, content_type, filename = await service.export_report(scan_id, fmt.value)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
