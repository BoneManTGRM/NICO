#ifndef OWNED_STDINT_H
#define OWNED_STDINT_H
typedef unsigned int uint32_t;
inline int owned_bad_header() { int* pointer = nullptr; return *pointer; }
#endif
