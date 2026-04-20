"""
Main module to execute Sim.API.
"""

import logging
import os.path
import sqlite3

import click
import uvicorn
from fastapi import FastAPI
from starlette.responses import RedirectResponse

from api import auth_router, budget_router, run_router
from config import CONFIG, DATABASE_DIR, SCHEMA_PATH
from shared_task.shared_task import SharedTaskManager
from security.authenticator import Authenticator


def setup_app() -> FastAPI:
    """
    Configure FastAPI app routes.

    :return: FastAPI app.
    """
    app = FastAPI(
        version=CONFIG["api"]["version"],
        title=CONFIG["api"]["title"],
        description=CONFIG["api"]["description"],
        root_path=CONFIG["api"]["root_path"],
        contact=CONFIG["api"]["contact"],
    )
    app.include_router(auth_router.router)
    app.include_router(run_router.debug_router)
    app.include_router(run_router.run_router)
    app.include_router(budget_router.router)

    @app.get("/", include_in_schema=False, response_class=RedirectResponse)
    def root():
        return RedirectResponse(url=os.path.join(CONFIG["api"]["root_path"], "docs"))

    return app


def setup_storage(shared_task: str):
    """
    Configure internal Sqlite3 database storage for given shared task.

    :param shared_task: Name of the configured shared task.
    :return: None
    """
    os.makedirs(DATABASE_DIR, exist_ok=True)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as in_file:
        db_path = os.path.join(DATABASE_DIR, f"{shared_task}.db")
        with sqlite3.connect(db_path) as conn:
            _ = conn.executescript(in_file.read())
            conn.commit()


@click.command()
@click.option(
    "--admin-name",
    type=str,
    default=None,
    required=False,
    help="Set a username of the admin account.",
)
@click.option(
    "--admin-password",
    type=str,
    default=None,
    required=False,
    help="Set a password of the admin account.",
)
@click.option(
    "--shared-task",
    type=click.Choice(SharedTaskManager().shared_tasks.keys()),
    default="dummy",
    required=True,
    help="Select one of the preconfigured shared tasks.",
)
def main(admin_name: str, admin_password: str, shared_task: str):
    """
    Main function to set up and execute Sim.API.

    :param admin_name: Username for the admin account.
    :param admin_password: Password for the admin account.
    :param shared_task: Name of the configured shared task.
    :return: None
    """
    format_string = "%(asctime)s - %(name)-20s - %(levelname)-7s - %(message)s"
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = format_string
    log_config["formatters"]["default"]["fmt"] = format_string

    logging.basicConfig(level=logging.DEBUG, format=format_string)
    logger = logging.getLogger("main")

    if admin_name == "":
        admin_name = None
    if admin_password == "":
        admin_password = None

    setup_storage(shared_task)
    task_manager = SharedTaskManager()
    task_manager.set_active_task(shared_task)
    task_manager.active_task.initialize()

    if admin_name is not None and admin_password is not None:
        authenticator = Authenticator()
        authenticator.add_admin(admin_name, admin_password)
        logger.info("Added admin credentials")
    else:
        logger.warning("No admin credentials provided")

    app = setup_app()
    try:
        uvicorn.run(
            app, host="0.0.0.0", port=8888, log_config=log_config, log_level="debug"
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
