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

    return {
        "tag": "interactive_message",
        "interactive_message": {
            "elements": [
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
                {
                    "element_type": "button_group",
                    "button_group": buttons,
                },
            ]
        },
    }


def build_report_interactive_payload(package: dict) -> dict:
    rendered_text = str(package.get("renderedText") or "").strip()
    title = str(package.get("title") or package.get("reportCode") or "Report").strip()
    description = rendered_text
    if description.startswith(title):
        description = description[len(title):].lstrip("\n").strip()
    if not description:
        description = rendered_text or "Khong co du lieu."
    return build_interactive_payload(
        title=title,
        description=description,
        actions=list(package.get("interactiveActions") or []),
    )
