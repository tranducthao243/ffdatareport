import json
import os

import requests


URL = "https://socialdata.garena.vn/graphql"


def gql(query: str, variables: dict | None = None) -> dict:
    cookie = os.environ.get("DATASOCIAL_USESSION", "").strip()
    if not cookie:
        raise SystemExit("DATASOCIAL_USESSION is empty")

    response = requests.post(
        URL,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"usession={cookie}",
        },
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    print(f"HTTP: {response.status_code}")
    response.raise_for_status()
    data = response.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def main() -> None:
    print("=== Query fields ===")
    gql('query { __type(name: "Query") { fields { name } } }')

    print("=== listPost field ===")
    schema_data = gql(
        'query { __schema { queryType { fields { name args { name type { kind name ofType { kind name ofType { kind name } } } } } } } }'
    )
    for field in schema_data["data"]["__schema"]["queryType"]["fields"]:
        if field["name"] == "listPost":
            print(json.dumps(field, ensure_ascii=False, indent=2))

    print("=== Post type ===")
    gql(
        'query { __type(name: "Post") { name fields { name type { kind name ofType { kind name ofType { kind name } } } } } }'
    )


if __name__ == "__main__":
    main()
