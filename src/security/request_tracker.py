import datetime
import json
import os
import sqlite3
from typing import Literal, Optional, Dict, Any

from config import DATABASE_DIR
from shared_task.shared_task import SharedTaskManager


class RequestTracker:

    def __init__(self):
        db_path = os.path.join(
            DATABASE_DIR, f"{SharedTaskManager().active_task.name}.db"
        )
        self.db_connection = sqlite3.connect(db_path, check_same_thread=False)

    def register_request(
        self,
        run_id: str,
        team_id: str,
        session_id: str,
        topic_id: str,
        user_id: str,
        api: Literal["debug", "run"],
        user_utterance: str,
        response: str | None,
        citations: dict[str, float],
        user_meta: Dict[str, Any],
        assistant_meta: Dict[str, Any],
    ) -> None:
        timestamp = datetime.datetime.now().isoformat()

        _ = self.db_connection.execute(
            """
            INSERT INTO requests(
                timestamp, run_id, team_id, session_id, topic_id, user_id,
                api, user_utterance, user_meta, assistant_response, assistant_meta, assistant_citations)
            VALUES 
                (?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                timestamp,
                run_id,
                team_id,
                session_id,
                topic_id,
                user_id,
                api,
                user_utterance,
                json.dumps(user_meta),
                response,
                json.dumps(assistant_meta),
                json.dumps(citations),
            ),
        )
        self.db_connection.commit()
