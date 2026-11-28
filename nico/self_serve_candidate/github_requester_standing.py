"""Pure admission from trusted server-side GitHub App user-token API results.

Never decode a browser payload into this contract; the same authorized server-side
user-token context must fetch all three observations freshly. No I/O or grants.
"""
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Standing:
    actor_id: int
    app_id: int
    installation_id: int
    repository_id: int


def _same_id(value: object, expected: object) -> bool:
    return type(value) is type(expected) is int and value == expected and value > 0


def verify_standing(*, authenticated_user, user_installations, installation_repositories,
                    expected_actor_id, expected_app_id, expected_installation_id,
                    expected_repository_id) -> Standing | None:
    """Admit only pull permission explicitly observed in the selected installation.

    The trusted caller must select the repositories endpoint by
    expected_installation_id, and combine all verified pagination pages first.
    """
    if (not isinstance(authenticated_user, Mapping)
            or not _same_id(authenticated_user.get("id"), expected_actor_id)
            or authenticated_user.get("type") != "User"
            or not isinstance(user_installations, (tuple, list))
            or not isinstance(installation_repositories, (tuple, list))):
        return None
    installs = [row for row in user_installations if isinstance(row, Mapping)
                and _same_id(row.get("id"), expected_installation_id)]
    if (len(installs) != 1 or not _same_id(installs[0].get("app_id"), expected_app_id)
            or "suspended_at" not in installs[0] or installs[0]["suspended_at"] is not None):
        return None
    repos = [row for row in installation_repositories if isinstance(row, Mapping)
             and _same_id(row.get("id"), expected_repository_id)]
    if len(repos) != 1:
        return None
    permissions = repos[0].get("permissions")
    if not isinstance(permissions, Mapping) or permissions.get("pull") is not True:
        return None
    return Standing(expected_actor_id, expected_app_id, expected_installation_id, expected_repository_id)


def verify_commissioning_authority(*, repository_details, **standing_inputs) -> Standing | None:
    """Owner/admin-only first path; site-wide admin and attestations are not proof.

    repository_details must be obtained by the trusted server using the same
    fresh user token as the standing observations. No delegated grants here.
    This check neither starts an assessment nor authorizes a report download.
    """
    standing = verify_standing(**standing_inputs)
    if (standing is None or not isinstance(repository_details, Mapping)
            or not _same_id(repository_details.get("id"), standing.repository_id)):
        return None
    owner = repository_details.get("owner")
    if not isinstance(owner, Mapping):
        return None
    owner_id = owner.get("id")
    if not _same_id(owner_id, owner_id) or owner.get("type") not in ("User", "Organization"):
        return None
    if owner.get("type") == "User" and _same_id(owner_id, standing.actor_id):
        return standing
    permissions = repository_details.get("permissions")
    if isinstance(permissions, Mapping) and permissions.get("admin") is True:
        return standing
    return None
