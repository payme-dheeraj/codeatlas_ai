"""Authentication endpoints: register, login, refresh, logout, API keys.

Route prefix: /api/v1/auth
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_current_user_id, get_auth_service
from app.schemas.auth import (
    ApiKeyListItem,
    ApiKeyResponse,
    ChangePasswordRequest,
    CreateApiKeyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses={
        201: {"description": "Account created successfully"},
        409: {"description": "Email or username already registered"},
        422: {"description": "Validation error (password complexity, invalid email, etc.)"},
    },
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Create a new user account.

    Enforces:
    - Unique email address.
    - Unique username.
    - Minimum password complexity (uppercase + digit).

    Args:
        payload: Registration request body.
        service: Injected AuthService.

    Returns:
        The newly created user profile.

    Raises:
        HTTPException 409: If email or username is already taken.
    """
    try:
        return await service.register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


from app.schemas.auth import LoginRequest  # noqa: E402


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    responses={
        200: {"description": "Login successful — returns JWT token pair"},
        401: {"description": "Invalid credentials or inactive account"},
    },
)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Authenticate with email and password and receive JWT tokens.

    Args:
        payload: Email and password credentials.
        service: Injected AuthService.

    Returns:
        TokenResponse containing access_token, refresh_token, and expires_in.

    Raises:
        HTTPException 401: On invalid email, wrong password, or inactive account.
    """
    try:
        return await service.login(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh JWT token pair",
    description=(
        "Exchange a valid refresh token for a new access + refresh token pair. "
        "The submitted refresh token is immediately invalidated (rotation)."
    ),
    responses={
        200: {"description": "New token pair issued"},
        401: {"description": "Refresh token invalid, expired, or already used"},
    },
)
async def refresh_tokens(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Rotate the token pair using a refresh token.

    Args:
        payload: Request body containing the current refresh JWT.
        service: Injected AuthService.

    Returns:
        New TokenResponse with rotated tokens.

    Raises:
        HTTPException 401: On invalid or already-used refresh token.
    """
    try:
        return await service.refresh_tokens(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate a refresh token",
    description="Revokes the provided refresh token. Always returns 204 regardless of token validity.",
)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Revoke a refresh token.

    Args:
        payload: Request body containing the refresh JWT to revoke.
        service: Injected AuthService.
    """
    await service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get authenticated user profile",
    responses={
        200: {"description": "Current user profile"},
        401: {"description": "Not authenticated"},
        404: {"description": "User record not found"},
    },
)
async def get_me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Return the profile of the currently authenticated user.

    Args:
        user_id: Injected from JWT by get_current_user_id dependency.
        service: Injected AuthService.

    Returns:
        UserResponse for the authenticated user.

    Raises:
        HTTPException 404: If the user record no longer exists.
    """
    profile = await service.get_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )
    return profile


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change authenticated user's password",
    responses={
        204: {"description": "Password changed successfully"},
        400: {"description": "Current password is incorrect"},
        401: {"description": "Not authenticated"},
    },
)
async def change_password(
    payload: ChangePasswordRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Update the authenticated user's password.

    Args:
        payload: Current password and new password.
        user_id: Injected from JWT.
        service: Injected AuthService.

    Raises:
        HTTPException 400: If the current password is incorrect.
    """
    try:
        await service.change_password(user_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ── API Keys ───────────────────────────────────────────────────────────────────


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API key",
    description=(
        "Creates a new API key for CI/CD or programmatic access. "
        "The raw key value is shown **only once** in this response."
    ),
    responses={
        201: {"description": "API key created — raw value shown once"},
        401: {"description": "Not authenticated"},
    },
)
async def create_api_key(
    payload: CreateApiKeyRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> ApiKeyResponse:
    """Generate a new API key for the authenticated user.

    Args:
        payload: Key name and optional expiry.
        user_id: Injected from JWT.
        service: Injected AuthService.

    Returns:
        ApiKeyResponse with the one-time raw key value.
    """
    return await service.create_api_key(user_id, payload)


@router.get(
    "/api-keys",
    response_model=list[ApiKeyListItem],
    summary="List active API keys",
    responses={
        200: {"description": "List of active API keys (no raw values)"},
        401: {"description": "Not authenticated"},
    },
)
async def list_api_keys(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> list[ApiKeyListItem]:
    """Return all active API keys for the authenticated user.

    Args:
        user_id: Injected from JWT.
        service: Injected AuthService.

    Returns:
        List of ApiKeyListItem (no raw key values exposed).
    """
    return await service.list_api_keys(user_id)


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    responses={
        204: {"description": "Key revoked"},
        401: {"description": "Not authenticated"},
        404: {"description": "Key not found or not owned by caller"},
    },
)
async def revoke_api_key(
    key_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Revoke (soft-delete) an API key.

    Args:
        key_id: UUID of the API key to revoke.
        user_id: Injected from JWT (ownership enforced).
        service: Injected AuthService.

    Raises:
        HTTPException 404: If the key is not found or belongs to another user.
    """
    revoked = await service.revoke_api_key(key_id, user_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found.",
        )
