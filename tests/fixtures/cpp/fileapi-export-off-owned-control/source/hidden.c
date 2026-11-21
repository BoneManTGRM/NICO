#include "active.h"
#include "config.h"
#if TARGET_SENTINEL != 17 || SOURCE_SENTINEL != 19 || CONFIG_SENTINEL != 23 || ACTIVE_SENTINEL != 29
#error Exact owned compile settings were not preserved
#endif
int owned_hidden(void) { return TARGET_SENTINEL + SOURCE_SENTINEL + CONFIG_SENTINEL + ACTIVE_SENTINEL; }
