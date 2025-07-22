.PHONY: help format lint setup_devel_env
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

build-docker-image:  ## Builds the Kelvin docker image
	@docker build --network host -t ucsschool-kelvin-rest-api:dev -f docker/Dockerfile .

dev-server: build-docker-image ## Start local Kelvin development server
	@echo "Starting development server..."
	@echo "Access via http://127.0.0.1:8911/ucsschool/kelvin/v1/docs"
	@if [ ! -f $(VM_CONF_DIR)/env ]; then \
		echo "Error: $(VM_CONF_DIR)/env not found. Run 'make fetch-vm-data TARGET=hostname' first."; \
		exit 1; \
	fi
	@set -a && source $(VM_CONF_DIR)/env && set +a && \
	docker run --rm --network host -ti \
		-v "$$(pwd)/kelvin-api/:/kelvin/kelvin-api" \
		-v "$$(pwd)/$(VM_CONF_DIR)/machine.secret":/etc/machine.secret:ro \
		-v "$$(pwd)/$(VM_CONF_DIR)/ldap.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/cn_admin.secret:ro \
		-v "$$(pwd)/$(VM_CONF_DIR)/ca-certificates.crt":/etc/ssl/certs/ca-certificates.crt:ro \
		-v "$$(pwd)/$(VM_CONF_DIR)/tokens.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/tokens.secret:ro \
		-v "$$(pwd)/$(VM_CONF_DIR)/base.conf":/etc/univention/base.conf \
		-v "$$(pwd)/$(VM_CONF_DIR)/mapped_udm_properties.json":/etc/univention/ucsschool/kelvin/mapped_udm_properties.json \
		-v "$$(pwd)/custom_hooks/add_school_admins_to_admin_group.py":/var/lib/ucs-school-import/kelvin-hooks/add_school_admins_to_admin_group.py \
		--env-file $(VM_CONF_DIR)/env \
		--add-host="$$LDAP_MASTER:$$TARGET" \
		--hostname "$$HOSTNAME" \
		ucsschool-kelvin-rest-api:dev
