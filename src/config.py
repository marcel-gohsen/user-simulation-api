import tomllib

import yaml
from watchdog.events import FileSystemEventHandler, DirModifiedEvent, FileModifiedEvent
from watchdog.observers import Observer

CONFIG_PATH = "config/api-conf.yml"

DATABASE_DIR = "database"
SCHEMA_PATH = "data/db-schema.sql"

with open(CONFIG_PATH, "r", encoding="utf-8") as project_file:
    CONFIG = yaml.load(project_file, Loader=yaml.SafeLoader)

    with open("pyproject.toml", "rb") as project_file:
        data = tomllib.load(project_file)
        CONFIG["api"]["version"] = data["project"]["version"]


class ConfigChangeHandler(FileSystemEventHandler):
    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        super().on_modified(event)
        global CONFIG
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            CONFIG = yaml.load(config_file, Loader=yaml.SafeLoader)


observer = Observer()
observer.schedule(ConfigChangeHandler(), CONFIG_PATH, recursive=False)
observer.start()
