import random
from typing import Any, Dict, List

from diskcache import Index

from .settings_locust import get_settings


class TestData(object):
    def __init__(self):
        self.settings = get_settings()
        self.db = Index(str(self.settings.test_data_path))

    @property
    def schools(self) -> List[str]:
        # return self.db["schools"]
        return ["001", "002", "003", "004"]

    def random_school(self) -> str:
        """Return a random school from the dataset"""
        return random.choice(self.schools)  # nosec

    def school_staff(self, school: str) -> List[str]:
        """Return all staff ``username``s of ``school``"""
        return list(self.db[school]["staff"].keys())

    def school_user(self, school: str, username: str) -> Dict[str, Any]:
        """Return the detailed``username`` of a random user from ``school``"""
        return self.db[school]["users"][username]

    def random_user(self, school: str) -> str:
        """Return the ``username`` of a random user from ``school``"""
        return random.choice(list(self.db[school]["users"].keys()))  # nosec

    def random_users(self, school: str, k: int = 10) -> List[str]:
        """Return ``k`` random ``username``s from ``school``"""
        return random.sample(list(self.db[school]["users"].keys()), k=k)  # nosec

    def random_student(self, school: str) -> str:
        """Return the ``username`` of a random student from ``school``"""
        return random.choice(list(self.db[school]["students"].keys()))  # nosec

    def random_students(self, school: str, k: int = 10) -> List[str]:
        """Return ``k`` random ``username``s from ``school`` which have the role student"""
        return random.sample(list(self.db[school]["students"].keys()), k=k)  # nosec

    def random_workgroup(self, school: str) -> str:
        """Return a random workgroup from ``school``"""
        return random.choice(self.db[school]["workgroups"])  # nosec

    def random_class(self, school: str) -> str:
        """Return a random class from ``school``"""
        # return random.choice(self.db[school]["classes"])
        classes = {"001": ["1a"], "002": ["1a"], "003": ["1a"], "004": ["1a"]}
        return random.choice(classes[school])  # nosec
