"""Domain errors.

These are raised by the service layer, which knows nothing about HTTP. A single
exception handler in main.py maps them to status codes, so the rules live in one
place and the routes stay thin.
"""


class DomainError(Exception):
    """Base for anything the caller did that the domain refuses."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class NotPermitted(DomainError):
    status_code = 403
    code = "not_permitted"


class Conflict(DomainError):
    """The request was well-formed but conflicts with current state, e.g.
    joining a game you already joined."""

    status_code = 409
    code = "conflict"


class InvalidTransition(DomainError):
    """The game cannot move from its current state to the requested one."""

    status_code = 409
    code = "invalid_transition"


class AuthError(DomainError):
    status_code = 401
    code = "unauthorized"
