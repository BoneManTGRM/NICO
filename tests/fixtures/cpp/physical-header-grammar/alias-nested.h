#pragma once
typedef int* Alias;
namespace Model { struct Clock { static int now(); }; }
template<class T> struct Shadow {
  using Alias = T;
  static int nested() { { using Alias = T; Alias::now(); } return Alias::now(); }
  static int after() { return Alias::now(); }
  static int global_bug() { ::Alias p = nullptr; return *p; }
};
int use() { return Shadow<Model::Clock>::nested() + Shadow<Model::Clock>::after() + Shadow<Model::Clock>::global_bug(); }
int outside_bug() { Alias p = nullptr; return *p; }
