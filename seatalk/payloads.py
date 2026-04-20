from __future__ import annotations


def build_text_payload(content: str) -> str:
    return content


def build_interactive_payload(
    *,
    title: str,
    description: str,
    actions: list[dict],
) -> dict:
    buttons = []
    for action in actions[:5]:
        buttons.append(
            {
                "text": action.get("label", "Open"),
                "button_type": "callback",
                "value": action.get("callbackPayload", ""),
            }
        )

    elements = [
        {
            "element_type": "title",
            "title": {"text": title},
        },
        {
            "element_type": "description",
            "description": {
                "format": 1,
                "text": description,
            },
        },
    ]
    if buttons:
        elements.append(
            {
                "element_type": "button_group",
                "button_group": buttons,
            }
        )

    return {
        "tag": "interactive_message",
        "interactive_message": {
            "elements": elements
        },
    }


def build_report_interactive_payload(package: dict) -> dict:
    title = str(package.get("title") or package.get("reportCode") or "Report").strip()
    return build_interactive_payload(
        title=title,
        description="Mo nhanh phan du lieu can xem them.",
        actions=list(package.get("interactiveActions") or []),
    )


def build_interactive_group_payload(group: dict) -> dict:
    return build_interactive_payload(
        title=str(group.get("title") or "Mo rong bao cao").strip(),
        description=str(group.get("description") or "").strip(),
        actions=list(group.get("actions") or []),
    )


def build_callback_report_payload(*, title: str, summary: str) -> dict:
    return build_interactive_payload(
        title=title,
        description=summary,
        actions=[],
    )
