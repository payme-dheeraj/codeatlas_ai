"""User management endpoints (admin operations and self-service profile updates).

Route prefix: /api/v1/users
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_auth_service, get_current_user_id, require_role
from app.schemas.user import AdminUpdateUserRequest, UpdateProfileRequest, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    responses={
        200: {"description": "User profile"},
        401: {"description": "Not authenticated"},
    },
)
async def get_my_profile(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Return the profile of the authenticated user.

    Args:
        user_id: Injected from JWT by get_current_user_id.
        service: Injected AuthService.

    Returns:
        UserResponse for the current user.

    Raises:
        HTTPException 404: If the user record has been deleted.
    """
    profile = await service.get_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )
    return profile


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update profile",
    responses={
        200: {"description": "Updated profile"},
        401: {"description": "Not authenticated"},
        409: {"description": "Username already taken"},
    },
)
async def update_my_profile(
    payload: UpdateProfileRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Apply partial updates to the authenticated user's profile.

    Args:
        payload: Fields to update (username).
        user_id: Injected from JWT.
        service: Injected AuthService.

    Returns:
        Updated UserResponse.

    Raises:
        HTTPException 409: If the requested username is already taken.
    """
    try:
        return await service.update_profile(user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


# ── Admin-only endpoints ───────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users (admin only)",
    responses={
        200: {"description": "All user accounts"},
        401: {"description": "Not authenticated"},
        403: {"description": "Admin role required"},
    },
)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_role("admin")),
    service: AuthService = Depends(get_auth_service),
) -> list[UserResponse]:
    """Return a paginated list of all platform users.

    Requires admin role.

    Args:
        page: 1-indexed page number.
        limit: Items per page (max 100).
        _: Role guard (admin required).
        service: Injected AuthService.

    Returns:
        List of UserResponse objects.
    """
    users, _ = await service._user_repo.list(
        offset=(page - 1) * limit,
        limit=limit,
    )
    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID (admin only)",
    responses={
        200: {"description": "User profile"},
        401: {"description": "Not authenticated"},
        403: {"description": "Admin role required"},
        404: {"description": "User not found"},
    },
)
async def get_user(
    user_id: uuid.UUID,
    _: None = Depends(require_role("admin")),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Retrieve any user by UUID. Requires admin role.

    Args:
        user_id: Target user UUID.
        _: Role guard.
        service: Injected AuthService.

    Returns:
        UserResponse.

    Raises:
        HTTPException 404: If the user does not exist.
    """
    profile = await service.get_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )
    return profile


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user's role or status (admin only)",
    responses={
        200: {"description": "Updated user"},
        401: {"description": "Not authenticated"},
        403: {"description": "Admin role required"},
        404: {"description": "User not found"},
    },
)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequest,
    _: None = Depends(require_role("admin")),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Change a user's role or active status. Requires admin role.

    Args:
        user_id: UUID of the user to modify.
        payload: role and/or is_active update.
        _: Role guard.
        service: Injected AuthService.

    Returns:
        Updated UserResponse.

    Raises:
        HTTPException 404: If the user does not exist.
    """
    try:
        return await service.admin_update_user(user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
