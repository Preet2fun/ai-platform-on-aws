# app/core/auth.py
"""
Cognito JWT authentication middleware for FastAPI.
Validates JWT tokens from Cognito User Pool.
"""

from fastapi import HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from typing import Dict, Optional
from functools import lru_cache
from app.core.config import settings

# Security scheme — auto_error=False allows cookie fallback
security = HTTPBearer(auto_error=False)

# JWK client for fetching Cognito public keys (cached)
@lru_cache()
def get_jwks_client():
    """Get cached JWKS client for Cognito public key verification."""
    jwks_url = (
        f"https://cognito-idp.{settings.AWS_REGION}.amazonaws.com/"
        f"{settings.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    )
    return PyJWKClient(jwks_url)


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    request: Request = None,
) -> Dict:
    """
    Verify Cognito JWT token and return user claims.
    Checks Authorization header first, falls back to session_token httpOnly cookie.
    """
    token = None
    if credentials:
        token = credentials.credentials
    
    # Fallback: read from httpOnly cookie
    if not token and request:
        token = request.cookies.get("session_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Get signing key from Cognito JWKS
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Expected issuer URL
        issuer = (
            f"https://cognito-idp.{settings.AWS_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}"
        )
        
        # Verify and decode token
        # Note: Cognito ID tokens have client_id as audience
        # Access tokens have different audience format
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.COGNITO_CLIENT_ID,
            issuer=issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["sub", "exp", "iss"]  # Email not always present
            }
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user(
    token_payload: Dict = Security(verify_token)
) -> Dict:
    """
    Extract user information from validated token.
    
    Args:
        token_payload: Validated JWT payload
        
    Returns:
        dict: User information including:
            - user_id: Cognito user ID (sub claim)
            - email: User email address
            - username: Cognito username
            - auth_time: When user authenticated
            - exp: Token expiration time
    """
    return {
        "user_id": token_payload.get("sub"),
        "email": token_payload.get("email"),
        "username": token_payload.get("cognito:username", token_payload.get("email")),
        "token_use": token_payload.get("token_use"),
        "auth_time": token_payload.get("auth_time"),
        "exp": token_payload.get("exp"),
        "iss": token_payload.get("iss"),
        "aud": token_payload.get("aud")
    }
