#pragma once
typedef int *Alias;
namespace Model { struct Type { static int now(); }; }
// Unused matching declarations must not require a shadow snapshot.
struct UnusedAlias { typedef long Alias, Spare; };
// The declaration precedes the local typedef; the out-of-class conversion is
// the first matching operator after it and takes the separate mutation branch.
struct Conversion {
  operator int*() const;
  typedef int* Alias;
};
Conversion::operator Alias() const { return nullptr; }
struct Shadow {
  using Alias = Model::Type;
  // Freeze shadow decisions before qualified replacement changes the tokens,
  // then retain local complete-class lookup in the same replacement sweep.
  static int inside_global() { ::Alias p = nullptr; return *p + Alias::now(); }
  static int inside_local() { return Alias::now(); }
};
int after_global() { Alias p = nullptr; return *p; }
