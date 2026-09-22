CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -fPIC
VK_CFLAGS := $(shell pkg-config --cflags vulkan 2>/dev/null || echo -I/usr/include)
LIBS    := -ldl

all: src/libpentoxgl.so src/libpentoxvk.so

src/libpentoxgl.so: src/pentox_gl.c src/ring.h
	$(CC) $(CFLAGS) -shared -o $@ src/pentox_gl.c $(LIBS)

src/libpentoxvk.so: src/pentox_vk.c src/ring.h
	$(CC) $(CFLAGS) $(VK_CFLAGS) -shared -o $@ src/pentox_vk.c

clean:
	rm -f src/libpentoxgl.so src/libpentoxvk.so

.PHONY: all clean
