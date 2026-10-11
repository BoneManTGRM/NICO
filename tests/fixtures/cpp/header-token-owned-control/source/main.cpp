#include "macro_only.h"
#include "generated.h"
#if MODE == 1
#include "active_a.h"
#else
#include "active_b.h"
#endif
int header_control() { return active_value() + generated_value() + MACRO_VALUE; }
