/* Pentox frame-timestamp ring — shared by our GL shim and Vulkan layer.
 *
 * Written by hand for Pentox; no external HUD/codebase is copied.
 *
 * Shared memory file layout (little endian):
 *   header 64 B : magic u64 | entry_size u32 | capacity u32 | write_index u64 | pad
 *   entries     : capacity * 16 B of { uint64 t_ns; uint32 pid; uint32 api; }
 */
#ifndef PENTOXY_RING_H
#define PENTOXY_RING_H

#include <stdint.h>
#include <string.h>
#include <time.h>

#define PENTOX_MAGIC      0x50454E5458583031ULL /* "PENTXX01" */
#define PENTOX_ENTRY_SIZE 16u
#define PENTOX_CAPACITY   4096u
#define PENTOX_HEADER     64u
#define PENTOX_API_VULKAN 1u
#define PENTOX_API_OPENGL 2u

static inline uint64_t pentox_now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

#endif /* PENTOXY_RING_H */
