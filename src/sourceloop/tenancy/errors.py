class CrossTenantAccessError(Exception):
    """Raised when a repository returns a row belonging to a different tenant."""

    pass
