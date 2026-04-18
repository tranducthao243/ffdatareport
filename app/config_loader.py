from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from datasocial.exceptions import DatasocialError


VALID_ANALYZER_CODES = {"TOPA", "TOPB", "TOPC", "TOPD", "TOPE", "TOPF"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_group_target(group: dict[str, Any]) -> str:
    if group.get("group_id"):
        return str(group["group_id"]).strip()
    env_key = str(group.get("group_id_env") or "").strip()
    if env_key:
        return os.getenv(env_key, "").strip()
    return ""


def validate_reporting_config(
    groups_config: dict[str, Any],
    reports_config: dict[str, Any],
    campaigns_config: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    group_states: list[dict[str, Any]] = []

    groups = groups_config.get("groups")
    if not isinstance(groups, list):
        raise DatasocialError("Invalid groups config: 'groups' must be a list.")

    reports = reports_config.get("reports")
    if not isinstance(reports, dict):
        raise DatasocialError("Invalid reports config: 'reports' must be an object.")

    if not isinstance(campaigns_config, list):
        raise DatasocialError("Invalid campaigns config: root value must be a list.")

    campaign_names_seen: set[str] = set()
    campaign_names: set[str] = set()
    for campaign in campaigns_config:
        name = str(campaign.get("name") or "").strip()
        if not name:
            errors.append(
                {
                    "code": "invalid_campaign",
                    "message": "Campaign entry is missing 'name'.",
                }
            )
            continue
        if name in campaign_names_seen:
            errors.append(
                {
                    "code": "duplicate_campaign",
                    "campaignName": name,
                    "message": f"Campaign '{name}' is duplicated in campaigns.json.",
                }
            )
            continue
        campaign_names_seen.add(name)
        campaign_names.add(name)

        hashtags = campaign.get("hashtags")
        if not isinstance(hashtags, list) or not hashtags:
            errors.append(
                {
                    "code": "invalid_campaign_hashtags",
                    "campaignName": name,
                    "message": f"Campaign '{name}' must define a non-empty hashtags list.",
                }
            )

    seen_group_names: set[str] = set()
    invalid_group_names: set[str] = set()

    for index, group in enumerate(groups):
        name = str(group.get("name") or "").strip() or f"group_{index}"
        enabled = bool(group.get("enabled", True))
        report_code = str(group.get("report_code") or "").strip()
        state = {
            "groupName": name,
            "enabled": enabled,
            "reportCode": report_code,
            "status": "disabled" if not enabled else "valid",
            "messages": [],
            "resolvedGroupId": bool(resolve_group_target(group)),
        }

        if name in seen_group_names:
            errors.append(
                {
                    "code": "duplicate_group",
                    "groupName": name,
                    "message": f"Group '{name}' is duplicated in groups.json.",
                }
            )
            invalid_group_names.add(name)
            state["status"] = "invalid"
            state["messages"].append("duplicate_group")
        else:
            seen_group_names.add(name)

        if not enabled:
            group_states.append(state)
            continue

        if not report_code:
            errors.append(
                {
                    "code": "missing_report_code",
                    "groupName": name,
                    "message": f"Enabled group '{name}' is missing report_code.",
                }
            )
            invalid_group_names.add(name)
            state["status"] = "invalid"
            state["messages"].append("missing_report_code")
            group_states.append(state)
            continue

        report_def = reports.get(report_code)
        if not isinstance(report_def, dict):
            errors.append(
                {
                    "code": "unknown_report_code",
                    "groupName": name,
                    "reportCode": report_code,
                    "message": f"Group '{name}' references unknown report_code '{report_code}'.",
                }
            )
            invalid_group_names.add(name)
            state["status"] = "invalid"
            state["messages"].append("unknown_report_code")
            group_states.append(state)
            continue

        sections = report_def.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append(
                {
                    "code": "invalid_report_sections",
                    "groupName": name,
                    "reportCode": report_code,
                    "message": f"Report '{report_code}' must define a non-empty sections list.",
                }
            )
            invalid_group_names.add(name)
            state["status"] = "invalid"
            state["messages"].append("invalid_report_sections")
            group_states.append(state)
            continue

        unknown_sections = [section for section in sections if section not in VALID_ANALYZER_CODES]
        if unknown_sections:
            errors.append(
                {
                    "code": "unknown_section_code",
                    "groupName": name,
                    "reportCode": report_code,
                    "message": f"Report '{report_code}' uses unsupported sections: {', '.join(unknown_sections)}.",
                }
            )
            invalid_group_names.add(name)
            state["status"] = "invalid"
            state["messages"].append("unknown_section_code")

        if "TOPD" in sections:
            campaign_list = group.get("campaign_names")
            if not isinstance(campaign_list, list) or not campaign_list:
                errors.append(
                    {
                        "code": "missing_campaign_names",
                        "groupName": name,
                        "message": f"Group '{name}' uses TOPD but does not define campaign_names.",
                    }
                )
                invalid_group_names.add(name)
                state["status"] = "invalid"
                state["messages"].append("missing_campaign_names")
            else:
                missing_campaigns = [
                    str(campaign_name)
                    for campaign_name in campaign_list
                    if str(campaign_name) not in campaign_names
                ]
                if missing_campaigns:
                    errors.append(
                        {
                            "code": "unknown_campaign_name",
                            "groupName": name,
                            "message": f"Group '{name}' references missing campaigns: {', '.join(missing_campaigns)}.",
                        }
                    )
                    invalid_group_names.add(name)
                    state["status"] = "invalid"
                    state["messages"].append("unknown_campaign_name")

        if not state["resolvedGroupId"]:
            warnings.append(
                {
                    "code": "missing_group_id",
                    "groupName": name,
                    "message": f"Group '{name}' has no resolved group id. It will be built but skipped during send.",
                }
            )
            state["messages"].append("missing_group_id")

        group_states.append(state)

    return {
        "errors": errors,
        "warnings": warnings,
        "groupStates": group_states,
        "invalidGroupNames": sorted(invalid_group_names),
    }


def format_validation_errors(validation: dict[str, Any]) -> str:
    lines = ["Invalid reporting config:"]
    for item in validation.get("errors", []):
        lines.append(f"- {item['message']}")
    return "\n".join(lines)
