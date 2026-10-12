PREFIX     ?= /usr
PRESETDIR  ?= $(PREFIX)/share/projectM/presets/m0rf30
CFLAGS     ?= -O2

.PHONY: all tools validate install clean milk2

all: tools

tools: tools/render

tools/render: tools/render.c
	$(CC) $(CFLAGS) -rdynamic -include string.h -o $@ $< -lprojectM-4 -lEGL -lGL -lm -ldl

validate: tools/render
	@fail=0; for p in presets/*.milk; do \
		echo "== $$p"; tools/validate.py "$$p" || fail=1; \
	done; exit $$fail

milk2:
	python3 tools/mkmilk2.py milk2/src/*/

install:
	install -d "$(DESTDIR)$(PRESETDIR)"
	install -m644 presets/*.milk "$(DESTDIR)$(PRESETDIR)/"
	install -m644 milk2/*.milk2 "$(DESTDIR)$(PRESETDIR)/"

clean:
	rm -rf tools/render renders
