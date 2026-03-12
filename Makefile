.PHONY: help fetch-vm-data build-docker-image dev-server
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

fetch-vm-data:  ## Fetches necessary information from a UCS host, to use its UDM REST API for a local Kelvin instance
	mkdir -p $(VM_CONF_DIR)
	echo "dev" > $(VM_CONF_DIR)/tokens.secret
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
	echo "HOSTNAME=$$(ssh $(TARGET) ucr get hostname)" >> $(VM_CONF_DIR)/env
	echo "DOCKER_HOST_NAME=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "TARGET=$(TARGET)" >> $(VM_CONF_DIR)/env
	echo "KELVIN_HOST=127.0.0.1" >> $(VM_CONF_DIR)/env
	echo "KELVIN_PORT=8911" >> $(VM_CONF_DIR)/env

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
