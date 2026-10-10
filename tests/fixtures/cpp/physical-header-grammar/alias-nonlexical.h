#pragma once
typedef int* Alias;
namespace Model { struct Clock { static int now(); }; }
namespace N { using Alias = Model::Clock; }
namespace N { int reopened() { return Alias::now(); } }
struct Base { using Alias = Model::Clock; };
struct Derived : Base { static int inherited() { return Alias::now(); } };
struct Outside { using Alias = Model::Clock; static int method(); };
int Outside::method() { return Alias::now(); }
int outside_bug() { Alias p = nullptr; return *p; }
