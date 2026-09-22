# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import random
from typing import Any, final

from diskcache import Index

from .settings_locust import get_settings


@final
class TestData(object):
    """One instance is shared per process, so picks use the caller's seeded
    generator (see ``KelvinClient.rng``) rather than the ``random`` module."""

    def __init__(self):
        self.settings = get_settings()
        self.db = Index(str(self.settings.test_data_path))

    @property
    def schools(self) -> list[str]:
        return self.db["schools"]

    def random_school(self, rng: random.Random) -> str:
        """Return a random school from the dataset"""
        return rng.choice(self.schools)

    def school_staff(self, school: str) -> list[str]:
        """Return all staff ``username``s of ``school``"""
        return list(self.db[school]["staff"])

    def school_user(self, school: str, username: str) -> dict[str, Any]:
        """Return the detailed``username`` of a random user from ``school``"""
        return self.db[school]["users"][username]

    def random_user(self, rng: random.Random, school: str) -> str:
        """Return the ``username`` of a random user from ``school``"""
        return rng.choice(self.db[school]["users"])

    def random_users(self, rng: random.Random, school: str, k: int = 10) -> list[str]:
        """Return ``k`` random ``username``s from ``school``"""
        return rng.sample(self.db[school]["users"], k=k)

    def random_student(self, rng: random.Random, school: str) -> str:
        """Return the ``username`` of a random student from ``school``"""
        return rng.choice(self.db[school]["students"])

    def random_students(self, rng: random.Random, school: str, k: int = 10) -> list[str]:
        """Return ``k`` random ``username``s from ``school`` which have the role student"""
        return rng.sample(self.db[school]["students"], k=k)

    def random_workgroup(self, rng: random.Random, school: str) -> str:
        """Return a random workgroup from ``school``"""
        return rng.choice(self.db[school]["workgroups"])

    def random_class(self, rng: random.Random, school: str) -> str:
        """Return a random class from ``school``"""
        return rng.choice(self.db[school]["school_classes"])
