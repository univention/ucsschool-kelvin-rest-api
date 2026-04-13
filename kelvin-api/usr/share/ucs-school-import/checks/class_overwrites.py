# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import importlib
import inspect

from ucsschool.importer.exceptions import InitialisationError
from ucsschool.importer.utils.configuration_checks import ConfigurationChecks


class ClassOverwriteConfigurationCheck(ConfigurationChecks):
    def test_01_no_overwrite(self):
        classes = self.config.get("classes", {})
        for k, v in classes.items():
            self.logger.info(f"Checking class override for {k}: {v}")
            if v == "":  # Empty module names are being ignored by the Import Framework
                continue
            module_name, class_name = v.rsplit(".", 1)
            try:
                imported_module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                raise InitialisationError(
                    f"Overwriting the class for {k} is not possible, because the module {module_name} "
                    f"could not be found. You might deactivating the override for Kelvin API by setting"
                    f" the class in the kelvin.json to ''."
                )
            if not inspect.isclass(getattr(imported_module, class_name)):
                raise InitialisationError(
                    f"Overwriting the class for {k} is not possible, because the class {class_name} "
                    f"could not be found in module {module_name}. You might deactivating the override "
                    f"for Kelvin API by setting the class in the kelvin.json to ''."
                )
