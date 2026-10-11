#pragma once
typedef int* Alias;
namespace Model { struct Clock { static int now(); }; }
template<class T> struct Shadow {
  static int before() { return Alias::now(); }
  using Alias = T;
  static int after() { return Alias::now(); }
  static int global_bug() { ::Alias p = nullptr; return *p; }
};
int use() { return Shadow<Model::Clock>::before() + Shadow<Model::Clock>::after() + Shadow<Model::Clock>::global_bug(); }
int outside_bug() { Alias p = nullptr; return *p; }
