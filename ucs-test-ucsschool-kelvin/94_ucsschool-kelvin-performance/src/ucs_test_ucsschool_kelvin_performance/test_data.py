import random
from typing import Any, final

from diskcache import Index

from .settings_locust import get_settings


@final
class TestData(object):
    def __init__(self):
        self.settings = get_settings()
        self.db = Index(str(self.settings.test_data_path))

    @property
    def schools(self) -> list[str]:
        return self.db["schools"]

    def random_school(self) -> str:
        """Return a random school from the dataset"""
        return random.choice(self.schools)  # nosec

    def school_staff(self, school: str) -> list[str]:
        """Return all staff ``username``s of ``school``"""
        return list(self.db[school]["staff"])

    def school_user(self, school: str, username: str) -> dict[str, Any]:
        """Return the detailed``username`` of a random user from ``school``"""
        return self.db[school]["users"][username]

    def random_user(self, school: str) -> str:
        """Return the ``username`` of a random user from ``school``"""
        return random.choice(self.db[school]["users"])  # nosec

    def random_users(self, school: str, k: int = 10) -> list[str]:
        """Return ``k`` random ``username``s from ``school``"""
        return random.sample(self.db[school]["users"], k=k)  # nosec

    def random_student(self, school: str) -> str:
        """Return the ``username`` of a random student from ``school``"""
        return random.choice(self.db[school]["students"])  # nosec

    def random_students(self, school: str, k: int = 10) -> list[str]:
        """Return ``k`` random ``username``s from ``school`` which have the role student"""
        return random.sample(self.db[school]["students"], k=k)  # nosec

    def random_workgroup(self, school: str) -> str:
        """Return a random workgroup from ``school``"""
        return random.choice(self.db[school]["workgroups"])  # nosec

    def random_class(self, school: str) -> str:
        """Return a random class from ``school``"""
        return random.choice(self.db[school]["school_classes"])  # nosec
