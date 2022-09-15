WITH_TSX ?= 0
CFLAGS ?= -Os -Wall -g -fno-strict-aliasing
LDFLAGS ?= -lpthread

CPPFLAGS += -DWITH_TSX=${WITH_TSX}

all: kernel-scan dump-page

kernel-scan: main.c ptedit_header.h
	@echo [CC] $@
	@gcc ${CPPFLAGS} ${CFLAGS} main.c ${LDFLAGS} -o kernel-scan

dump-page: dump-page.c ptedit_header.h
	@echo [CC] $@
	@gcc ${CPPFLAGS} ${CFLAGS} dump-page.c ${LDFLAGS} -o dump-page

clean:
	@rm -rf kernel-scan dump-page

dist:
	@tar cfv dist.tar \
		--transform 's,^,kernel-scan/,' \
		Makefile \
		cacheutils.h \
		main.c \
		ptedit_header.h
