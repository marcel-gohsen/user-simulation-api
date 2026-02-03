import uuid

from starlette.testclient import TestClient

from main import setup_app

client = TestClient(setup_app())

def test_run_start():
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
        },
        json={
            "run_id": "test-run-simple",
            "description": "This is a very basic test run.",
            "track_persona": False,
        }
    )

    assert response.status_code == 200


def test_run_empty_fields():
    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
        },
        json={
            "run_id": "",
            "description": "This is a very basic test run.",
        }
    )

    assert response.status_code == 400

    response = client.post(
        "/debug/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
        },
        json={
            "run_id": "Blah",
            "description": "",
        }
    )

    assert response.status_code == 400


def test_full_conversation():
    random = uuid.uuid4().hex

    response = client.post(
        "/run/start",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
        },
        json={
            "run_id": random,
            "description": "This is a test run.",
        }
    )

    try:
        assert response.status_code == 200
    except AssertionError:
        raise RuntimeError(response.json())

    while True:
        response = client.post(
            "/run/continue",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
            },
            json={
                "run_id": random,
                "response": "I don't know."
            }
        )

        assert response.status_code == 200

        if response.json()["last_response_of_run"]:
            break

    response = client.post(
        "/run/continue",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer NzI0OGJlZGEyNzNlY2NkOTFiNjA0N2UxM2I4NmQyODg=",
        },
        json={
            "run_id": random,
            "response": "I don't know."
        }
    )

    assert response.status_code == 400