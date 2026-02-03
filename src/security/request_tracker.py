import datetime
import json
import sqlite3
from typing import Literal, Optional

from config import DATABASE_PATH


class RequestTracker:

    def __init__(self):
        self.db_connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)


    def register_request(self, run_id: str, team_id: str, session_id: str, topic_id: str, user_id: str,
                         api: Literal["debug", "run"], user_utterance: str, response: str | None,
                         citations: dict[str, float], ptkbs: list[str], rubrik: Optional[str], rubrik_score: Optional[int]) -> None:
        timestamp = datetime.datetime.now().isoformat()

        _ = self.db_connection.execute(
            """
            INSERT INTO requests(
                timestamp, run_id, team_id, session_id, topic_id, user_id,
                api, user_utterance, response, citations, ptkbs, rubrik, rubrik_score)
            VALUES 
                (?,?,?,?,?,?,?,?,?,?,?,?,?);
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
                response,
                json.dumps(citations),
                json.dumps(ptkbs),
                rubrik,
                rubrik_score
            ),
        )
        self.db_connection.commit()
