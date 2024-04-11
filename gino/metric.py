import cmo.notion
import cmo.common
from cmo import _bmo

import typer

app = typer.Typer()


@app.command()
def sync():
    # pylint: disable=no-member
    token = cmo.common.get_config("METRIC_API_TOKEN")
    assert token, "METRIC_API_TOKEN is not set"
    metrics = _bmo.available_metrics(token)
    cmo.notion.sync_metrics(metrics)

    vm_token = cmo.common.get_config("VM_TOKEN")
    metrics = _bmo.available_metrics_os(vm_token, "Windows")
    print(metrics)


if __name__ == "__main__":
    app()
