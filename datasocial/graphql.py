from __future__ import annotations


LIST_POST_QUERY = """
query ListPost(
  $appId: UInt32!
  $filter: JSON
  $page: UInt32
  $perPage: UInt16
  $sortField: String
  $sortOrder: OrderEnum
) {
  listPost(
    appId: $appId
    filter: $filter
    page: $page
    perPage: $perPage
    sortField: $sortField
    sortOrder: $sortOrder
  ) {
    total
    results {
      id
      channelId
      sub
      alias
      type
      name
      url
      tags
      createdAt
      metrics
      thumbnail
    }
  }
}
""".strip()


def build_list_post_variables(
    *,
    app_id: int,
    created_at_gte: str | None,
    created_at_lte: str | None,
    category_ids: list[int] | None,
    platform_ids: list[int] | None,
    channel_ids: list[int] | None,
    page: int,
    per_page: int,
) -> dict:
    filter_payload: dict[str, object] = {}
    if created_at_gte:
        filter_payload["createdAt_gte"] = created_at_gte
    if created_at_lte:
        filter_payload["createdAt_lte"] = created_at_lte

    channel_filter: dict[str, object] = {}
    if category_ids:
        channel_filter["categoryId_in"] = category_ids
    if platform_ids:
        channel_filter["plat_in"] = platform_ids
    if channel_ids:
        channel_filter["id_in"] = channel_ids
    if channel_filter:
        filter_payload["channel"] = channel_filter

    return {
        "appId": app_id,
        "filter": filter_payload or None,
        "page": page,
        "perPage": per_page,
        "sortField": "createdAt",
        "sortOrder": "DESC",
    }
