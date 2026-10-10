#pragma once
typedef long int __clock_t;
namespace clock_model { struct Clock { static long now(); }; }
struct Semaphore {
  using __clock_t = clock_model::Clock;
  static long now() { return __clock_t::now(); }
};
int genuine_bug() { int *p = nullptr; return *p; }
