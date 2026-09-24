/*
 * native_canary.c — 2x2 execution/syscall matrix canaries.
 *
 *  FOUR instruments, two kinds:
 *
 *                    SAME PID          SEPARATE PID
 *  PURE USERSPACE    U_MAIN            U_CHILD      (no syscalls in steady state)
 *  TRIVIAL SYSCALL   S_MAIN            S_CHILD      (syscall(SYS_gettid) at low cadence)
 *
 *  Both kinds exist per process.  S_MAIN and S_CHILD issue the IDENTICAL syscall
 *  (same number, same cadence, same clock, same timestamp semantics) so that a
 *  difference between them can only mean PID/thread-group scope.
 *
 *  Contract for every canary thread:
 *    - no Python C-API, no PyGILState_Ensure, no callbacks
 *    - no I/O, no malloc/free, no logging, no locks shared with Python
 *    - cadence established with a vDSO CLOCK_MONOTONIC busy-wait (never sleep/futex)
 *    - records into caller-supplied preallocated anonymous memory
 *
 *  Layout per buffer: 128-byte nc_header, then records at offset 128.
 *    userspace record : int64 [ts_ns, seq]                     (16 bytes)
 *    syscall   record : int64 [intended_ns, enter_ns, exit_ns, retval]  (32 bytes)
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <stdint.h>
#include <string.h>
#include <sys/syscall.h>
#include <errno.h>
#ifndef FUTEX_WAIT_PRIVATE
#define FUTEX_WAIT_PRIVATE 128   /* FUTEX_WAIT(0) | FUTEX_PRIVATE_FLAG(128) */
#endif
#ifndef SYS_futex
#define SYS_futex 202            /* x86-64 */
#endif

#define NC_HDR_SIZE 128
#define NC_USER_REC 16
#define NC_SYS_REC  32
#define NC_FUTEX_REC 48

typedef struct {
    volatile int64_t stop;        /*  0 */
    volatile int64_t count;       /*  8 */
    volatile int64_t overflow;    /* 16 */
    volatile int64_t capacity;    /* 24 */
    volatile int64_t tid;         /* 32 */
    volatile int64_t pid;         /* 40 */
    volatile int64_t cadence_ns;  /* 48 */
    volatile int64_t started;     /* 56 */
    volatile int64_t pad[8];      /* 64..127 */
} nc_header;

typedef struct {
    pthread_t thread;
    nc_header *hdr;
    int64_t *recs;
    int running;
} nc_slot;

static nc_slot g_user;
static nc_slot g_sys;
static nc_slot g_futex;
static int32_t g_futex_word = 0;   /* never changed: timeout is the expected wake */

static int64_t nc_now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000000LL + (int64_t)ts.tv_nsec;
}

/* ---- U_*: pure userspace, no syscalls in the steady-state loop ---- */
static void *nc_user_loop(void *arg)
{
    nc_header *h = g_user.hdr;
    int64_t *r = g_user.recs;
    int64_t n = 0, cap;
    (void)arg;

    h->tid = (int64_t)syscall(SYS_gettid);
    h->pid = (int64_t)getpid();
    h->started = 1;
    cap = h->capacity;

    while (!h->stop) {
        int64_t now = nc_now();
        if (n < cap) {
            r[n * 2] = now;
            r[n * 2 + 1] = n;
            n++;
        } else {
            h->overflow = 1;
        }
        h->count = n;
        {
            int64_t target = now + h->cadence_ns;
            while (!h->stop && nc_now() < target) {
                /* spin */
            }
        }
    }
    return 0;
}

/* ---- S_*: one real syscall per tick, identical in both processes ---- */
static void *nc_sys_loop(void *arg)
{
    nc_header *h = g_sys.hdr;
    int64_t *r = g_sys.recs;
    int64_t n = 0, cap, next;
    (void)arg;

    h->tid = (int64_t)syscall(SYS_gettid);
    h->pid = (int64_t)getpid();
    h->started = 1;
    cap = h->capacity;
    next = nc_now();

    while (!h->stop) {
        int64_t intended = next;
        int64_t enter = nc_now();
        long long rv = (long long)syscall(SYS_gettid);
        int64_t exit_ns = nc_now();
        if (n < cap) {
            r[n * 4] = intended;
            r[n * 4 + 1] = enter;
            r[n * 4 + 2] = exit_ns;
            r[n * 4 + 3] = (int64_t)rv;
            n++;
        } else {
            h->overflow = 1;
        }
        h->count = n;
        next = intended + h->cadence_ns;
        while (!h->stop && nc_now() < next) {
            /* spin */
        }
    }
    return 0;
}

/* ---- B_*: deliberately bounded blocking futex, woken by TIMEOUT only ----
 * The futex word is never modified, so the expected return is ETIMEDOUT after
 * h->cadence_ns.  Nothing else wakes this waiter, which isolates
 * park -> timer fires -> resume from any storage/application wakeup.
 */
static void *nc_futex_loop(void *arg)
{
    nc_header *h = g_futex.hdr;
    int64_t *r = g_futex.recs;
    int64_t n = 0, cap, next;
    (void)arg;

    h->tid = (int64_t)syscall(SYS_gettid);
    h->pid = (int64_t)getpid();
    h->started = 1;
    cap = h->capacity;
    next = nc_now();

    while (!h->stop) {
        int64_t intended = next;
        int64_t enter = nc_now();
        struct timespec ts;
        long rv;
        int err;
        ts.tv_sec = 0;
        ts.tv_nsec = (long)h->cadence_ns;
        errno = 0;
        rv = syscall(SYS_futex, &g_futex_word, FUTEX_WAIT_PRIVATE,
                     (int32_t)0, &ts, (void *)0, (int32_t)0);
        err = errno;
        {
            int64_t exit_ns = nc_now();
            if (n < cap) {
                r[n * 6] = intended;
                r[n * 6 + 1] = enter;
                r[n * 6 + 2] = exit_ns;
                r[n * 6 + 3] = (int64_t)rv;
                r[n * 6 + 4] = (int64_t)err;
                r[n * 6 + 5] = h->cadence_ns;
                n++;
            } else {
                h->overflow = 1;
            }
            h->count = n;
        }
        next = intended + h->cadence_ns;
    }
    return 0;
}

static long long nc_start_slot(nc_slot *s, void *base, long long capacity,
                               long long cadence_ns,
                               void *(*fn)(void *))
{
    if (s->running) {
        return -1;
    }
    s->hdr = (nc_header *)base;
    memset((void *)s->hdr, 0, NC_HDR_SIZE);
    s->hdr->capacity = capacity;
    s->hdr->cadence_ns = cadence_ns;
    s->recs = (int64_t *)((char *)base + NC_HDR_SIZE);
    if (pthread_create(&s->thread, 0, fn, 0) != 0) {
        return -2;
    }
    s->running = 1;
    return 0;
}

static long long nc_stop_slot(nc_slot *s)
{
    long long n;
    if (!s->running) {
        return -1;
    }
    s->hdr->stop = 1;
    pthread_join(s->thread, 0);
    s->running = 0;
    n = s->hdr->count;
    return n;
}

long long nc_start(void *base, long long capacity, long long cadence_ns)
{
    return nc_start_slot(&g_user, base, capacity, cadence_ns, nc_user_loop);
}
long long nc_stop(void) { return nc_stop_slot(&g_user); }

long long nc_start_syscall(void *base, long long capacity, long long cadence_ns)
{
    return nc_start_slot(&g_sys, base, capacity, cadence_ns, nc_sys_loop);
}
long long nc_stop_syscall(void) { return nc_stop_slot(&g_sys); }

long long nc_start_futex(void *base, long long capacity, long long timeout_ns)
{
    return nc_start_slot(&g_futex, base, capacity, timeout_ns, nc_futex_loop);
}
long long nc_stop_futex(void) { return nc_stop_slot(&g_futex); }

long long nc_count(void)         { return g_user.hdr ? g_user.hdr->count : -1; }
long long nc_overflow(void)      { return g_user.hdr ? g_user.hdr->overflow : -1; }
long long nc_tid(void)           { return g_user.hdr ? g_user.hdr->tid : -1; }
long long nc_pid(void)           { return g_user.hdr ? g_user.hdr->pid : -1; }
long long nc_started(void)       { return g_user.hdr ? g_user.hdr->started : -1; }
long long nc_count_syscall(void) { return g_sys.hdr ? g_sys.hdr->count : -1; }
long long nc_tid_syscall(void)   { return g_sys.hdr ? g_sys.hdr->tid : -1; }
long long nc_pid_syscall(void)   { return g_sys.hdr ? g_sys.hdr->pid : -1; }

long long nc_self_tid(void) { return (long long)syscall(SYS_gettid); }
long long nc_self_pid(void) { return (long long)getpid(); }
long long nc_syscall_number(void) { return (long long)SYS_gettid; }

/* ---- timing-source and syscall-path validation -------------------------- */

double nc_calibrate_monotonic_ns(long long iters)
{
    struct timespec a, b;
    volatile int64_t sink = 0;
    long long i;
    if (iters < 1) {
        return -1.0;
    }
    clock_gettime(CLOCK_MONOTONIC, &a);
    for (i = 0; i < iters; i++) {
        struct timespec t;
        clock_gettime(CLOCK_MONOTONIC, &t);
        sink += (int64_t)t.tv_nsec;
    }
    clock_gettime(CLOCK_MONOTONIC, &b);
    (void)sink;
    {
        int64_t d = ((int64_t)b.tv_sec - (int64_t)a.tv_sec) * 1000000000LL
                  + ((int64_t)b.tv_nsec - (int64_t)a.tv_nsec);
        return (double)d / (double)iters;
    }
}

/* the exact syscall the S_* canaries issue, so calibration matches the canary */
double nc_calibrate_syscall_ns(long long iters)
{
    struct timespec a, b;
    volatile int64_t sink = 0;
    long long i;
    if (iters < 1) {
        return -1.0;
    }
    clock_gettime(CLOCK_MONOTONIC, &a);
    for (i = 0; i < iters; i++) {
        sink += (int64_t)syscall(SYS_gettid);
    }
    clock_gettime(CLOCK_MONOTONIC, &b);
    (void)sink;
    {
        int64_t d = ((int64_t)b.tv_sec - (int64_t)a.tv_sec) * 1000000000LL
                  + ((int64_t)b.tv_nsec - (int64_t)a.tv_nsec);
        return (double)d / (double)iters;
    }
}
