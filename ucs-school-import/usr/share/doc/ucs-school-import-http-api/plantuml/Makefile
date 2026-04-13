#!/usr/bin/make -f

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

# Downloaded from http://plantuml.com/
# Direct download URL http://sourceforge.net/projects/plantuml/files/plantuml.jar/download

FORMATS := png svg
INPUT := import-pyhooks.md

all: $(foreach i,$(INPUT),$(foreach f,$(FORMATS), $(addsuffix .$f,$(basename $i))))

%.png: %.md
	DISPLAY= java -jar plantuml.jar -nbthread auto -failfast2 -tpng $<

%.svg: %.md
	DISPLAY= java -jar plantuml.jar -nbthread auto -failfast2 -tsvg $<

clean:
	rm -f *.png *.svg
