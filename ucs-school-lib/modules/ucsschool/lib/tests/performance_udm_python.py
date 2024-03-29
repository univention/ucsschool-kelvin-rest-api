import random
import sys
import time
from multiprocessing import Pool
from typing import Any, Dict, List, Optional, Tuple

from faker import Faker

from univention.udm import UDM
from univention.udm.base import BaseModule, BaseObject

try:
    PARALLELISM = int(sys.argv[1])
except (ValueError, IndexError):
    print("Usage: {} <paralellism>")
    sys.exit(1)

fake = Faker()

NUMBER_USERS = 900
SCHOOL_OU = fake.user_name()[:10]
STR_NUMERIC = "0123456789"
STR_ALPHA = "abcdefghijklmnopqrstuvwxyz"
STR_ALPHANUM = STR_ALPHA + STR_NUMERIC

LDAP_BASE_DN = "dc=uni,dc=dtr"
AUTH = ("Administrator", "univention")


user_mod: BaseModule = UDM.credentials(*AUTH).version(0).get("users/user")


def random_string(  # nosec
    length: Optional[int] = 10,
    alpha: Optional[bool] = True,
    numeric: Optional[bool] = True,
) -> str:
    result = ""
    for _ in range(length):
        if alpha and numeric:
            result += random.choice(STR_ALPHANUM)
        elif alpha:
            result += random.choice(STR_ALPHA)
        elif numeric:
            result += random.choice(STR_NUMERIC)
    return str(result)


def random_name(length: int = 10) -> str:
    """
    create random name (1 ALPHA, 8 ALPHANUM, 1 ALPHA)
    """
    return (
        random_string(length=1, alpha=True, numeric=False)
        + random_string(length=(length - 2), alpha=True, numeric=True)
        + random_string(length=1, alpha=True, numeric=False)
    )


def create_objs_via_UDM_python_sequential(
    datas: List[Dict[str, Any]],
) -> List[str]:
    res = []
    for data in datas:
        obj: BaseObject = user_mod.new(data["superordinate"])
        obj.options = data["options"]
        obj.policies = data["policies"].keys()
        obj.position = data["position"]
        for k, v in data["properties"].items():
            setattr(obj.props, k, v)
        obj.save()
        res.append(obj.dn)
    return res


def user_resource_kwargs(school):
    return {
        "properties": {
            "username": "test{}".format(random_name()),
            "password": random_name(),
            "firstname": random_name(),
            "lastname": random_name(),
            "birthday": "2015-05-15",
            "disabled": False,
            "groups": [
                "cn={0}-Da,cn=klassen,cn=schueler,cn=groups,ou={0},{1}".format(school, LDAP_BASE_DN),
                "cn={0}-Db,cn=klassen,cn=schueler,cn=groups,ou={0},{1}".format(school, LDAP_BASE_DN),
            ],
        },
        "position": "cn=lehrer,cn=users,ou={},{}".format(school, LDAP_BASE_DN),
        "superordinate": None,
        "options": {"ucsschoolTeacher": True},
        "policies": {},
    }


def create_objs_via_UDM_python_parallel(
    school: str, num: int, parallelism: int
) -> Tuple[float, List[str]]:
    # create `parallelism` amount of processes each working on a `num / parallelism` long list
    assert num % parallelism == 0
    if parallelism == 1:
        dns = []
        kwargs = [user_resource_kwargs(school) for _ in range(num)]
        t0 = time.time()
        for kw in kwargs:
            dns.extend(create_objs_via_UDM_python_sequential([kw]))
        return time.time() - t0, dns
    kwargs = [
        [user_resource_kwargs(school) for i in range(int(num / parallelism))] for j in range(parallelism)
    ]
    pool = Pool(processes=parallelism)
    t0 = time.time()
    map_async_result = pool.map_async(create_objs_via_UDM_python_sequential, kwargs)
    results = map_async_result.get()
    t1 = time.time() - t0
    dns = []
    for res in results:
        dns.extend(res)
    return t1, dns


def read_objs_via_UDM_python(dns: List[str]) -> None:
    for dn in dns:
        obj: BaseObject = user_mod.get(dn)
        assert obj.dn == dn


def read_objs_via_UDM_python_parallel(dns: List[str], parallelism: int) -> float:
    # create `parallelism` amount of processes each working on a `num / parallelism` long list
    assert len(dns) % parallelism == 0
    if parallelism == 1:
        t0 = time.time()
        for dn in dns:
            read_objs_via_UDM_python([dn])
        return time.time() - t0
    kwargs: List[List[str]] = [dns[i : i + parallelism] for i in range(0, len(dns), parallelism)]
    pool = Pool(processes=parallelism)
    t0 = time.time()
    map_async_result = pool.map_async(read_objs_via_UDM_python, kwargs)
    _results = map_async_result.get()  # noqa: F841 for pytest output
    return time.time() - t0


def modify_objs_via_UDM_python(dns: List[str]) -> float:
    t_delta = 0.0
    for dn in dns:
        obj: BaseObject = user_mod.get(dn)
        obj.props.firstname = random_name()
        obj.props.lastname = random_name()
        t0 = time.time()
        obj.save()
        t_delta += time.time() - t0
        obj_new: BaseObject = user_mod.get(dn)
        assert obj_new.props.firstname == obj.props.firstname
        assert obj_new.props.lastname == obj.props.lastname
    return t_delta


def modify_objs_via_UDM_python_parallel(dns: List[str], parallelism: int) -> float:
    assert len(dns) % parallelism == 0
    if parallelism == 1:
        t0 = time.time()
        for dn in dns:
            modify_objs_via_UDM_python([dn])
        return time.time() - t0
    kwargs: List[List[str]] = [dns[i : i + parallelism] for i in range(0, len(dns), parallelism)]
    pool = Pool(processes=parallelism)
    map_async_result = pool.map_async(modify_objs_via_UDM_python, kwargs)
    results = map_async_result.get()
    return sum(results)


def delete_objs_via_UDM_python(dns: List[str]) -> None:
    for dn in dns:
        obj: BaseObject = user_mod.get(dn)
        obj.delete()


def delete_objs_via_UDM_python_parallel(dns: List[str], parallelism: int) -> float:
    assert len(dns) % parallelism == 0
    if parallelism == 1:
        t0 = time.time()
        for dn in dns:
            delete_objs_via_UDM_python([dn])
        return time.time() - t0
    kwargs: List[List[str]] = [dns[i : i + parallelism] for i in range(0, len(dns), parallelism)]
    pool = Pool(processes=parallelism)
    t0 = time.time()
    map_async_result = pool.map_async(delete_objs_via_UDM_python, kwargs)
    _results = map_async_result.get()  # noqa: F841 for pytest output
    return time.time() - t0


def main() -> None:
    print("Starting UDM Python tests (parallelism={})...".format(PARALLELISM))
    print("Connection args: {!r}".format(AUTH))
    print("Creating {} Users...".format(NUMBER_USERS))
    t_1000_1, dns = create_objs_via_UDM_python_parallel(SCHOOL_OU, NUMBER_USERS, PARALLELISM)
    time.sleep(30)

    print("Reading {} Users...".format(NUMBER_USERS))
    t_1000_2 = read_objs_via_UDM_python_parallel(dns, PARALLELISM)

    print("Modifying {} Users...".format(NUMBER_USERS))
    t_1000_3 = modify_objs_via_UDM_python_parallel(dns, PARALLELISM)
    time.sleep(15)

    print("Deleting {} Users...".format(NUMBER_USERS))
    t_1000_4 = delete_objs_via_UDM_python_parallel(dns, PARALLELISM)

    print("Results:")
    print("Seconds for creating   {} Users: {:02.2f}".format(NUMBER_USERS, t_1000_1))
    print("Seconds for reading    {} Users: {:02.2f}".format(NUMBER_USERS, t_1000_2))
    print("Seconds for modifying  {} Users: {:02.2f}".format(NUMBER_USERS, t_1000_3))
    print("Seconds for deleting   {} Users: {:02.2f}".format(NUMBER_USERS, t_1000_4))


if __name__ == "__main__":
    main()
