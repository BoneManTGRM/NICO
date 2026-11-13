// Owned malformed alias control: missing defining type-id.
typedef int* Alias;
namespace Broken { using Alias = ; }
