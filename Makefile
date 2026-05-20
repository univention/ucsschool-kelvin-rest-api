SHELL := /usr/bin/env bash
.PHONY: help fetch-vm-data build-docker-image dev-server update-architecture-docs
.DEFAULT_GOAL := help

VM_CONF_DIR := "dev/_vm_config"

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-35s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

update-architecture-docs: ## Updates entity tables and diagrams in the architecture documentation
	# This is a semi manual process: If sqlalchemy class names change, they need to
	# be changed here and included in the architecture.rst file.
	# For example, sqlalchemy model class SchoolMembership will be rendered to
	# schoolmembership-attributes.rst and schoolmembership-relations.rst
	# The script has some inline unit tests: pytest doc/dev/sqlalchemy_to_rst.py

	python3 doc/dev/sqlalchemy_to_rst.py Group User School Role SchoolMembership doc/dev/architecture
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

.env-configured:
	@if [ ! -f $(VM_CONF_DIR)/env ]; then \
		echo "Error: $(VM_CONF_DIR)/env not found. Run 'make fetch-vm-data TARGET=hostname' first."; \
		exit 1; \
	fi


fetch-vm-data: .get-target ## Fetches necessary information from a UCS host, to use its UDM REST API for a local Kelvin instance
	mkdir -p $(VM_CONF_DIR)
	mkdir -p $(VM_CONF_DIR)/provisioning
	echo "dev" > $(VM_CONF_DIR)/tokens.secret
	echo "univention" > $(VM_CONF_DIR)/postgresql-kelvin.secret
	scp $(TARGET):/etc/machine.secret $(VM_CONF_DIR)/
	scp $(TARGET):/etc/ldap.secret $(VM_CONF_DIR)/
	scp $(TARGET):/etc/ssl/certs/ca-certificates.crt $(VM_CONF_DIR)/
	scp $(TARGET):/etc/univention/base.conf $(VM_CONF_DIR)/
	scp $(TARGET):/usr/share/ucs-school-import/configs/ucs-school-testuser-import.json $(VM_CONF_DIR)/user_import.json
	echo "{}" > $(VM_CONF_DIR)/mapped_udm_properties.json
	echo "LDAP_MASTER=$$(ssh $(TARGET) ucr get ldap/master)" > $(VM_CONF_DIR)/env
	echo "LDAP_BASE=$$(ssh $(TARGET) ucr get ldap/base)" >> $(VM_CONF_DIR)/env
	echo "LDAP_MASTER_PORT=$$(ssh $(TARGET) ucr get ldap/master/port)" >> $(VM_CONF_DIR)/env
	echo "LDAP_HOSTDN=$$(ssh $(TARGET) ucr get ldap/hostdn)" >> $(VM_CONF_DIR)/env
	echo "LDAP_SERVER_NAME=$$(ssh $(TARGET) ucr get ldap/server/name)" >> $(VM_CONF_DIR)/env
	echo "LDAP_SERVER_PORT=$$(ssh $(TARGET) ucr get ldap/server/port)" >> $(VM_CONF_DIR)/env
	echo "LDAP_SERVER_TYPE=$$(ssh $(TARGET) ucr get ldap/server/type)" >> $(VM_CONF_DIR)/env
	echo "HOSTNAME=$$(ssh $(TARGET) ucr get hostname)" >> $(VM_CONF_DIR)/env
	echo "DOCKER_HOST_NAME=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "TARGET=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_URI=postgresql+psycopg://postgres:5432/ucsschool-kelvin-rest-api?sslmode=disable" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_USERNAME=ucsschool-kelvin-rest-api" >> $(VM_CONF_DIR)/env
	echo "UCSSCHOOL_KELVIN_DB_PASSWORD_FILE=/etc/ucsschool/kelvin/postgresql-kelvin.secret" >> $(VM_CONF_DIR)/env
	echo "REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt" >> $(VM_CONF_DIR)/env
	echo "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" >> $(VM_CONF_DIR)/env


build-docker-image:  ## Builds the Kelvin docker image
	@docker build --network host -t ucsschool-kelvin-rest-api:dev -f docker/Dockerfile .

dev-server: .env-configured build-docker-image setup-provisioning-subscription ## Start local Kelvin development server
	@echo "Starting development server..."
	@echo "Access via http://127.0.0.1:8911/ucsschool/kelvin/"
	@set -a && source $(VM_CONF_DIR)/env && set +a && \
	trap 'docker compose -f dev/docker-compose.yaml down' EXIT && \
		docker compose -f dev/docker-compose.yaml up --watch

alembic-migration: .running-dev-server .get-alembic-message ## Creates a new alembic revison from kelvin-dev
	uv run --env-file .env.alembic alembic revision --autogenerate -m "$(ALEMBIC_MESSAGE)"

setup-provisioning-subscription: .env-configured ## Create a provisioning subscription on TARGET (SUBSCRIPTION_NAME=kelvin-connector, FORCE=false)
	@set -a && source $(VM_CONF_DIR)/env && set +a && \
	echo "$$TARGET" && \
	{ cat appcenter/includes/setup-provisioning-subscription.sh; echo 'setup_provisioning_subscriptions'; } | \
		ssh $$TARGET "SUBSCRIPTION_NAME='$${SUBSCRIPTION_NAME:-kelvin-connector}' FORCE='$${FORCE:-false}' APP_PROVISIONING_CONFIG_FILE='/tmp/provisioning_config.json' bash -s" && \
	scp $$TARGET:/tmp/provisioning_config.json $(VM_CONF_DIR)/provisioning/provisioning_config.json
