"""
Mixins for inventory ViewSets.

As of Phase 0 the org-scoping logic was promoted to the shared
`apps.common.mixins.OrgScopeMixin`. `InventoryOrgScopeMixin` is kept as a
thin alias so every existing inventory ViewSet keeps working unchanged.

Two cross-cutting invariants (now enforced in the common mixin):
1. Querysets are ALWAYS scoped to the organizations the user is a member of.
2. Optional `organization` / `location` query params narrow further, but only
   after verifying the user belongs to that organization.
"""
from apps.common.mixins import OrgScopeMixin


class InventoryOrgScopeMixin(OrgScopeMixin):
    """Alias of the shared OrgScopeMixin — kept for import stability."""
    pass
