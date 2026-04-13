#!/usr/bin/make -f

# SPDX-FileCopyrightText: 2012 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

PKG := ucs-school-lib
VERSION := $(shell dpkg-parsechangelog | sed -ne 's/^Version: //p')

PO_FILE := modules/ucsschool/lib/de.po
MO_FILE := modules/ucsschool/lib/python-ucs-school.mo
PYTHON_FILES := $(shell find modules -name "*.py")
INST_DIR := $(DESTDIR)/usr/share/locale/de/LC_MESSAGES/

.PHONY: build
build:: l10n

.PHONY: l10n
l10n:: $(MO_FILE)

$(MO_FILE):: $(PO_FILE)
	msgfmt --check --output-file "$@" "$<"

$(PO_FILE):: $(PO_FILE).tmp
	if [ -e "$@" ]; then \
		msgmerge --update --sort-output "$@" "$<"; \
		touch "$@"; \
	else \
		cp "$<" "$@"; \
	fi

$(PO_FILE).tmp:: $(PYTHON_FILES)
	xgettext --output=$(@) \
		--language=Python \
		--keyword=N_:1 \
		--sort-output \
		--package-name=$(PKG) \
		--package-version=$(VERSION) \
		--msgid-bugs-address="packages@univention.de" \
		--copyright-holder="Univention GmbH" \
		$^

.PHONY: clean
clean::
	$(RM) $(MO_FILE) $(PO_FILE).tmp
