import uuid

from simulation.user import User
from api.messages import RunMeta


class Session:
    def __init__(self, team_id: str, user: User, topic_id: str):
        self.user = user
        self.team_id = team_id
        self.topic_id = topic_id
        self.subtopics = []
        self.chat_history = []
        self._id = uuid.uuid4().hex


class SessionManager(object):
    _instance = None

    def __init__(self):
        if not hasattr(self, "sessions"):
            self.sessions: dict[str, dict[str, Session]] = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def get_session(self, teamname: str, run_id: str) -> Session | None:
        runs = self.sessions.get(teamname, None)
        if runs is None:
            return None

        return runs.get(run_id, None)

    def create_session(self, run: RunMeta, user: User, topic_id: str) -> Session:
        assert run.team_id is not None
        if run.team_id in self.sessions:
            assert run.run_id not in self.sessions[run.team_id]
        else:
            self.sessions[run.team_id] = {}
        new_session = Session(run.team_id, user, topic_id)
        self.sessions[run.team_id][run.run_id] = new_session
        return new_session

    def terminate_session(self, run: RunMeta) -> None:
        assert run.team_id is not None
        assert run.team_id in self.sessions and run.run_id in self.sessions[run.team_id]
        del self.sessions[run.team_id][run.run_id]
