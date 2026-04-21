from collections.abc import Iterable
from typing import get_args, get_origin, get_type_hints

from ucsschool_objects.core.domain.ports import Manager


def test_manager_protocol_search_returns_iterable() -> None:
    return_type = get_type_hints(Manager.search)["return"]

    assert get_origin(return_type) is Iterable
    assert get_args(return_type)[0].__name__ == "ManagerT"
