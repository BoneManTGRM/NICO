#pragma once
typedef int *Alias;
namespace Model { struct Type { static int now(); }; }
struct Shadow {
  using Alias = Model::Type;
  static int inside_global() { ::Alias p = nullptr; return *p; }
  static int inside_local() { return Alias::now(); }
};
int after_global() { Alias p = nullptr; return *p; }
