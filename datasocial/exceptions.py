class DatasocialError(Exception):
    """Base error."""


class GraphQLHTTPError(DatasocialError):
    """HTTP-level GraphQL failure."""


class GraphQLResponseError(DatasocialError):
    """GraphQL-level error payload."""


class GraphQLParseError(DatasocialError):
    """Invalid response shape."""
