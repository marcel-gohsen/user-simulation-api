import json
import uuid
from dataclasses import asdict

import pytest
from pydantic import ValidationError, TypeAdapter
from starlette.testclient import TestClient

from api.messages import UserUtterance, RunMeta, AssistantResponse
from security.authenticator import Authenticator
from shared_task.shared_task import SharedTaskManager


@pytest.fixture
def client():
    from main import setup_app, setup_storage
    task_name = "dummy"
    task_manager = SharedTaskManager()
    task_manager.set_active_task(task_name)
    task_manager.active_task.initialize()
    setup_storage(task_name)
    return TestClient(setup_app())


@pytest.fixture
def admin_credentials(client):
    authenticator = Authenticator()
    name = "_test_admin"
    password = uuid.uuid4().hex
    authenticator.add_admin(name, password)
    yield name, password
    authenticator.rm_admin(name)


@pytest.fixture(autouse=True)
def team_token(client):
    authenticator = Authenticator()
    name = "_test_team"
    authenticator.rm_team(name)
    yield authenticator.add_team(name)
    authenticator.rm_team(name)


@pytest.mark.integration
def test_run_start(client, team_token):
    run_meta = RunMeta("_test-run-start", "This is a test run.", False)
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {team_token}",
        },
        json=asdict(run_meta)
    )

    assert response.status_code == 200

    data = response.content.decode("utf-8")
    try:
        TypeAdapter(UserUtterance).validate_json(data)
    except ValidationError as e:
        pytest.fail(f"API response is not valid!\n{str(e)}")


@pytest.mark.integration
def test_full_run(client, team_token):
    run_meta = RunMeta("_test-run-full", "This is a test run.", False)
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {team_token}",
        },
        json=asdict(run_meta)
    )

    assert response.status_code == 200

    data = response.content.decode("utf-8")

    utterance = None
    try:
        utterance = TypeAdapter(UserUtterance).validate_json(data)
    except ValidationError as e:
        pytest.fail(f"API response is not valid!\n{str(e)}")

    while True:
        if utterance.last_response_of_run:
            break

        assistant_response = AssistantResponse(
            run_meta.run_id,
            "This is a test response!",
            {"docA": 0.9, "docB": 0.5},
            None
        )

        response = client.post(
            "/debug/continue",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {team_token}",
            },
            json=asdict(assistant_response)
        )

        assert response.status_code == 200

        data = response.content.decode("utf-8")
        try:

            utterance = TypeAdapter(UserUtterance).validate_json(data)
        except ValidationError as e:
            pytest.fail(f"API response is not valid!\n{str(e)}")


@pytest.mark.integration
def test_malformed_request(client, team_token):
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {team_token}",
        },
        json={"run_id": None}
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_unauthorized_request(client):
    run_meta = RunMeta("_test-run-auth", "This is a test run.", False)
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer d3JvbmctdG9rZW4=",
        },
        json=asdict(run_meta)
    )

    assert response.status_code == 401