import csv
import importlib
import json
from abc import ABCMeta, abstractmethod
from typing import OrderedDict

import simulation
from shared_task.topic import Topic


class SharedTask(metaclass=ABCMeta):
    """Abstract class to configure shared tasks."""

    def __init__(self, name):
        self.name = name

        self.topics = OrderedDict()
        self.users_per_topic = {}
        self.debug_users_per_topic = {}

    @abstractmethod
    def initialize(self):
        pass


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
        self.topics["dummy1"] = Topic("dummy1", "Why is the sky blue?")
        self.topics["dummy2"] = Topic("dummy2", "Why is the sky not green?")

        for _id, topic in self.topics.items():
            self.users_per_topic[_id] = [simulation.user.DummyUser()]
            self.debug_users_per_topic[_id] = [simulation.user.DummyUser()]



class TREC_iKAT25(SharedTask):
    topics_path = "data/2025_test_topics.json"
    users_path = "data/simulation-data.csv"

    def __init__(self):
        super().__init__("trec-ikat25")

    def initialize(self):
        self._load_topics()
        self._load_users()

    def _load_topics(self):
        with open(self.topics_path, "r") as f:
            topics = json.load(f)
            for topic in topics:
                self.topics[topic["number"]] = Topic(topic["number"], topic["title"])

    def _load_users(self):
        with open(self.users_path, "r") as f:
            reader = csv.reader(f, delimiter=";")
            _ = next(reader)
            for row in reader:
                topic_id = row[0].replace("Persona_", "").replace("_", "-").strip()
                persona_statements = [p.strip() for p in row[1].strip().split(";")]
                topics = {topic_id: self.topics[topic_id]}
                trajectory = {topic_id: [row[i] for i in range(2, len(row)) if row[i].strip() != ""]}

                user = simulation.user.PTKBUserWithoutGuidance(
                    row[0],
                    topics,
                    trajectory,
                    persona_statements
                )

                self.debug_users_per_topic[topic_id] = [user]

                user = simulation.user.PTKBUserWithoutGuidance(
                    row[0],
                    topics,
                    trajectory,
                    persona_statements
                )

                self.users_per_topic[topic_id] = [user]


class SharedTaskManager:
    _instance = None

    def __init__(self):
        if not hasattr(self, 'shared_tasks'):
            self.shared_tasks = {}

            modname, _, clsname = "shared_task.shared_task.SharedTask".rpartition('.')
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