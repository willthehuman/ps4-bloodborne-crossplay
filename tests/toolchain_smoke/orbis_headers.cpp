// Toolchain smoke test — Task 3.4
// Purpose: prove the OpenOrbis PS4 target can compile C++ standard headers that
// CI failed on (atomic, array, cassert, cerrno) before attempting the full plugin build.
// Compile-only (no link):  see scripts/build-plugin.sh
#include <array>
#include <atomic>
#include <cassert>
#include <cerrno>

static_assert(sizeof(void*) == 8, "PS4 target must be 64-bit");

int orbis_headers_smoke() {
    std::array<int, 4> a{{1, 2, 3, 4}};
    std::atomic<int> x{0};
    x.fetch_add(a[0]);
    assert(x.load() == 1);
    return x.load() + errno;
}
