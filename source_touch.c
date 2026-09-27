/* Native source touch / materialization helpers.
 *
 * Purpose: force file-backed mmap pages to become actually accessible using
 * native code only.  No payload copy, no Python per-page loop, and every access
 * goes through a volatile load so it cannot be optimised away.
 *
 * Each function returns an accumulated sink value; callers keep it so the work
 * is observable.  None of these functions allocate or copy.
 */
#include <stddef.h>
#include <stdint.h>

/* One volatile load per page across [base, base+len). */
long st_touch_pages(const unsigned char *base, size_t len, size_t page)
{
    volatile unsigned char sink = 0;
    long acc = 0;
    size_t off;
    if (page == 0)
        return -1;
    for (off = 0; off < len; off += page) {
        sink = base[off];
        acc += (long)sink;
    }
    return acc;
}

/* One volatile load per cache line across [base, base+len). */
long st_touch_lines(const unsigned char *base, size_t len, size_t line)
{
    volatile unsigned char sink = 0;
    long acc = 0;
    size_t off;
    if (line == 0)
        return -1;
    for (off = 0; off < len; off += line) {
        sink = base[off];
        acc += (long)sink;
    }
    return acc;
}

/* Read every byte exactly once via volatile loads (native reduction, no copy).
 * CPU cost is intentionally measurable and separable from source service. */
long st_reduce_full(const unsigned char *base, size_t len)
{
    volatile unsigned char sink = 0;
    long acc = 0;
    size_t i;
    for (i = 0; i < len; i++) {
        sink = base[i];
        acc += (long)sink;
    }
    return acc;
}
