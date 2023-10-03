#  Copyright (c) 2019-2023 SRI International.

from prism.server.CS2.roles.announcing_role import AnnouncingRole


class Dummy(AnnouncingRole, registry_name="DUMMY"):
    @property
    def ark_ready(self) -> bool:
        return False

    @property
    def ark_broadcasting(self) -> bool:
        return False
