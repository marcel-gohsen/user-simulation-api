import csv
import json
import tomllib
from collections import OrderedDict

import yaml
from watchdog.events import FileSystemEventHandler, DirModifiedEvent, FileModifiedEvent
from watchdog.observers import Observer

import simulation.user
from data.topic import Topic

CONFIG_PATH = "config/api-conf.yml"
TOPICS_PATH = "data/2025_test_topics.json"
USERS_PATH = "data/simulation-data.csv"
DATABASE_PATH = "database/trec-ikat-2025.db"
SCHEMA_PATH = "data/trec-ikat-2025-schema.sql"
TOPICS = OrderedDict()
DEBUG_USERS_PER_TOPIC = {}
RUN_USERS_PER_TOPIC = {}

with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.load(f, Loader=yaml.SafeLoader)

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
        CONFIG["api"]["version"] = data["project"]["version"]


with open(TOPICS_PATH, "r") as f:
    topics = json.load(f)
    for topic in topics:
        TOPICS[topic["number"]] = Topic(topic["number"], topic["title"])


with open(USERS_PATH, "r") as f:
    reader =  csv.reader(f, delimiter=";")
    header = next(reader)
    for row in reader:
        topic_id = row[0].replace("Persona_", "").replace("_", "-").strip()
        persona_statements = [p.strip() for p in row[1].strip().split(";")]
        topics = {topic_id: TOPICS[topic_id]}
        trajectory = {topic_id: [row[i] for i in range(2, len(row)) if row[i].strip() != ""]}

        user = simulation.user.PTKBUserWithGuidance(
            row[0],
            topics,
            trajectory,
            persona_statements
        )

        DEBUG_USERS_PER_TOPIC[topic_id] = [user]

        user = simulation.user.OpenAIPTKBUserWithGuidance(
            row[0],
            topics,
            trajectory,
            persona_statements
        )

        RUN_USERS_PER_TOPIC[topic_id] = [user]




class ConfigChangeHandler(FileSystemEventHandler):
    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        super().on_modified(event)
        global CONFIG
        with open(CONFIG_PATH, "r") as f:
            CONFIG = yaml.load(f, Loader=yaml.SafeLoader)


observer = Observer()
observer.schedule(ConfigChangeHandler(), CONFIG_PATH, recursive=False)
observer.start()
