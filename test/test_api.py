import uuid

import pytest
from starlette.testclient import TestClient

from security.authenticator import Authenticator


@pytest.fixture
def client():
    from main import setup_app
    return TestClient(setup_app())


@pytest.fixture
def admin_credentials():
    authenticator = Authenticator()
    name = "_test_admin"
    password = uuid.uuid4().hex
    authenticator.add_admin(name, password)
    yield name, password
    authenticator.rm_admin(name)


@pytest.fixture(autouse=True)
def team_token():
    authenticator = Authenticator()
    name = "_test_team"
    yield authenticator.add_team(name)
    authenticator.rm_team(name)


@pytest.mark.integration
def test_run_start(client, team_token):
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {team_token}",
        },
        json={
            "run_id": "test-run-simple",
            "description": "This is a very basic test run.",
            "track_persona": False,
        }
    )

    assert response.status_code == 200

#
# @pytest.mark.integration
# def test_run_empty_fields(client):
#     response = client.post(
#         "/debug/start",
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
#         },
#         json={
#             "run_id": "",
#             "description": "This is a very basic test run.",
#         }
#     )
#
#     assert response.status_code == 400
#
#     response = client.post(
#         "/debug/start",
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
#         },
#         json={
#             "run_id": "Blah",
#             "description": "",
#         }
#     )
#
#     assert response.status_code == 400
#
#
# @pytest.mark.integration
# def test_full_conversation(client):
#     random = uuid.uuid4().hex
#
#     response = client.post(
#         "/run/start",
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
#         },
#         json={
#             "run_id": random,
#             "description": "This is a test run.",
#         }
#     )
#
#     try:
#         assert response.status_code == 200
#     except AssertionError:
#         raise RuntimeError(response.json())
#
#     while True:
#         response = client.post(
#             "/run/continue",
#             headers={
#                 "Content-Type": "application/json",
#                 "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
#             },
#             json={
#                 "run_id": random,
#                 "response": "I don't know."
#             }
#         )
#
#         assert response.status_code == 200
#
#         if response.json()["last_response_of_run"]:
#             break
#
#     response = client.post(
#         "/run/continue",
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
#         },
#         json={
#             "run_id": random,
#             "response": "I don't know."
#         }
#     )
#
#     assert response.status_code == 400