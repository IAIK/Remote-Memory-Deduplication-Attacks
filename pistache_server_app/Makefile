LIBS ?= $(shell pkg-config --libs libpistache)
INCS ?= $(shell pkg-config --cflags libpistache)

all:
	@g++ -std=c++17 -O3 ${INCS} main.cpp ${LIBS} -o server

clean:
	@rm server
