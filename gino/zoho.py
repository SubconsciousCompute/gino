"""Zoho intergation."""

import os

import typer
import requests


from cmo.common import load_config

app = typer.Typer()

ZOHO = None


def get_zoho_client():
    global ZOHO
    if ZOHO is not None:
        return ZOHO
    load_config()
    app_id = os.environ["ZOHO_CLIENT_ID"]
    secret = os.environ["ZOHO_CLIENT_SECRET"]
    ZOHO = ZohoClient(app_id, secret)
    return ZOHO


class ZohoClient:
    def __init__(self, app_id, secret):
        self.leave_base_url = (
            "https://people.zoho.com/people/api/v2/leavetracker/reports/user"
        )
        self.app_id = app_id
        self.secret = secret

    def get(self, url, data={}):
        headers = {"Authorization": "Zoho-oauthtoken " + self.secret}
        payload = dict(employee='sc1001')
        return requests.get(url, headers=headers, params=payload)

    def get_leaves(self, data={}):
        response = self.get(self.leave_base_url, **data)
        response.raise_for_status()
        return response.json()


@app.command()
def today_leave_status():
    zoho = get_zoho_client()
    zoho.get_leaves()


if __name__ == "__main__":
    app()
