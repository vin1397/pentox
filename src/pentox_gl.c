/* Pentox OpenGL/OpenGL ES frame capture — LD_PRELOAD shim, written from
 * scratch. Intercepts eglSwapBuffers and glXSwapBuffers, timestamps each
 * presented frame into our ring, then forwards to the real function.
 *
 * Environment:
 *   PENTOX_RING  path of the shared-memory ring file (required)
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "ring.h"

typedef struct {
    uint64_t magic;
    uint32_t entry_size;
    uint32_t capacity;
    uint64_t write_index;
    uint64_t pad;
} pentox_hdr;

static unsigned char *g_map = NULL;
static int g_fd = -1;

static void pentox_init(void) {
    const char *path = getenv("PENTOX_RING");
    if (!path) {
        /* ambient mode: ring named after our own pid */
        static char fallback[128];
        snprintf(fallback, sizeof fallback, "/tmp/pentox-run-%d.ring", (int)getpid());
        path = fallback;
    }
    if (g_map) return;
    g_fd = open(path, O_RDWR | O_CREAT, 0600);
    if (g_fd < 0) return;
    if (ftruncate(g_fd, PENTOX_HEADER + (off_t)PENTOX_CAPACITY * PENTOX_ENTRY_SIZE) != 0) {
        close(g_fd); g_fd = -1; return;
    }
    g_map = mmap(NULL, PENTOX_HEADER + (size_t)PENTOX_CAPACITY * PENTOX_ENTRY_SIZE,
                 PROT_READ | PROT_WRITE, MAP_SHARED, g_fd, 0);
    if (g_map == MAP_FAILED) { g_map = NULL; close(g_fd); g_fd = -1; return; }
    pentox_hdr *h = (pentox_hdr *)g_map;
    if (h->magic != PENTOX_MAGIC) {
        h->magic = PENTOX_MAGIC;
        h->entry_size = PENTOX_ENTRY_SIZE;
        h->capacity = PENTOX_CAPACITY;
        h->write_index = 0;
    }
}

static void pentox_push(uint32_t api) {
    if (!g_map) return;
    pentox_hdr *h = (pentox_hdr *)g_map;
    unsigned char *base = g_map + PENTOX_HEADER;
    uint64_t idx = __sync_fetch_and_add(&h->write_index, 1ull);
    unsigned char *slot = base + (idx % PENTOX_CAPACITY) * PENTOX_ENTRY_SIZE;
    uint64_t t = pentox_now_ns();
    uint32_t pid = (uint32_t)getpid();
    __atomic_store_n((uint64_t *)(slot + 0), t, __ATOMIC_RELAXED);
    __atomic_store_n((uint32_t *)(slot + 8), pid, __ATOMIC_RELAXED);
    __atomic_store_n((uint32_t *)(slot + 12), api, __ATOMIC_RELAXED);
}

/* ------------------------------ EGL ------------------------------ */
typedef void *EGLDisplay;
typedef void *EGLSurface;
typedef unsigned int EGLBoolean;

static EGLBoolean (*real_eglSwapBuffers)(EGLDisplay, EGLSurface) = NULL;

EGLBoolean eglSwapBuffers(EGLDisplay dpy, EGLSurface surf) {
    if (!real_eglSwapBuffers)
        real_eglSwapBuffers = (EGLBoolean (*)(EGLDisplay, EGLSurface))dlsym(RTLD_NEXT, "eglSwapBuffers");
    pentox_init();
    pentox_push(PENTOX_API_OPENGL);
    return real_eglSwapBuffers ? real_eglSwapBuffers(dpy, surf) : 0;
}

/* ------------------------------ GLX ------------------------------ */
typedef void *Display;
typedef void *GLXDrawable;

static void (*real_glXSwapBuffers)(Display, GLXDrawable) = NULL;

void glXSwapBuffers(Display dpy, GLXDrawable drawable) {
    if (!real_glXSwapBuffers)
        real_glXSwapBuffers = (void (*)(Display, GLXDrawable))dlsym(RTLD_NEXT, "glXSwapBuffers");
    pentox_init();
    pentox_push(PENTOX_API_OPENGL);
    if (real_glXSwapBuffers) real_glXSwapBuffers(dpy, drawable);
}
