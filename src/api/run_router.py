import datetime
import json
import logging
from logging import Logger
from typing import Annotated, Tuple, Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.security import HTTPBasicCredentials
from starlette import status
from starlette.responses import JSONResponse, Response

from api.auth_router import admin_auth
from api.messages import UserUtteranceMessage, RunMetaMessage, AssistantResponseMessage
from config import CONFIG
from security.authenticator import authenticate
from security.budget_tracker import check_budget
from security.request_tracker import RequestTracker
from shared_task.participant_run import RunManager
from shared_task.sessions import SessionManager
from shared_task.shared_task import SharedTaskManager

run_router = APIRouter(
    prefix=f"/{CONFIG['api']['run']['name']}",
)

debug_router = APIRouter(
    prefix=f"/{CONFIG['api']['debug']['name']}",
)

"""
===========
API ROUTES.
===========
"""


@run_router.post(
    "/start",
    response_model=UserUtteranceMessage,
    **CONFIG["api"]["run"]["docs"]["start"],
)
@debug_router.post(
    "/start",
    response_model=UserUtteranceMessage,
    **CONFIG["api"]["debug"]["docs"]["start"],
)
def start(
    request: Request,
    team_id: Annotated[str, Depends(authenticate)],
    run_meta: RunMetaMessage,
) -> UserUtteranceMessage:
    debug_mode, logger = check_debug_mode(request)
    api = "run"
    if debug_mode:
        api = "debug"

    run_manager = RunManager(debug=debug_mode)
    check_budget(
        run_manager,
        team_id,
        CONFIG["api"][api]["name"],
        CONFIG["api"][api]["limits"]["value"],
        CONFIG["api"][api]["limits"]["unit"],
    )

    check_request(
        team_id,
        run_meta.run_id,
        run_meta,
        run_manager,
        run_must_exists=False,
        debug_mode=debug_mode,
    )

    run_meta.team_id = team_id

    run = run_manager.create_run(run_meta)
    logger.debug(f'Team "{team_id}" starts run "{run_meta.run_id}".')
    task_manager = SharedTaskManager()
    active_task = task_manager.active_task

    try:
        session = active_task.init_session(run, debug_mode)
    except AssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=f'Active run with the name "{run_meta.run_id}" already exists '
            f"or a run with that name was already completed before.",
        )

    user = active_task.users_by_id[session.user_id]
    utterance = user.initiate(session)
    active_task.update_session(session, utterance=utterance)

    return UserUtteranceMessage(
        datetime.datetime.now().isoformat(),
        run_meta.run_id,
        session.topic_id,
        session.user_id,
        utterance.content,
        session.history,
        False,
        False,
    )


@run_router.post(
    "/continue",
    response_model=UserUtteranceMessage,
    **CONFIG["api"]["run"]["docs"]["continue"],
)
@debug_router.post(
    "/continue",
    response_model=UserUtteranceMessage,
    **CONFIG["api"]["debug"]["docs"]["continue"],
)
def continue_conversation(
    request: Request,
    team_id: Annotated[str, Depends(authenticate)],
    assistant: AssistantResponseMessage,
):
    debug_mode, logger = check_debug_mode(request)
    api = "run"
    if debug_mode:
        api = "debug"

    run_manager = RunManager(debug=debug_mode)
    try:
        if debug_mode:
            check_budget(
                run_manager,
                team_id,
                CONFIG["api"][api]["name"],
                CONFIG["api"][api]["limits"]["value"],
                CONFIG["api"][api]["limits"]["unit"],
            )
    except HTTPException as e:
        # prevent running out of budget while working on the very last topic of the last allowed run/session
        check_request(
            team_id,
            assistant.run_id,
            None,
            run_manager,
            run_must_exists=True,
            debug_mode=debug_mode,
        )

        session_manager = SessionManager()
        session = session_manager.get_session(team_id, assistant.run_id)

        if session is None:
            raise e

    check_request(
        team_id,
        assistant.run_id,
        None,
        run_manager,
        run_must_exists=True,
        debug_mode=debug_mode,
    )

    run = run_manager.get_active_run(assistant.run_id)

    session_manager = SessionManager()
    session = session_manager.get_session(team_id, assistant.run_id)

    task_manager = SharedTaskManager()
    active_task = task_manager.active_task

    if session is None:
        # session of prior topic ended
        session = active_task.init_session(run, debug_mode)
        if session is None:
            # no new topics
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'No more open topics for run "{run.run_meta.run_id}". Run was finished!',
            )

        logger.debug(
            f'Team "{team_id}" starts new session on topic "{session.topic_id}".'
        )
    else:
        logger.debug(
            f'Team "{team_id}" continues session on topic "{session.topic_id}".'
        )

    user = active_task.users_by_id[session.user_id]

    if len(session.history) == 0:
        utterance = user.initiate(session)
    else:
        active_task.update_session(session, response=assistant)
        utterance = user.respond(session)

    active_task.update_session(session, utterance=utterance)
    if len(session.history) >= 2:
        assert (
            session.history[-1]["role"] == "user"
            and session.history[-2]["role"] == "assistant"
        )

    api = "run"
    if debug_mode:
        api = "debug"

    if not len(session.history) == 1:
        request_tracker = RequestTracker()
        request_tracker.register_request(
            run.run_meta.run_id,
            team_id,
            session.id,
            session.topic_id,
            session.user_id,
            api,
            session.history[-3]["content"],
            assistant.response,
            assistant.citations,
            session.user_meta[-2] if len(session.user_meta) > 1 else {},
            assistant.meta,
        )

    if utterance.end_of_session:
        session_manager.terminate_session(run.run_meta)

        request_tracker = RequestTracker()
        request_tracker.register_request(
            run.run_meta.run_id,
            team_id,
            session.id,
            session.topic_id,
            session.user_id,
            api,
            utterance.content,
            None,
            {},
            utterance.meta,
            {},
        )

    return UserUtteranceMessage(
        datetime.datetime.now().isoformat(),
        run.run_meta.run_id,
        session.topic_id,
        user.id,
        utterance.content,
        session.history,
        utterance.end_of_session,
        utterance.end_of_session and not run.has_next_topic(),
    )


@run_router.get("/session", **CONFIG["api"]["run"]["docs"]["session"])
@debug_router.get("/session", **CONFIG["api"]["debug"]["docs"]["session"])
def session(
    request: Request, team_id: Annotated[str, Depends(authenticate)], run_id: str
):
    debug_mode, logger = check_debug_mode(request)

    run_manager = RunManager(debug=debug_mode)
    check_request(
        team_id, run_id, None, run_manager, run_must_exists=True, debug_mode=debug_mode
    )

    run = run_manager.get_active_run(run_id)

    session_manager = SessionManager()
    session = session_manager.get_session(team_id, run_id)

    return UserUtteranceMessage(
        datetime.datetime.now().isoformat(),
        run.run_meta.run_id,
        session.topic_id,
        session.user_id,
        session.history[-1]["content"],
        session.history,
        False,
        False,
    )


@run_router.get("/status", **CONFIG["api"]["run"]["docs"]["status"])
def run_status(team_id: Annotated[str, Depends(authenticate)], run_id: str):
    run_manager = RunManager()

    if not run_manager.run_exists(run_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f'Run "{run_id}" does not exist.'
        )

    return JSONResponse(run_manager.get_status(run_id), status_code=status.HTTP_200_OK)


@run_router.get("/dump", **CONFIG["api"]["run"]["docs"]["dump"])
def run_dump(team_id: Annotated[str, Depends(authenticate)], run_id: str):
    run_manager = RunManager()
    if not run_manager.run_exists(run_id, team_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f'Run "{run_id}" does not exist.'
        )

    response = "\n".join([json.dumps(s) for s in run_manager.dump(run_id)])
    return Response(
        response, status_code=status.HTTP_200_OK, media_type="application/x-ndjson"
    )


@run_router.get("/dump-all", **CONFIG["api"]["run"]["docs"]["dump-all"])
def run_dump_all(credentials: Annotated[HTTPBasicCredentials, Depends(admin_auth)]):
    run_manager = RunManager()

    response = "\n".join([json.dumps(s) for s in run_manager.dump_all()])
    return Response(
        response, status_code=status.HTTP_200_OK, media_type="application/x-ndjson"
    )


"""
===============
HELPER METHODS.
===============
"""


def check_debug_mode(request: Request) -> Tuple[bool, Logger]:
    debug_mode = "debug" in request.url.path

    if debug_mode:
        logger = logging.getLogger("DebugAPI")
        logger.setLevel(logging.DEBUG)
    else:
        logger = logging.getLogger("RunAPI")
        logger.setLevel(logging.INFO)

    return debug_mode, logger


def check_request(
    team_id: str,
    run_id: str,
    run_meta: Optional[RunMetaMessage],
    run_manager: RunManager,
    run_must_exists: bool = False,
    debug_mode: bool = False,
) -> bool:
    run = run_manager.get_active_run(run_id)

    if run_must_exists:
        if run is None:
            if (
                run_manager.run_exists(run_id, team_id)
                and run_manager.get_status(run_id)["status"] != "complete"
            ):
                run = run_manager.recover_run(run_id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                    detail=f'Run with the name "{run_id}" does not exist or was completed.',
                )

        run_meta = run.run_meta
        if team_id != run_meta.team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Run with the name "{run_meta.run_id}" does not belong to team "{team_id}".',
            )
    else:
        if len(run_meta.run_id) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Run name cannot be empty. Please provide a meaningful name.",
            )

        if len(run_meta.description) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Run description cannot be empty. Please provide a meaningful description.",
            )

        if run is not None or (run_manager.run_exists(run_id) and not debug_mode):
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail=f'Active run with the name "{run_meta.run_id}" already exists or a run with that name was already completed before.',
            )

        # check for the case where a request is submitted with a team name that doesn't match
        # the token in the header. the check for None is required because the team_id field is
        # optional in the request and will probably not be set in most cases
        if run_meta.team_id is not None and team_id != run_meta.team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Team name {run_meta.team_id} does not match token",
            )

    return True
