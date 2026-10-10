#pragma once
typedef int* Alias;
namespace Model { struct Clock { static int now(); }; }
struct RecordBase { using Alias = Model::Clock; };
struct RecordMiddle : RecordBase {};
struct RecordLeaf : RecordMiddle {
    static int repeated() { return Alias::now() + Alias::now() + Alias::now(); }
};
struct RecordOutside {
    using Alias = Model::Clock;
    static int outside(bool flag);
};
int RecordOutside::outside(bool flag) {
    int value = Alias::now() + Alias::now();
    if (flag) {
        using Alias = int*;
        Alias p = nullptr;
        return *p;
    }
    return value + Alias::now() + Alias::now();
}
struct UnrelatedRecord {
    static int bug() { Alias p = nullptr; return *p; }
};
struct RecordOwnRhs {
    static bool clean() {
        using Alias = Alias*;
        Alias p = nullptr; Alias q = nullptr;
        return p == q;
    }
};
int record_cache_global_bug() { Alias p = nullptr; return *p; }
