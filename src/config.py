import tomllib

import yaml
from watchdog.events import FileSystemEventHandler, DirModifiedEvent, FileModifiedEvent
from watchdog.observers import Observer

CONFIG_PATH = "config/api-conf.yml"

DATABASE_DIR = "database"
SCHEMA_PATH = "data/db-schema.sql"

with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.load(f, Loader=yaml.SafeLoader)

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
        CONFIG["api"]["version"] = data["project"]["version"]


class ConfigChangeHandler(FileSystemEventHandler):
    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        super().on_modified(event)
        global CONFIG
        with open(CONFIG_PATH, "r") as f:
            CONFIG = yaml.load(f, Loader=yaml.SafeLoader)


observer = Observer()
observer.schedule(ConfigChangeHandler(), CONFIG_PATH, recursive=False)
observer.start()
