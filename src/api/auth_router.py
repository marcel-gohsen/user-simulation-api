from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette import status
from starlette.responses import JSONResponse

from config import CONFIG
from security.authenticator import authenticate, Authenticator

router = APIRouter(
    prefix="/auth",
)

admin_auth = HTTPBasic()


@router.get("/verify", **CONFIG["api"]["auth"]["docs"]["verify"])
def verify(team_id: Annotated[str, Depends(authenticate)]):
    """Verifies if authentication token is valid."""
    return JSONResponse({"team_id": team_id})


@router.get("/issue-token", include_in_schema=False)
def issue_token(
    credentials: Annotated[HTTPBasicCredentials, Depends(admin_auth)],
    name: str
):
    """Registers a new team and issues a token (requires admin privileges)."""
    authenticator = Authenticator()
    if not authenticator.authenticate_admin(
        credentials.username.strip(), credentials.password.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    try:
        token = authenticator.add_team(name)

        return JSONResponse({"token": token})
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
