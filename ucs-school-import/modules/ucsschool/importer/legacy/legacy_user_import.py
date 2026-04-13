# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Legacy mass import class.
"""

import copy

from univention.admin.uexceptions import noObject

from ..exceptions import CreationError, DeletionError, UnknownAction
from ..mass_import.user_import import UserImport


class LegacyUserImport(UserImport):
    async def detect_users_to_delete(self):
        """
        No need to compare input and LDAP. Action was written in the CSV file
        and is already stored in user.action.
        """
        self.logger.info("------ Detecting which users to delete... ------")
        users_to_delete = list()
        for user in self.imported_users:
            if user.action == "D":
                try:
                    users_to_delete.append((user.source_uid, user.record_uid, user.input_data))
                except noObject:
                    msg = "User to delete not found in LDAP: {}.".format(user)
                    self.logger.error(msg)
                    self._add_error(DeletionError(msg, entry_count=user.entry_count, import_user=user))
        return users_to_delete

    async def determine_add_modify_action(self, imported_user):
        """
        Determine what to do with the ImportUser. Should set attribute "action"
        to either "A" or "M". If set to "M" the returned user must be a opened
        ImportUser from LDAP.
        Run modify preparations here, like school-move etc.

        :param ImportUser imported_user: ImportUser from input
        :return: ImportUser with action set and possibly fetched from LDAP
        :rtype: ImportUser
        """
        if imported_user.action == "A":
            try:
                user = await imported_user.get_by_import_id_or_username(
                    self.connection,
                    imported_user.source_uid,
                    imported_user.record_uid,
                    imported_user.name,
                )
                if (
                    user.disabled != "0"
                    or await user.has_expiry(self.connection)
                    or await user.has_purge_timestamp(self.connection)
                ):
                    self.logger.info(
                        "Found user %r that was previously deactivated or is scheduled for deletion "
                        "(purge timestamp is non-empty), reactivating user.",
                        user,
                    )
                    imported_user.old_user = copy.deepcopy(user)
                    imported_user.prepare_all(new_user=False)
                    # make school move first, reactivate freshly fetched user
                    if user.school != imported_user.school:
                        user = self.school_move(imported_user, user)
                    if self.dry_run:
                        self.logger.info("Dry-run: not reactivating.")
                    else:
                        user.reactivate()
                    user.update(imported_user)
                    user.action = "M"
                else:
                    raise CreationError(
                        "User {} (source_uid:{} record_uid: {}) exist, but input demands 'A'.".format(
                            imported_user, imported_user.source_uid, imported_user.record_uid
                        ),
                        entry_count=imported_user.entry_count,
                        import_user=imported_user,
                    )
            except noObject:
                # this is expected
                imported_user.prepare_all(new_user=True)
                user = imported_user
        elif imported_user.action == "M":
            try:
                user = await imported_user.get_by_import_id_or_username(
                    self.connection,
                    imported_user.source_uid,
                    imported_user.record_uid,
                    imported_user.name,
                )
                imported_user.old_user = copy.deepcopy(user)
                imported_user.prepare_all(new_user=False)
                if user.school != imported_user.school:
                    user = await self.school_move(imported_user, user)
                if (
                    user.disabled != "0"
                    or await user.has_expiry(self.connection)
                    or await user.has_purge_timestamp(self.connection)
                ):
                    self.logger.info(
                        "Found user %r that was previously deactivated or is scheduled for deletion "
                        "(purge timestamp is non-empty), reactivating user.",
                        user,
                    )
                    if self.dry_run:
                        self.logger.info("Dry-run: not reactivating.")
                    else:
                        user.reactivate()
                user.update(imported_user)
            except noObject:
                imported_user.prepare_all(new_user=True)
                user = imported_user
                user.action = "A"
        elif imported_user.action == "D":
            user = imported_user
        else:
            raise UnknownAction(
                "{} (source_uid:{} record_uid: {}) has unknown action '{}'.".format(
                    imported_user,
                    imported_user.source_uid,
                    imported_user.record_uid,
                    imported_user.action,
                ),
                entry_count=imported_user.entry_count,
                import_user=imported_user,
            )
        return user
