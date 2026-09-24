/*
 * Pentox Vulkan layer — written from scratch for this project.
 *
 * Minimal layer that hooks vkQueuePresentKHR to timestamp every presented
 * frame into the shared Pentox ring. Uses only the official loader
 * structures from <vulkan/vk_layer.h>.
 *
 * Build:  make (see Makefile)  ->  libpentoxvk.so + Pentox_layer.json
 * Enable: VK_LAYER_PATH=<dir> VK_INSTANCE_LAYERS=VK_LAYER_PENTOX_capture
 * Env:    PENTOX_RING=<path to shared ring file>
 */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <vulkan/vulkan.h>
#include <vulkan/vk_layer.h>

#include "ring.h"

static PFN_vkGetInstanceProcAddr g_next_gipa    = NULL;
static PFN_vkGetDeviceProcAddr   g_next_gdpa    = NULL;
static PFN_vkQueuePresentKHR     g_next_present = NULL;

/* ------------------------------- ring ---------------------------------- */

static void pentox_push_vk(void) {
    const char *path = getenv("PENTOX_RING");
    if (!path) {
        /* implicit-layer mode: no env needed — ring named after our own pid */
        static char fallback[128];
        snprintf(fallback, sizeof fallback, "/tmp/pentox-run-%d.ring", (int)getpid());
        path = fallback;
    }
    static unsigned char *map = NULL;
    if (!map) {
        int fd = open(path, O_RDWR | O_CREAT, 0600);
        if (fd < 0) return;
        size_t len = PENTOX_HEADER + (size_t)PENTOX_CAPACITY * PENTOX_ENTRY_SIZE;
        if (ftruncate(fd, (off_t)len) != 0) { close(fd); return; }
        map = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (map == MAP_FAILED) { map = NULL; return; }
        uint64_t magic = 0;
        memcpy(&magic, map, 8);
        if (magic != PENTOX_MAGIC) {
            uint64_t m = PENTOX_MAGIC;
            uint32_t es = PENTOX_ENTRY_SIZE, cap = PENTOX_CAPACITY;
            uint64_t zero = 0;
            memcpy(map + 0,  &m,    8);
            memcpy(map + 8,  &es,   4);
            memcpy(map + 12, &cap,  4);
            memcpy(map + 16, &zero, 8);
        }
    }
    /* Same atomic fetch-and-add discipline as the GL shim (ring.h users):
     * games presenting from multiple threads take unique slots instead of
     * racing through a read-modify-write on the header index. */
    static uint64_t *hdr_idx = NULL;
    if (!hdr_idx) hdr_idx = (uint64_t *)(map + 16);
    uint64_t idx = __sync_fetch_and_add(hdr_idx, 1ull);
    unsigned char *slot = map + PENTOX_HEADER + (idx % PENTOX_CAPACITY) * PENTOX_ENTRY_SIZE;
    uint64_t t = pentox_now_ns();
    uint32_t pid = (uint32_t)getpid();
    uint32_t api = PENTOX_API_VULKAN;
    __atomic_store_n((uint64_t *)(slot + 0), t, __ATOMIC_RELAXED);
    __atomic_store_n((uint32_t *)(slot + 8), pid, __ATOMIC_RELAXED);
    __atomic_store_n((uint32_t *)(slot + 12), api, __ATOMIC_RELAXED);
}

/* ---------------------------- hooked call ------------------------------ */

VKAPI_ATTR VkResult VKAPI_CALL pentox_QueuePresentKHR(
        VkQueue queue, const VkPresentInfoKHR *pPresentInfo) {
    pentox_push_vk();
    return g_next_present(queue, pPresentInfo);
}

/* --------------------------- chain plumbing ---------------------------- */

VKAPI_ATTR VkResult VKAPI_CALL pentox_CreateInstance(
        const VkInstanceCreateInfo *pCreateInfo,
        const VkAllocationCallbacks *pAllocator, VkInstance *pInstance) {
    VkLayerInstanceCreateInfo *lici = (VkLayerInstanceCreateInfo *)pCreateInfo->pNext;
    while (lici && !(lici->sType == VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO &&
                     lici->function == VK_LAYER_LINK_INFO)) {
        lici = (VkLayerInstanceCreateInfo *)lici->pNext;
    }
    if (!lici) return VK_ERROR_INITIALIZATION_FAILED;
    g_next_gipa = lici->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    lici->u.pLayerInfo = lici->u.pLayerInfo->pNext;   /* hand link to next layer */

    PFN_vkCreateInstance create = (PFN_vkCreateInstance)g_next_gipa(VK_NULL_HANDLE, "vkCreateInstance");
    return create(pCreateInfo, pAllocator, pInstance);
}

VKAPI_ATTR VkResult VKAPI_CALL pentox_CreateDevice(
        VkPhysicalDevice gpu, const VkDeviceCreateInfo *pCreateInfo,
        const VkAllocationCallbacks *pAllocator, VkDevice *pDevice) {
    VkLayerDeviceCreateInfo *ldci = (VkLayerDeviceCreateInfo *)pCreateInfo->pNext;
    while (ldci && !(ldci->sType == VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO &&
                     ldci->function == VK_LAYER_LINK_INFO)) {
        ldci = (VkLayerDeviceCreateInfo *)ldci->pNext;
    }
    if (!ldci) return VK_ERROR_INITIALIZATION_FAILED;
    g_next_gipa = ldci->u.pLayerInfo->pfnNextGetInstanceProcAddr;
    g_next_gdpa = ldci->u.pLayerInfo->pfnNextGetDeviceProcAddr;
    ldci->u.pLayerInfo = ldci->u.pLayerInfo->pNext;

    /* per loader spec: creation entry points resolve through the next
     * layer's GetInstanceProcAddr, with a NULL instance */
    PFN_vkCreateDevice create = (PFN_vkCreateDevice)g_next_gipa(VK_NULL_HANDLE, "vkCreateDevice");
    if (!create) return VK_ERROR_INITIALIZATION_FAILED;
    VkResult r = create(gpu, pCreateInfo, pAllocator, pDevice);
    if (r == VK_SUCCESS) {
        g_next_present = (PFN_vkQueuePresentKHR)g_next_gdpa(*pDevice, "vkQueuePresentKHR");
    }
    return r;
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetDeviceProcAddr(VkDevice dev, const char *name) {
    if (name && strcmp(name, "vkQueuePresentKHR") == 0 && g_next_present)
        return (PFN_vkVoidFunction)pentox_QueuePresentKHR;
    if (g_next_gdpa)
        return g_next_gdpa(dev, name);
    return NULL;
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance inst, const char *name) {
    if (name && strcmp(name, "vkCreateInstance") == 0)
        return (PFN_vkVoidFunction)pentox_CreateInstance;
    if (name && strcmp(name, "vkCreateDevice") == 0)
        return (PFN_vkVoidFunction)pentox_CreateDevice;
    if (name && strcmp(name, "vkGetInstanceProcAddr") == 0)
        return (PFN_vkVoidFunction)vkGetInstanceProcAddr;
    if (name && strcmp(name, "vkGetDeviceProcAddr") == 0)
        return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    if (name && strcmp(name, "vkQueuePresentKHR") == 0 && g_next_present)
        return (PFN_vkVoidFunction)pentox_QueuePresentKHR;
    if (g_next_gipa)
        return g_next_gipa(inst, name);
    return NULL;
}
