#pragma once
typedef int *Global;
using ChainA = Global;
using ChainB = ChainA;
struct Early {
  static int first() { Local p = nullptr; return *p; }
  using Local = ChainB;
};
namespace Nest {
  using Base = ChainB;
  namespace Inner { using Leaf = Base; int inner() { Leaf p = nullptr; return *p; } }
}
template<class T> using Ptr = T*;
int alias_template() { Ptr<int> p = nullptr; return *p; }
int after() { Global p = nullptr; return *p; }
