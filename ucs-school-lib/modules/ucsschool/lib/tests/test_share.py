import pytest

from ucsschool.lib.models.group import SchoolClass, WorkGroup
from ucsschool.lib.models.share import ClassShare, MarketplaceShare, WorkGroupShare
from udm_rest_client import UDM


def _inside_docker():
    try:
        import ucsschool.kelvin.constants
    except ImportError:
        return False
    return ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists()


pytestmark = pytest.mark.skipif(
    not _inside_docker(),
    reason="Must run inside Docker container started by appcenter.",
)


async def check_acls(share, udm, expected_acls):
    # Bug #55103: These are the NT ACLs, which are applied in the school lib, when the share is created.
    school_lib_acls = share.get_nt_acls(udm)
    assert not any(["b'" in acl for acl in school_lib_acls])
    # Test if the school lib acls are set correct in UDM.
    share_udm = await share.get_udm_object(udm)
    udm_acls = set(share_udm.props.appendACL)
    assert udm_acls == set(school_lib_acls)
    # The acls are not fixed strings and depend on the sids of the groups,
    # but we can amongst others, test if the composition of them is correct.
    # A more direct test could test if the methods contain the sids.
    assert set(share.get_nt_acls(udm)) == set(expected_acls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ObjectClass,ShareClass",
    [(SchoolClass, ClassShare), (WorkGroup, WorkGroupShare)],
)
async def test_group_share_nt_acls(
    create_ou_using_python,
    school_class_attrs,
    workgroup_attrs,
    udm_kwargs,
    ObjectClass,
    ShareClass,
):
    ou = await create_ou_using_python()
    if isinstance(ObjectClass, SchoolClass):
        _attrs = await school_class_attrs(ou)
    else:
        _attrs = await workgroup_attrs(ou)
    create_attr = _attrs.copy()
    create_attr["name"] = f"{ou}-{create_attr['name']}"
    async with UDM(**udm_kwargs) as udm:
        group1 = ObjectClass(**create_attr)
        await group1.create(udm)
        sc0 = await ObjectClass.from_dn(group1.dn, ou, udm)
        share = ShareClass.from_school_group(school_group=sc0)
        expected_acls = share.get_aces_deny_students_change_permissions(udm)
        samba_sid = share.get_groups_samba_sid(udm, sc0.dn)
        expected_acls.append("(A;OICI;0x001f01ff;;;{})".format(samba_sid))
        expected_acls.extend(share.get_ou_admin_full_control(udm))
        await check_acls(share, udm, expected_acls)


@pytest.mark.asyncio
async def test_marktplatz_share_nt_acls(create_ou_using_python, udm_kwargs):
    ou = await create_ou_using_python(cache=False)
    async with UDM(**udm_kwargs) as udm:
        share = MarketplaceShare(name="Marktplatz", school=ou)
        expected_acls = share.get_aces_deny_students_change_permissions(udm)
        search_base = share.get_search_base(share.school)
        domain_users_dn = "cn=Domain Users %s,%s" % (share.school.lower(), search_base.groups)
        samba_sid = share.get_groups_samba_sid(udm, domain_users_dn)
        expected_acls.append("(A;OICI;0x001f01ff;;;{})".format(samba_sid))
        expected_acls.extend(share.get_ou_admin_full_control(udm))
        await check_acls(share, udm, expected_acls)
