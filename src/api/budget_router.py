from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette import status
from starlette.responses import JSONResponse

from config import CONFIG
from security.authenticator import authenticate, Authenticator
from security.budget_tracker import BudgetTracker, check_budget
from data.trec_run import RunManager

router = APIRouter(
    prefix="/budget",
)

admin_auth = HTTPBasic()

@router.get("/check", **CONFIG["api"]["budget"]["docs"]["check"])
def check(teamname: Annotated[str, Depends(authenticate)]):
    from config import CONFIG

    remaining_credits = {}
    apis = ["debug", "run"]
    for api in apis:
        try:
            remaining = check_budget(
                RunManager(debug=api == "debug"),
                teamname,
                api,
                CONFIG["api"][api]["limits"]["value"],
                CONFIG["api"][api]["limits"]["unit"],
            )
        except HTTPException:
            remaining = 0

        remaining_credits[api] = {
            "remaining": remaining,
            "unit": CONFIG["api"][api]["limits"]["unit"]
        }

    return JSONResponse({"remaining": remaining_credits})

@router.get("/reset", include_in_schema=False)
def reset_budget(credentials: Annotated[HTTPBasicCredentials, Depends(admin_auth)], teamname: str, api: Literal["debug", "run"]):
    authenticator = Authenticator()
    if not authenticator.authenticate_admin(
            credentials.username.strip(), credentials.password.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    budget_tracker = BudgetTracker()
    budget_tracker.reset_credits(teamname, api)

    return JSONResponse({"status": "success"})
