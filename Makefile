SHELL := /usr/bin/env bash
.PHONY: help fetch-vm-data build-docker-image dev-server local-tests local-server
.DEFAULT_GOAL := help

VM_CONF_DIR := "dev/_vm_config"

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

update-architecture-docs:
	# Updates entity tables and diagrams in the architecture documentation
	# This is a semi manual process: If sqlalchemy class names change, they need to
	# be changed here and included in the architecture.rst file.
	# For example, sqlalchemy model class SchoolMembership will be rendered to
	# schoolmembership-attributes.rst and schoolmembership-relations.rst
	# The script has some inline unit tests: pytest doc/dev/sqlalchemy_to_rst.py

	python3 doc/dev/sqlalchemy_to_rst.py Group User School Role GroupType SchoolMembership doc/dev/architecture
	python3 doc/dev/render_er_diagram.py doc/dev/architecture/er.mmd

.get-target:
ifeq ($(TARGET),)
	$(eval TARGET := $(shell read -p "Enter value for TARGET: " val; echo $$val))
endif

.get-alembic-message:
ifeq ($(ALEMBIC_MESSAGE),)
	$(eval ALEMBIC_MESSAGE := $(shell read -p "Enter value for ALEMBIC_MESSAGE: " val; echo $$val))
endif

.running-dev-server:
	@if ! $$(docker compose ls --filter name=kelvin-dev | grep --quiet running); then \
		echo "Error: kelvin-dev not running. Run 'make dev-server' first."; \
		exit 1; \
	fi

fetch-vm-data: .get-target ## Fetches necessary information from a UCS host, to use its UDM REST API for a local Kelvin instance
	mkdir -p $(VM_CONF_DIR)
	mkdir -p $(VM_CONF_DIR)/kelvin-hooks
	mkdir -p $(VM_CONF_DIR)/school-lib-hooks
	echo "dev" > $(VM_CONF_DIR)/tokens.secret
	echo "univention" > $(VM_CONF_DIR)/postgresql-kelvin.secret
	scp $(TARGET):/etc/machine.secret $(VM_CONF_DIR)/
	scp $(TARGET):/etc/ldap.secret $(VM_CONF_DIR)/
	scp $(TARGET):/etc/ssl/certs/ca-certificates.crt $(VM_CONF_DIR)/
	scp $(TARGET):/etc/univention/base.conf $(VM_CONF_DIR)/
	scp $(TARGET):/usr/share/ucs-school-import/configs/ucs-school-testuser-import.json $(VM_CONF_DIR)/user_import.json
	cp kelvin-api/usr/share/ucs-school-import/configs/kelvin_defaults.json $(VM_CONF_DIR)/kelvin_defaults.json
	if ssh $(TARGET) "test -f /var/lib/ucs-school-import/configs/kelvin.json"; then \
		scp $(TARGET):/var/lib/ucs-school-import/configs/kelvin.json $(VM_CONF_DIR)/kelvin.json; \
	else \
		echo "{}" > $(VM_CONF_DIR)/kelvin.json; \
	fi
	python3 -c "import json,sys; f,h=sys.argv[1],sys.argv[2]; d=json.load(open(f)); d['hooks_dir_pyhook']=h; open(f,'w').write(json.dumps(d,indent=2))" \
		$(VM_CONF_DIR)/kelvin.json $(VM_CONF_DIR)/kelvin-hooks
	echo "{}" > $(VM_CONF_DIR)/mapped_udm_properties.json
	echo "LDAP_MASTER=$$(ssh $(TARGET) ucr get ldap/master)" > $(VM_CONF_DIR)/env
	echo "LDAP_BASE=$$(ssh $(TARGET) ucr get ldap/base)" >> $(VM_CONF_DIR)/env
	echo "LDAP_MASTER_PORT=$$(ssh $(TARGET) ucr get ldap/master/port)" >> $(VM_CONF_DIR)/env
	echo "LDAP_HOSTDN=$$(ssh $(TARGET) ucr get ldap/hostdn)" >> $(VM_CONF_DIR)/env
	echo "LDAP_SERVER_NAME=$$(ssh $(TARGET) ucr get ldap/server/name)" >> $(VM_CONF_DIR)/env
	echo "LDAP_SERVER_PORT=$$(ssh $(TARGET) ucr get ldap/server/port)" >> $(VM_CONF_DIR)/env
	echo "HOSTNAME=$$(ssh $(TARGET) ucr get hostname)" >> $(VM_CONF_DIR)/env
	echo "DOCKER_HOST_NAME=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "TARGET=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_URI=postgresql://postgres:5432/ucsschool-kelvin-rest-api?sslmode=disable" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_USERNAME=ucsschool-kelvin-rest-api" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_PASSWORD_FILE=/etc/ucsschool/kelvin/postgresql-kelvin.secret" >> $(VM_CONF_DIR)/env
	@echo ""
	@echo "----------------------------------------------------------------------"
	@echo "To resolve UCS hostnames locally, add this line to /etc/hosts:"
	@echo ""
	@LDAP_SERVER=$$(ssh $(TARGET) ucr get ldap/server/name); \
	echo "  $(TARGET)  $$LDAP_SERVER $$(echo $$LDAP_SERVER | cut -d. -f1)"
	@echo ""
	@echo "  sudo sh -c 'echo \"$(TARGET)  $$(ssh $(TARGET) ucr get ldap/server/name)\" >> /etc/hosts'"
	@echo "----------------------------------------------------------------------"

build-docker-image:  ## Builds the Kelvin docker image
	@docker build --network host -t ucsschool-kelvin-rest-api:dev -f docker/Dockerfile .

dev-server: build-docker-image ## Start local Kelvin development server
	@echo "Starting development server..."
	@echo "Access via http://127.0.0.1:8911/ucsschool/kelvin/"
	@if [ ! -f $(VM_CONF_DIR)/env ]; then \
		echo "Error: $(VM_CONF_DIR)/env not found. Run 'make fetch-vm-data TARGET=hostname' first."; \
		exit 1; \
	fi
	@set -a && source $(VM_CONF_DIR)/env && set +a && \
	trap 'docker compose -f dev/docker-compose.yaml down' EXIT && \
		docker compose -f dev/docker-compose.yaml up --watch

local-server: ## Run kelvin locally
	@if [ ! -f $(VM_CONF_DIR)/env ]; then \
		echo "Error: $(VM_CONF_DIR)/env not found. Run 'make fetch-vm-data TARGET=hostname' first."; \
		exit 1; \
	fi
	# TBD: Should we connect to the remote database?
	docker run --detach --rm --name kelvin-local-postgres --publish 5432:5432 \
		--env POSTGRES_USER=ucsschool-kelvin-rest-api \
		--env POSTGRES_PASSWORD=univention \
		postgres:15-bookworm
	uv run --env-file dev/_vm_config/env --env-file .env.local-tests gunicorn --reload --pid dev/gunicorn.pid --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8911 ucsschool.kelvin.main:app
	docker stop kelvin-local-postgres

local-tests: ## Run test suite locally against a remote UCS server (requires fetch-vm-data first)
	@if [ ! -f $(VM_CONF_DIR)/env ]; then \
		echo "Error: $(VM_CONF_DIR)/env not found. Run 'make fetch-vm-data TARGET=hostname' first."; \
		exit 1; \
	fi
	uv run --env-file dev/_vm_config/env --env-file .env.local-tests pytest -l -vv --asyncio-mode=auto \
		ucs-school-lib/modules/ucsschool/lib/tests/ \
		kelvin-api/tests/

alembic-migration: .running-dev-server .get-alembic-message ## Creates a new alembic revison from kelvin-dev
	uv run --env-file .env.alembic alembic revision --autogenerate -m "$(ALEMBIC_MESSAGE)"
