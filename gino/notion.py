import os
import difflib
import uuid
import typing as T
import pprint
import logging

from datetime import timedelta

import dateparser
from validators import email
from validators.uuid import uuid as is_uuid

from notion_client import Client

import gino.common

import typer

app = typer.Typer()

# Notion client.
# https://github.com/ramnes/notion-sdk-py
NOTION = None

NOTION_SECURITY_METRICS_DB: T.Final[str] = "fc79dbd028694a32a1f162eae3bcdb01"


def _pp(x):
    pprint.pprint(x)


def client():
    global NOTION
    if NOTION is not None:
        return NOTION
    gino.common.load_config()
    api_key = os.environ["NOTION_ACCESS_TOKEN"]
    NOTION = Client(auth=api_key)
    return NOTION


def db_id():
    return os.environ["TASK_DATABASE_ID"]


def _create_block(text, color="red"):
    return dict(
        object="block",
        type="paragraph",
        paragraph=dict(
            rich_text=dict(type="text", text=dict(content=text)),
            annotation=dict(color=color),
        ),
    )


def get_page(_uuid):
    try:
        uid = str(uuid.UUID(_uuid))
    except Exception as e:
        logging.warning(f"Failed to convert uuid {_uuid} to UUID. Error {e}.")
        return None

    if not is_uuid(uid):
        logging.warning(f"Not a valid uuid: {uid}.")
        return None
    notion = client()
    logging.info(f"Finding page with uuid={uid}")
    return notion.pages.retrieve(uid)


def change_page_status(page_uuid, status: str):
    """Change the status of the page"""
    notion = client()
    _uuid = str(uuid.UUID(page_uuid))
    assert is_uuid(_uuid), f"{_uuid} is not UUID."
    notion.pages.update(_uuid, properties=dict(Status=dict(status=dict(name=status))))
    logging.info(f"Successfully updated status of `{_uuid}` to {status}")


def append_to_page(page_uuid, text):
    notion = client()
    _uuid = str(uuid.UUID(page_uuid))
    assert is_uuid(_uuid), f"{_uuid} is not UUID."
    children = [dict(paragraph=dict(rich_text=[dict(text=dict(content=text))]))]
    notion.blocks.children.append(block_id=_uuid, children=children)
    logging.info(f"Successfully appended to page `{_uuid}`")


@app.command()
def create_task(
    title: str,
    url: str,
    *,
    due_date: T.Optional[str] = None,
    assignee: T.Optional[str] = None,
    author: T.Optional[str] = None,
    gitlab_data=None,
):
    shelve_key = f"{url}-{title}"
    if gino.common.load(shelve_key) is not None:
        logging.debug("Page already exists in notion. Doing nothing")
        return

    tags = [{"name": "FromGITLAB"}]
    if gitlab_data.labels:
        tags += [{"name": value} for value in gitlab_data.labels]

    params = {
        "Task name": {"type": "title", "title": [{"text": {"content": title}}]},
        "Tags": {"multi_select": tags},
        "URL": {"url": url},
    }
    if due_date:
        dd = dateparser.parse(due_date).strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"
        logging.info(f"> due date {dd}")
        params["Due"] = {"date": {"start": dd}}

    if assignee:
        params["Assign"] = {"people": [{"id": _find_notion_uuid(assignee)}]}

    if author:
        params["Stakeholders"] = {"people": [{"id": _find_notion_uuid(author)}]}

    ## FIXME: appending blocks doesn't work
    ## page = []
    ## page.append(
    ##     _create_block(
    ##         f"""This page is automatically created by CMO.\
    ##         It is best if you upadte the issues at {url}.\n\n"""
    ##     ),
    ## )
    ## page.append(_create_block(gitlab_data.description))
    ## params["children"] = [page]
    ## pprint.pprint(params)
    page = client().pages.create(parent={"database_id": db_id()}, properties=params)

    # if page is created successful, write to the global keyval store.
    gino.common.store(shelve_key, 1)

    return page


def _find_notion_uuid(gitlab_user_or_email_or_uuid: str):
    if is_uuid(gitlab_user_or_email_or_uuid):
        return gitlab_user_or_email_or_uuid
    if email(gitlab_user_or_email_or_uuid):
        user = _find_user_by_email(gitlab_user_or_email_or_uuid)
        if user:
            return user["id"]
    user = _find_user_by_gitlab_user(gitlab_user_or_email_or_uuid)
    if user:
        return user["id"]
    assert False, f"Failed to find uuid for {gitlab_user_or_email_or_uuid}"


# cache but only for 10 minutes.
def _find_user_by_email(email: str) -> T.Optional[dict]:
    """Find user in notion with given email"""
    assert email(email), "Expected an email"
    notion = client()
    users = notion.users.list()

    result = None
    for user in users["results"]:
        if user["person"]["email"] == email:
            result = user
            break
    return result


# cache but only for 10 minutes.
def _find_user_by_gitlab_user(gitlab_username: str) -> T.Optional[dict]:
    """Find user in notion with given email"""
    gitlab_username = gitlab_username.lower()

    notion = client()
    users = notion.users.list()
    for user in users["results"]:
        if "name" not in user:
            continue
        name = user["name"].lower()
        if difflib.SequenceMatcher(None, name, gitlab_username).ratio() > 0.9:
            return user
        if gitlab_username in name:
            return user


@app.command()
def find_user(email_or_gitlab_username: str) -> T.Optional[dict]:
    """Find user in notion with given email"""
    if email(email_or_gitlab_username):
        user = _find_user_by_email(email_or_gitlab_username)
    else:
        user = _find_user_by_gitlab_user(email_or_gitlab_username)
    print(f"{user}")
    return user


@app.command()
def search(query: str, page_size: int = 1) -> T.Optional[dict]:
    """Find user in notion with given email"""
    notion = client()
    data = dict(query=query, page_size=page_size)
    results = notion.search(**data).get("results")
    return results


def blocks_to_markdown(blocks) -> str:
    from notion2markdown import json2md

    json2md = json2md.JsonToMd()
    return json2md.jsons2md(blocks)


@app.command("sync-blocks")
def sync_recently_added_blocks():
    """find pages that were modified in last INTER_RUN_INTERVAL_SEC"""
    mmin = gino.common.INTER_RUN_INTERVAL_SEC
    notion = client()
    edited_after = gino.common.now_utc() - timedelta(minutes=mmin)
    data = dict(
        filter=dict(
            property="Last edited time", date=dict(after=edited_after.isoformat())
        )
    )
    for item in notion.databases.query(db_id(), **data).get("results"):
        sync_recently_added_blocks_page(item["id"], item)


def sync_recently_added_blocks_page(page_uuid, page=None):
    """Sync recently added blocks with gitlab. There is no state keeping here.
    I.e., we can't figure out which blocks were added to gitlab. We make sure
    that we only process the blocks that were added within the
    INTER_RUN_INTERVAL_SEC.
    """
    mmin = gino.common.INTER_RUN_INTERVAL_SEC / 60
    _uuid = str(uuid.UUID(page_uuid))
    notion = client()
    blocks = []
    markdown = ""
    for block in notion.blocks.children.list(_uuid).get("results"):
        mins_from_now = gino.common.from_now_mins(block["created_time"])
        if mins_from_now < mmin:
            if ":from-gitlab:" in str(block):
                continue
            blocks.append(block)

    page = get_page(_uuid) if page is None else page
    page_url = page["url"]
    issue_url = page["properties"].get("URL", {}).get("url")
    markdown = blocks_to_markdown(blocks)
    if len(markdown.strip()) > 3:
        try:
            issue = gino.gitlab.get_issue_by_url(issue_url)
            issue.notes.create(dict(body=f"_from:notion_: <{page_url}>" + markdown))
        except Exception as e:
            logging.debug(e)


def sync_metrics(metrics):
    print(f"Syncing metrics {metrics}")
    notion = client()
    # create a code -> human_readable dict
    metrics_dict = dict(metrics)

    db_id = os.environ["NOTION_SECURITY_METRICS_DB"]
    for item in notion.databases.query(db_id).get("results"):
        _uuid = str(uuid.UUID(item["id"]))
        prop = item["properties"]
        try:
            long_name = prop["LongName"]["title"][0]["text"]["content"]
            unique_id = prop["UniqueId"]["rich_text"][0]["plain_text"]
            # check if unique_id is in metric server
            if (long_name_1 := metrics_dict.get(unique_id)) is not None:
                logging.debug(_uuid, unique_id, long_name, long_name_1)
                if long_name_1 != long_name:
                    # update the value in notion.
                    logging.info(f"Changing long name {long_name} to {long_name_1}")
                    notion.pages.update(
                        _uuid,
                        properties=dict(
                            LongName=dict(title=[dict(text=dict(content=long_name_1))])
                        ),
                    )
                del metrics_dict[unique_id]
        except Exception:
            pass

    # check if there are some metrics in metrics_dict that are not yet in
    # notion.
    logging.info(f"These metrics are not in notion yet: {metrics_dict}")
    for code, long_name in metrics_dict.items():
        _create_metric(notion, code, long_name)


def _create_metric(notion, unique_id, long_name):
    logging.info("Adding a new metrics to notion database")
    notion.pages.create(
        parent=dict(type="database_id", database_id=NOTION_SECURITY_METRICS_DB),
        properties=dict(
            LongName=dict(title=[dict(text=dict(content=long_name))]),
            UniqueId=dict(rich_text=[dict(text=dict(content=unique_id))]),
        ),
    )


if __name__ == "__main__":
    app()
