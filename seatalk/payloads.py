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
                    "tag": "title",
                    "title": {"text": title},
                },
                {
                    "tag": "description",
                    "description": {"text": description},
                },
                {
                    "tag": "button_group",
                    "buttons": buttons,
                },
            ]
        },
    }
