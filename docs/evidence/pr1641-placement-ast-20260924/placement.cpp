// Owned regression fixture: global placement construction after destruction.
#include <new>
struct Resource { int value{}; };
void reset(Resource& resource) {
    resource.~Resource();
    ::new (&resource) Resource{};
}
