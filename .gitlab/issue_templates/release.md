<!--
SPDX-FileCopyrightText: 2026 Univention GmbH
SPDX-License-Identifier: AGPL-3.0-only
-->
# Kelvin update issue

| Product Value || Reasoning |
|-|-|-|
| User Impact | 0 | + covered by other issues  |
| Product Enablement | 0 | + only release |

## Accounting

- [1] Univention GmbH
- [1050] 22605 - Univention - Entwicklung
- [14954] Development: Product Maintenance

kaze://localhost/14954?desc=Kelvin+Release

## Checklist

- [ ] Check contents of [kelvin-api/changelog.rst](./kelvin-api/changelog.rst)
- [ ] Kelvin [Jenkins tests](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API%20(branch%20main)/) OK
- [ ] Kelvin client [Jenkins test](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/Kelvin-client-daily) OK
- [ ] Jenkins in [test appcenter](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API)
- [ ] Create git tag with version you want to publish
- [ ] Monitor the pipeline and follow instructions in manual steps
- [ ] API still works (smoke test)
- [ ] Release QA (upgrade and smoke test)
- [ ] Close issues & bugs

/label ~"App::Kelvin"
/label ~"Team::ByteBenders"
/label ~"Release"
