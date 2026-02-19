import copy
import csv
import importlib
import json
import random
from abc import ABCMeta, abstractmethod
from typing import OrderedDict, Dict, List, Optional

from api.messages import AssistantResponseMessage
from shared_task.sessions import Session, SessionManager
from shared_task.topic import Topic
from simulation.user import User, UserUtterance, DummyUser, UnrestrictedUserSimulator


class SharedTask(metaclass=ABCMeta):
    """Abstract class to configure shared tasks."""

    name: str
    topics: OrderedDict[str, Topic]
    users_per_topic: Dict[str, List[User]]
    debug_users_per_topic: Dict[str, List[User]]

    users_by_id: Dict[str, User]

    def __init__(self, name):
        self.name = name

        self.topics = OrderedDict()
        self.users_per_topic = {}
        self.debug_users_per_topic = {}

        self.users_by_id = {}

    def _add_topic(self, topic: Topic):
        self.topics[topic.id] = topic

    def _add_user(self, topic_id: str, user: User):
        if topic_id not in self.users_per_topic:
            self.users_per_topic[topic_id] = []

        self.users_per_topic[topic_id].append(user)
        self.users_by_id[user.id] = user

    def _add_debug_user(self, topic_id: str, user: User):
        if topic_id not in self.debug_users_per_topic:
            self.debug_users_per_topic[topic_id] = []

        self.debug_users_per_topic[topic_id].append(user)
        self.users_by_id[user.id] = user

    @abstractmethod
    def initialize(self):
        pass

    @classmethod
    def init_session(cls, run, debug: bool) -> Optional[Session]:
        """
        Initialize a new session for the given participant run on the next available topic.

        :param run: The current participant run for which the session should be initialized.
        :param debug: Whether this run is a debugging run or not.
        :return: A new session object or None in case there are no topics left.
        """
        if not run.has_next_topic():
            return None

        task_manager = SharedTaskManager()
        topic = run.next_topic()
        topic_id = topic.id

        if debug:
            user = random.choice(
                task_manager.active_task.debug_users_per_topic[topic_id]
            )
        else:
            user = random.choice(task_manager.active_task.users_per_topic[topic_id])

        session_manager = SessionManager()
        session = session_manager.create_session(run.run_meta, user.id, topic_id)

        run.sessions[topic_id] = session

        return session

    @classmethod
    def update_session(
        cls,
        session: Session,
        utterance: Optional[UserUtterance] = None,
        response: Optional[AssistantResponseMessage] = None,
    ):
        if utterance is not None:
            session.history.append({"role": "user", "content": utterance.content})
            session.user_meta.append(copy.deepcopy(utterance.meta))

        if response is not None:
            session.history.append({"role": "assistant", "content": response.response})

            session.assistant_meta.append(copy.deepcopy(response.meta))


"""
==========================
REPOSITORY OF SHARED TASKS
==========================
"""


class DummySharedTask(SharedTask):
    """Dummy shared task for testing purposes."""

    def __init__(self):
        super().__init__("dummy")

    def initialize(self):
        self._add_topic(Topic("dummy1", "Why is the sky blue?"))
        self._add_topic(Topic("dummy2", "Why is the sky not green?"))

        for _id, topic in self.topics.items():
            self._add_user(_id, DummyUser(self.topics))
            self._add_debug_user(_id, DummyUser(self.topics))


class TREC_iKAT25(SharedTask):
    topics_path = "data/trec-ikat25/2025_test_topics.json"
    users_path = "data/trec-ikat25/simulation-data.csv"

    def __init__(self):
        super().__init__("trec-ikat25")

    def initialize(self):
        self._load_topics()
        self._load_users()

    @classmethod
    def update_session(
        cls,
        session: Session,
        utterance: Optional[UserUtterance] = None,
        response: Optional[AssistantResponseMessage] = None,
    ):
        super().update_session(session, utterance, response)

        if utterance is not None:
            session.user_meta.append(
                {
                    "rubric": utterance.meta["rubric"],
                    "rubric_score": utterance.meta["rubric_score"],
                }
            )

    def _load_topics(self):
        with open(self.topics_path, "r") as f:
            topics = json.load(f)
            for topic in topics:
                self._add_topic(Topic(topic["number"], topic["title"]))

    def _load_users(self):

        with open(self.users_path, "r") as f:
            reader = csv.reader(f, delimiter=";")
            _ = next(reader)
            for row in reader:
                topic_id = row[0].replace("Persona_", "").replace("_", "-").strip()
                ptkb = [p.strip() for p in row[1].strip().split(";")]
                rubrics = {
                    topic_id: [
                        row[i] for i in range(2, len(row)) if row[i].strip() != ""
                    ]
                }

                user = UnrestrictedUserSimulator(row[0], self.topics, rubrics, ptkb)

                self._add_debug_user(topic_id, user)

                user = UnrestrictedUserSimulator(row[0], self.topics, rubrics, ptkb)

                self._add_user(topic_id, user)


class SharedTaskManager:
    _instance = None

    active_task: Optional[SharedTask] = None

    def __init__(self):
        if not hasattr(self, "shared_tasks"):
            self.shared_tasks = {}

            modname, _, clsname = "shared_task.shared_task.SharedTask".rpartition(".")
            mod = importlib.import_module(modname)
            cls = getattr(mod, clsname)

            for task in cls.__subclasses__():
                task_instance = task()
                self.shared_tasks[task_instance.name] = task_instance

            self.active_task = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SharedTaskManager, cls).__new__(cls, *args, **kwargs)

        return cls._instance

    def set_active_task(self, task_name: str):
        self.active_task = self.shared_tasks[task_name]
