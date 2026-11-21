#pragma once
typedef int* Alias;
struct Shadow {
  using Alias = Alias;
  static int inner_bug() { Alias p = nullptr; return *p; }
};
int outside_bug() { Alias p = nullptr; return *p; }
