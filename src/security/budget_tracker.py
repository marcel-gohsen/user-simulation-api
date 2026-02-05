import os
import sqlite3

from fastapi import HTTPException
from starlette import status
from typing_extensions import Literal

from config import DATABASE_DIR
from shared_task.shared_task import SharedTaskManager
from shared_task.trec_run import RunManager


class BudgetTracker:

    def __init__(self):
        db_path = os.path.join(DATABASE_DIR, f"{SharedTaskManager().active_task.name}.db")
        self.db_connection = sqlite3.connect(db_path, check_same_thread=False)


    def get_number_of_sessions(self, team_id: str, api: Literal["debug", "run"]):
        cursor = self.db_connection.execute(
            "SELECT COUNT(DISTINCT session_id) FROM requests WHERE requests.team_id=? AND api=? AND requests.count_towards_credits=true;",
            (team_id, api)
        )
        return cursor.fetchone()[0]

    def reset_credits(self, team_id: str, api: Literal["debug", "run"]):
        _ = self.db_connection.execute(
            """
            UPDATE requests 
            SET count_towards_credits = false 
            WHERE api=? 
                AND 
                EXISTS(
                    SELECT * 
                    FROM runs 
                    WHERE runs.id = requests.run_id 
                        AND runs.team_id=?
                );""",
            (api, team_id),
        )
        self.db_connection.commit()


def check_budget(run_manager: RunManager, team_id: str, api: Literal["debug", "run"], limit: int, unit: Literal["sessions", "runs"] = "sessions"):
    if unit == "sessions":
        budget_tracker = BudgetTracker()
        number_of_requests = budget_tracker.get_number_of_sessions(team_id, api)

        if number_of_requests >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You exceeded the maximum number of requests you can submit.",
            )

        return max(0, limit - number_of_requests)
    elif unit == "runs":
        run_ids = run_manager.get_runs(team_id)

        num_runs = len(run_ids)
        completed_runs = 0
        for run_id in run_ids:
             run_status = run_manager.get_status(run_id)

             if run_status["status"] == "complete":
                 completed_runs += 1

        if num_runs >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You exceeded the maximum number of runs you can submit.",
            )

        return max(0, limit - num_runs)

    return None


