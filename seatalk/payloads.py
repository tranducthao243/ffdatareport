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
                "text": {"text": action.get("label", "Open")},
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
                    "text": {"text": title},
                },
                {
                    "element_type": "description",
                    "text": {"text": description},
                },
                {
                    "element_type": "button_group",
                    "buttons": buttons,
                },
            ]
        },
    }
