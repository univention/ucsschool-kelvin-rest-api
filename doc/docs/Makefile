# SPDX-FileCopyrightText: 2021-2023 Univention GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only

# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SPHINXPROJ    = UCSschoolKelvinRESTAPI
SOURCEDIR     = .
BUILDDIR      = _build
DOCKER_REGISTRY := docker-registry.knut.univention.de
SPHINX_DOCKER_BASE = $(DOCKER_REGISTRY)/knut/sphinx-base:latest
DOCKER_USER_CMD := docker run --rm -v "$(PWD)/../..:/project" -w /project/doc/docs --network=host -u "$(USER_ID)"

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

livehtml-nodocker:
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

livehtml:
	$(DOCKER_USER_CMD) $(SPHINX_DOCKER_BASE) sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
