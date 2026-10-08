#pragma once
namespace N {
  using Pointer = int*;
  ::N::Pointer const explicit_pointer = nullptr;
  Pointer const relative_pointer = nullptr;
  int explicit_bug() { return *explicit_pointer; }
  int relative_bug() { return *relative_pointer; }
}
