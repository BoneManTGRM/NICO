#pragma once
typedef int* Alias;
namespace Model { struct Clock { static int now(); }; }
namespace Left { namespace Shared {
using Alias = Model::Clock;
int first() { return Alias::now(); }
} }
namespace Right { namespace Shared {
using Alias = int*;
int sibling_bug() { Alias p = nullptr; return *p; }
} }
namespace Left { namespace Shared {
using Alias = Model::Clock;
int reopened() { return Alias::now(); }
} }
int separate_blocks() {
    { using Alias = Model::Clock; Alias::now(); }
    { using Alias = int*; Alias p = nullptr; return *p; }
}
struct Member {
    static int local() { using Alias = Model::Clock; return Alias::now(); }
};
int global_bug() { Alias p = nullptr; return *p; }
