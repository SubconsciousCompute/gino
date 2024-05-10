"""GiNo cli interface"""

import time
import sentry_sdk
import datetime

import gino.gitlab
import gino.notion

from gino.common import logger

import typer

app = typer.Typer()
app.add_typer(gino.gitlab.app, name="gitlab")
app.add_typer(gino.notion.app, name="notion")


def read_projects():
    # Loading the environment variables
    gl = gino.gitlab.get_gitlab_client()
    return gl.projects.list(
        iterator=True, archived=False, order_by="last_activity_at", sort="desc"
    )


@app.command("sync-new")
def sync_newly_created_issues_with_notion(project):
    if isinstance(project, str):
        project = gino.gitlab.get_project(project)
    logger.debug(f"Syncing new issues with notion {project.name_with_namespace}")
    gino.gitlab.link_newly_created_issues_with_notion(project)


@app.command("sync-closed")
def sync_recently_closed_issues(project):
    if isinstance(project, str):
        project = gino.gitlab.get_project(project)
    logger.debug(
        f"Syncing recently closed issue with notion {project.name_with_namespace}"
    )
    gino.gitlab.sync_recently_closed_issues(project)


@app.command("sync-notes")
def sync_notes(project):
    if isinstance(project, str):
        project = gino.gitlab.get_project(project)
    logger.debug(f"Syncing new notes with notion {project.name_with_namespace}")
    gino.gitlab.sync_notes(project)


def mark_stale(project):
    logger.debug(f"Marking old issues stale {project.name_with_namespace}")
    gino.gitlab.mark_issues_stale(project)


def close_issues(project):
    logger.debug(
        f"Closing very old issues due to inactivity: {project.name_with_namespace}"
    )
    gino.gitlab.close_issues_due_to_inactivity(project)


def office_hours():
    d = datetime.datetime.now()
    return (d.hour > 8) and (d.hour < 18)


@app.command()
def run_once():
    try:
        gino.notion.sync_recently_added_blocks()
    except Exception as e:
        logger.warning(e)
    for project in read_projects():
        logger.info(f"Analysing project {project.name_with_namespace}")
        try:
            sync_newly_created_issues_with_notion(project)
        except Exception as e:
            logger.warning(e)
        try:
            sync_recently_closed_issues(project)
        except Exception as e:
            logger.warning(e)
        try:
            mark_stale(project)
        except Exception as e:
            logger.warning(e)
        try:
            close_issues(project)
        except Exception as e:
            logger.warning(e)


@app.command()
def run():
    interval = gino.common.INTER_RUN_INTERVAL_SEC
    while True:
        t0 = time.time()
        try:
            run_once()
            t = time.time() - t0
            tosleep = max(60, interval - t)
            print(f"Sleeping for {tosleep} secs")
            time.sleep(tosleep)
        except Exception as e:
            logger.warning(f"Failed step: {e}")
            time.sleep(30)


if __name__ == "__main__":
    app()
