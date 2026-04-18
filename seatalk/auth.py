from __future__ import annotations

from datasocial.seatalk import SeaTalkClient, SeaTalkSettings


def build_seatalk_client(
    *,
    app_id: str,
    app_secret: str,
    group_id: str = "",
    employee_code: str = "",
) -> SeaTalkClient:
    settings = SeaTalkSettings(
        app_id=app_id,
        app_secret=app_secret,
        group_id=group_id,
        employee_code=employee_code,
    )
    return SeaTalkClient(settings)
