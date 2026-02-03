import copy
import json
import sqlite3
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, Optional, OrderedDict, Any, List

from api.messages import RunMeta
from config import TOPICS, DATABASE_PATH
from data.sessions import Session
from data.topic import Topic


@dataclass
class TRECRun:
    run_meta: RunMeta

    # topic_id -> session
    sessions: Dict[str, Session] = field(default_factory=dict)
    _open_topics: OrderedDict[str, Topic] = field(default_factory=lambda: copy.deepcopy(TOPICS))

    def next_topic(self) -> Topic:
        return self._open_topics.popitem(last=False)[1]

    def has_next_topic(self) -> bool:
        return len(self._open_topics) > 0

    def get_progress(self):
        done_topics = [t._id for t in TOPICS.values() if t._id not in self._open_topics]
        return {"done_topics": done_topics,
                "open_topics": [t._id for t in self._open_topics.values()]}


class RunManager(object):
    _instance = None
    _debug_instance = None
    _lock = RLock()

    def __new__(cls, debug: bool = False, *args, **kwargs):
        with RunManager._lock:
            if debug:
                if cls._debug_instance is None:
                    cls._debug_instance = super(RunManager, cls).__new__(cls, *args, **kwargs)
                    cls._debug_instance.runs = {}
                    cls._debug_instance.db_connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                instance = cls._debug_instance
            else:
                if cls._instance is None:
                    cls._instance = super(RunManager, cls).__new__(cls, *args, **kwargs)
                    cls._instance.runs = {}
                    cls._instance.db_connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                instance = cls._instance

            return instance

    def get_active_run(self, run_id: str) -> TRECRun | None:
        with RunManager._lock:
            return self.runs.get(run_id, None)

    def get_runs(self, team_id: str) -> List[str]:
        with RunManager._lock:
            cursor = self.db_connection.execute(f"SELECT id FROM runs WHERE team_id=?;", (team_id,))
            run_ids = cursor.fetchall()
        run_ids = [r[0] for r in run_ids]
        return run_ids

    def get_status(self, run_id: str) -> Dict[str, Any]:
        active_run = self.get_active_run(run_id)
        progress = {}
        if active_run is None:
            progress["status"] = "inactive"
            with RunManager._lock:
                cursor = self.db_connection.execute(f"SELECT DISTINCT topic_id FROM requests WHERE run_id=? AND api='run'", (run_id,))
                topic_ids = [t[0] for t in cursor.fetchall()]
            progress["done_topics"] = topic_ids
            progress["open_topics"] = [t._id for t in TOPICS.values() if t._id not in topic_ids]
        else:
            progress["status"] = "active"
            progress = {**progress, **active_run.get_progress()}

        if len(progress["open_topics"]) == 0:
            progress["status"] = "complete"

        return progress

    def run_exists(self, run_id: str, team_id: str = None) -> bool:
        active_run = self.get_active_run(run_id)
        with RunManager._lock:
            cursor = self.db_connection.cursor()
            if team_id is None:
                cursor.execute(
                    "SELECT * FROM runs WHERE id=? AND "
                    "EXISTS(SELECT * FROM requests WHERE requests.run_id = runs.id AND requests.api = 'run')", (run_id,))
            else:
                cursor.execute(
                    "SELECT * FROM runs WHERE id=? AND runs.team_id=? AND "
                    "EXISTS(SELECT * FROM requests WHERE requests.run_id = runs.id AND requests.api = 'run')", (run_id,team_id))
            res = cursor.fetchone()
        return res is not None or active_run is not None

    def create_run(self, run_meta: RunMeta) -> TRECRun:
        run = TRECRun(run_meta)
        with RunManager._lock:
            self.runs[run_meta.run_id] = run

        if self is self._instance:
            with RunManager._lock:
                _ = self.db_connection.execute(
                    "INSERT INTO runs VALUES (?,?,?,?);",
                    (run.run_meta.run_id, run.run_meta.team_id, run.run_meta.description, run.run_meta.track_persona)
                )
                self.db_connection.commit()
        return run

    def recover_run(self, run_id: str) -> TRECRun:
        run = self.get_active_run(run_id)
        if run is not None:
            return run

        with RunManager._lock:
            cursor = self.db_connection.execute(f"SELECT DISTINCT topic_id FROM requests WHERE run_id=? AND api='run'", (run_id,))
            topic_ids = cursor.fetchall()[0]
            cursor.execute(f"SELECT * FROM runs WHERE id=?;", (run_id,))
            res = cursor.fetchone()

        run = TRECRun(RunMeta(res[0], res[2], res[3], res[1]))
        while True:
            topic = run._open_topics.popitem(last=False)
            if topic[0] not in topic_ids:
                run._open_topics.update({topic[0]: topic[1]})
                run._open_topics.move_to_end(topic[0], last=False)
                break

        with RunManager._lock:
            self.runs[run_id] = run
        return run

    def dump(self, run_id: str) -> Optional[List[Dict[str, Any]]]:
        with RunManager._lock:
            cursor = self.db_connection.execute(
                "SELECT runs.team_id, runs.description, runs.track_persona, requests.topic_id, requests.user_utterance,requests.response, requests.citations, requests.ptkbs, requests.rubrik, requests.rubrik_score  FROM runs JOIN requests ON runs.id = requests.run_id WHERE runs.id=? AND requests.api='run' ORDER BY requests.timestamp;", (run_id,))

            requests = cursor.fetchall()

        if len(requests) == 0:
            return None

        metadata = {
            "team_id": requests[0][0],
            "run_id": run_id,
            "type": "interactive",
            "description": requests[0][1],
            "track_persona": requests[0][2],
        }


        responses_per_topic = {}
        for req in requests:
            if req[3] not in responses_per_topic:
                responses_per_topic[req[3]] = []

            responses_per_topic[req[3]].append(req)

        data = []
        for topic_id, responses in responses_per_topic.items():
            for i, response in enumerate(responses):
                data.append({
                    "metadata": {**metadata, "topic_id": f"{topic_id}_{i + 1}"},
                    "responses": [
                        {
                            "rank": 1,
                            "user_utterance": response[4],
                            "user_rubrik": response[8],
                            "user_rubrik_score": response[9],
                            "text": response[5],
                            "citations": json.loads(response[6]),
                            "ptkb_provenance": json.loads(response[7]),
                        }
                    ],
                    "references": json.loads(response[6])
                })

        return data



