#include "active.h"
#include "config.h"
static_assert(MODE == EXPECTED_MODE);
static_assert(SOURCE_SENTINEL == EXPECTED_SOURCE);
static_assert(GENERATED_SENTINEL == 23);
int shared_value() { return MODE + active_value; }
