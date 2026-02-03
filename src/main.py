import logging
import os.path
import sqlite3

import click
import uvicorn
from fastapi import FastAPI
from starlette.responses import RedirectResponse

from api import auth_router, budget_router, run_router
from config import CONFIG, DATABASE_PATH, SCHEMA_PATH


def setup_app() -> FastAPI:
    app = FastAPI(
        version=CONFIG["api"]["version"],
        title=CONFIG["api"]["title"],
        description=CONFIG["api"]["description"],
        root_path=CONFIG["api"]["root_path"],
        contact=CONFIG["api"]["contact"],)
    app.include_router(auth_router.router)
    app.include_router(run_router.debug_router)
    app.include_router(run_router.run_router)
    app.include_router(budget_router.router)

    @app.get("/", include_in_schema=False, response_class=RedirectResponse)
    def root():
        return RedirectResponse(url=os.path.join(CONFIG["api"]["root_path"],"docs"))

    return app

@click.command()
@click.option("--admin-name", type=str, default=None, required=False)
@click.option("--admin-password", type=str, default=None, required=False)
def main(admin_name: str, admin_password: str):
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

    # ensure our database schema is created here
    if not os.path.exists(DATABASE_PATH):
        os.makedirs(os.path.dirname(DATABASE_PATH))
        with open(SCHEMA_PATH, "r") as in_file:
            with sqlite3.connect(DATABASE_PATH) as conn:
                _ = conn.executescript(in_file.read())
                conn.commit()

    if admin_name is not None and admin_password is not None:
        from security.authenticator import Authenticator
        authenticator = Authenticator()
        authenticator.add_admin(admin_name, admin_password)
        logger.info("Added admin credentials")
    else:
        logger.warning("No admin credentials provided")


    app = setup_app()
    try:
        uvicorn.run(app, host="0.0.0.0", port=8888, log_config=log_config, log_level="debug")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
