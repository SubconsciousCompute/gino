from datetime import datetime, timezone, timedelta
from pathlib import Path

import typing as T
import json
import logging

import gitlab
import typer
from urlextract import URLExtract

import cmo.notion
from cmo.common import parse_date, load_config, get_config, shelve_it
from cmo.common import WAITING_FOR_TRIAGE, LINKED_WITH_NOTION, CLOSED_IN_NOTION

app = typer.Typer()

GL = None


def get_gitlab_client():
    global GL
    if GL is not None:
        return GL
    load_config()
    GL = gitlab.Gitlab(
        get_config("GITLAB_URL"), private_token=get_config("GL_GROUP_TOKEN")
    )
    GL.auth()
    return GL


def _issue_to_notion_title(project_name, issue):
    return f"#{issue.iid}:{project_name} - {issue.title}"


def is_linked_with_notion(issue):
    if LINKED_WITH_NOTION in issue.labels or "linked-with-notion" in issue.labels:
        return True
    return False


def sync_recently_closed_issues(project):
    updated_after = datetime.now(timezone.utc) - timedelta(minutes=600)
    nissues = 0
    for issue in project.issues.list(
        state="closed",
        updated_after=updated_after,
        iterator=True,
    ):
        nissues += 1
        logging.info(f" Issue '{issue.title}' was closed recently. Updating notion..")
        change_notion_task_status(issue)
    if nissues > 0:
        logging.info(f"Total {nissues} recently closed issues were synced.")


def link_newly_created_issues_with_notion(project, created_before_mins: int = 720):
    created_after = datetime.now(timezone.utc) - timedelta(minutes=created_before_mins)
    nissues = 0
    for issue in project.issues.list(
        state="opened",
        created_after=created_after,
        iterator=True,
    ):
        nissues += 1
        logging.info(f" Issue '{issue.title}' was created recently...")
        url = issue.web_url
        label = LINKED_WITH_NOTION
        page_title = _issue_to_notion_title(project.name, issue)
        if is_linked_with_notion(issue):
            logging.info("> This issue is already linked with notion")
            continue

        logging.info(f"  Linking issue {issue.title} with notion")
        author = issue.author["username"]
        page_date = str(issue.due_date) if issue.due_date else None
        assignee = issue.assignees[0]["username"] if issue.assignees else None
        if page := cmo.notion.create_task(
            page_title,
            url,
            due_date=page_date,
            assignee=assignee,
            author=author,
            gitlab_data=issue,
        ):
            # adds tag to issue that I have created the issue on the notion
            text = f"""{issue.description}. By {issue.author}."""
            cmo.notion.append_to_page(page["id"], text)
            issue.labels = issue.labels + [label]
            issue.notes.create(
                dict(body="More information may be found at " + page["url"])
            )
            issue.save()

    logging.info(f"Total {nissues} processed.")


def get_issue_by_url(url):
    """Return an issue for a given URL. Throw exceptions if anything goes wrong.
    Use with care.
    """
    client = get_gitlab_client()
    fs = url.split("/")
    issue_iid = int(fs[-1])
    pname = "/".join(fs[-5:-3])
    project = client.projects.get(pname)
    return project.issues.get(issue_iid)


def sync_notes(project):
    updated_before = datetime.now(timezone.utc) - timedelta(minutes=10)
    for issue in project.issues.list(
        state="opened",
        updated_before=updated_before,
        iterator=True,
    ):
        if "stale" in issue.labels:
            continue

        if not is_linked_with_notion(issue):
            continue

        notion_page_uuid = find_notion_page_uuid(issue)
        logging.info(f"Adding notes from {issue.title}")
        for note in issue.notes.list(updated_before=updated_before):
            if note.author["username"] == "cmo-bot":
                continue
            body = note.body
            if body.endswith(LINKED_WITH_NOTION):
                print("This issue is already linked with notion")
                continue

            try:
                text = f"{body}. By {note.author['username']}. On {note.created_at}."
                cmo.notion.append_to_page(notion_page_uuid, text)
                note.body += f"\n\n{LINKED_WITH_NOTION}"
                note.save()
            except Exception as e:
                logging.warning(f"Failed: {e}")


def mark_issues_stale(project):
    """Mark an issue stale if no activity on it for 4 weeks."""
    updated_before = datetime.now(timezone.utc) - timedelta(days=28)
    stale = "stale"
    for issue in project.issues.list(
        state="opened",
        order_by="created_at",
        updated_before=updated_before,
        sort="desc",
        iterator=True,
    ):
        logging.info(f" Open issue {issue.title}")
        if stale in issue.labels:
            logging.info("   already marked stale.")
            continue
        try:
            issue.labels += [stale]
            issue.save()
            logging.info(f"Successfully marked issue {issue.id} 'stale'")
        except Exception as e:
            logging.error(f"Failed to mark issue {issue.id} as stale. Error {e}")


def change_notion_task_status(issue):
    if CLOSED_IN_NOTION in issue.labels:
        logging.info("> This issue is already closed in notion.")
        return
    if not is_linked_with_notion(issue):
        logging.warning("> This issue was not found in notion")
        return 

    notion_status = gl_issue_status_to_notion_task_status(issue)
    notion_page_uuid = find_notion_page_uuid(issue)
    if notion_page_uuid:
        logging.info(f">Updating {notion_page_uuid} status to {notion_status}")
        cmo.notion.change_page_status(notion_page_uuid, notion_status)
        issue.notes.create(dict(body="Changed status of linked notion page"))
        issue.labels += [CLOSED_IN_NOTION]
        issue.save()
    else:
        logging.warn("> Could not found notion page!") 


def close_issues_due_to_inactivity(project):
    """Close issue if there is no activity on it for 6 months"""
    updated_before = datetime.now(timezone.utc) - timedelta(days=180)
    label = "closed-due-to-inactivity"
    for issue in project.issues.list(
        state="opened",
        order_by="created_at",
        updated_before=updated_before,
        sort="desc",
        iterator=True,
    ):
        if label in issue.labels:
            logging.info("Already closed")
            continue

        try:
            issue.labels += [label]
            issue.state_event = "close"
            issue.save()
            logging.info(f"Successfully closed issue {issue.id}/{issue.title}")
            change_notion_task_status(issue)
        except Exception as e:
            logging.error(f"Failed to close {issue.title}. Error {e}")


# FIXME: Email are returned only if admin queries the endpoint.
# See https://docs.gitlab.com/ee/api/users.html
def _find_gitlab_user_email(user: str):
    gl = get_gitlab_client()
    return gl.users.list(username=user)[0]


def get_project(name_or_id):
    gitlab = get_gitlab_client()
    project = None
    try:
        project = gitlab.projects.get(int(name_or_id))
    except Exception:
        project = gitlab.projects.list(search=name_or_id, get_all=True)[-1]
    return project


def compute_issue_task_maturity_metric(issue) -> dict:
    created_at = parse_date(issue.created_at)
    due_date = parse_date(issue.due_date)
    closed_at = parse_date(issue.closed_at)
    metric = dict()
    metric["created_at"] = issue.created_at
    metric["days_punctuality"] = (due_date - closed_at).days if due_date else None
    metric["days_spent"] = (closed_at - created_at).days
    return metric


@shelve_it("project_maturity.shelve")
def compute_project_task_maturity_metric(project_id, project):
    result = {}
    for issue in project.issues.list(state="closed", iterator=True):
        issue_id = issue.iid
        try:
            metric = compute_issue_task_maturity_metric(issue)
            result[issue_id] = metric
        except Exception as e:
            print(f"Failed to get metric: {e}")
            result[issue_id] = None
    return result


def plot_punctuality(result):
    for project, data in result.items():
        print(project, data)


def _get_projects(project_name_or_id: T.Optional[str] = None):
    if not project_name_or_id:
        projects = get_gitlab_client().projects.list(iterator=True)
    else:
        projects = [get_project(project_name_or_id)]
    return projects


@app.command("task-maturity")
def compute_task_maturity_metric(project_name_or_id: T.Optional[str] = None):
    result = {}
    for project in _get_projects(project_name_or_id):
        logging.info(f"=> Analysing '{project.name}'...")
        metric = compute_project_task_maturity_metric(project.name, project)
        result[project.name] = metric

    # save the data for ploting.
    outfile = Path() / "punctuality.json"
    with outfile.open("w") as f:
        json.dump(result, f)


@app.command("plot-task-maturity")
def plot_task_maturity(days_in_past: T.Optional[int] = None):
    import matplotlib.pyplot as plt

    plt.style.use("ggplot")
    plt.figure(figsize=(8, 5))

    datafile = Path() / "punctuality.json"
    data = json.loads(datafile.read_text())

    title = "All data"
    if days_in_past is not None:
        title = f"Data (last {days_in_past} days)"

    maturity_box, days_to_close = [], []
    n_issues_without_due_date = 0
    now = datetime.now()
    for project, project_data in data.items():
        for issue, issue_data in project_data.items():
            if issue_data is None:
                logging.warning("Empty issue data")
                continue
            if days_in_past is not None:
                print(issue_data)
                if (now - parse_date(issue_data["created_at"])).days > days_in_past:
                    continue
            if not issue_data:
                logging.warning("Empty issue_data")
                continue
            assert issue_data["days_spent"] is not None, issue_data
            days_to_close.append(issue_data["days_spent"])
            if (m := issue_data["days_punctuality"]) is not None:
                maturity_box.append(m)
            else:
                n_issues_without_due_date += 1

    ax1 = plt.subplot(221)
    print(f"Plotting {maturity_box}")
    ax1.hist(maturity_box, bins=10)
    ax1.set_title("Punctuality")
    ax1.set_xlabel("#days")

    ax2 = plt.subplot(222)
    ax2.hist(days_to_close, bins=10)
    ax2.set_title("Days to close")
    ax2.set_xlabel("#days")

    ax3 = plt.subplot(223)
    ax3.boxplot(maturity_box)

    ax4 = plt.subplot(224)
    ax4.boxplot(days_to_close)

    plt.suptitle(title)
    plt.tight_layout()
    plt.savefig(datafile.with_suffix(".png"))
    plt.close()


@app.command()
def no_due_date(project_name_or_id: str, state: str = "opened"):
    """TODO"""
    project = get_project(project_name_or_id)
    for issue in project.issues.list(state=state, iterator=True):
        author = issue.author["username"]
        author_email = _find_gitlab_user_email(author)
        print(author, author_email, issue)


def find_notion_page_uuid(issue) -> T.Optional[str]:
    # find the note that says more information can be found.
    extractor = URLExtract()
    for note in issue.notes.list(iterator=True):
        urls = extractor.find_urls(note.body)
        if len(urls) > 0:
            page_uuid = urls[0][-32:]
            return page_uuid
    return None


def gl_issue_status_to_notion_task_status(issue: str) -> str:
    notion_status = "Todo"
    if issue.state == "closed":
        notion_status = "Done"
    elif issue.state == "opened":
        notion_status = "Not Started"
    else:
        pass
    if WAITING_FOR_TRIAGE in issue.labels:
        notion_status = "Todo"
    return notion_status


@app.command()
def issues(project_name_or_id: str, state: str = "opened"):
    """TODO"""
    project = get_project(project_name_or_id)
    for issue in project.issues.list(state=state, iterator=True):
        author = issue.author["username"]
        author_email = _find_gitlab_user_email(author)
        print(author, author_email, issue.title)


if __name__ == "__main__":
    app()
