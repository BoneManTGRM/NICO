#pragma once
typedef int *Alias;
struct Shadow {
  using Alias = ::Alias;
  static int inside_global() { Alias p = nullptr; return *p; }
};
int after_global() { Alias p = nullptr; return *p; }
