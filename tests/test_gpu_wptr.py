"""Compile both versions of the actual WPTR functions; force the race in C.

This models locking/MMIO interleavings, not real GPU execution or IRQ timing.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

PATCH = Path(__file__).resolve().parents[1] / 'kernel/patches/0043-drm-msm-a5xx-serialize-ring-write-pointer-updates.patch'


def functions(after):
    prefixes = (' ', '+') if after else (' ', '-')
    source = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                       if line.startswith(prefixes) and not line.startswith(('+++', '---')))
    result = []
    for name in ('void a5xx_flush(', 'static inline void update_wptr('):
        start = source.index(name)
        opening = source.index('{', start)
        end, depth = opening + 1, 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        result.append(source[start:end])
    return '\n'.join(result)


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <pthread.h>
#include <sched.h>
struct msm_ringbuffer { pthread_mutex_t preempt_lock; uint32_t cur, next; };
struct a5xx_gpu { struct msm_ringbuffer *cur_ring; bool preempt; };
struct adreno_gpu { struct a5xx_gpu *a5xx; };
struct msm_gpu { struct adreno_gpu *adreno; };
#define to_adreno_gpu(gpu) ((gpu)->adreno)
#define to_a5xx_gpu(adreno) ((adreno)->a5xx)
#define get_wptr(ring) ((ring)->cur)
#define a5xx_in_preempt(gpu) ((gpu)->preempt)
#define REG_A5XX_CP_RB_WPTR 1
#define mb() atomic_thread_fence(memory_order_seq_cst)
static _Thread_local int held, role;
static atomic_int old_at_write, peer_attempting, peer_done;
static atomic_uint hardware_wptr;
static bool race;
static void lock(pthread_mutex_t *mutex) {
    if (race && role == 2) atomic_store(&peer_attempting, 1);
    assert(pthread_mutex_lock(mutex) == 0); held++;
}
static void unlock(pthread_mutex_t *mutex) {
    held--; assert(pthread_mutex_unlock(mutex) == 0);
}
#define spin_lock_irqsave(m, flags) do { (flags) = 0; lock(m); } while (0)
#define spin_unlock_irqrestore(m, flags) do { (void)(flags); unlock(m); } while (0)
static void update_shadow_rptr(struct msm_gpu *gpu, struct msm_ringbuffer *ring) {
    (void)gpu; (void)ring;
}
static void gpu_write(struct msm_gpu *gpu, int reg, uint32_t value) {
    (void)gpu; assert(reg == REG_A5XX_CP_RB_WPTR);
    if (race && role == 1) {
        atomic_store(&old_at_write, 1);
        while (!atomic_load(&peer_attempting)) sched_yield();
        /* The unfixed updater has released the lock: force the new submit
         * to finish its write before we write the stale value. With the fix,
         * the submit blocks on the held lock until this MMIO is finished. */
        if (!held) while (!atomic_load(&peer_done)) sched_yield();
    }
    atomic_store(&hardware_wptr, value);
}
'''

MAIN = r'''
static struct msm_ringbuffer ring = {PTHREAD_MUTEX_INITIALIZER, 0, 0};
static struct a5xx_gpu a5xx = {&ring, false};
static struct adreno_gpu adreno = {&a5xx};
static struct msm_gpu gpu = {&adreno};
static void *old_writer(void *unused) {
    (void)unused; role = 1; update_wptr(&gpu, &ring); return NULL;
}
static void *new_submit(void *unused) {
    (void)unused; role = 2;
    while (!atomic_load(&old_at_write)) sched_yield();
    a5xx_flush(&gpu, &ring, false);
    atomic_store(&peer_done, 1); return NULL;
}
int main(void) {
    const uint32_t values[][2] = {{100, 200}, {8190, 5}};
    for (unsigned i = 0; i < 2; i++) {
        pthread_t old, newer;
        ring.cur = values[i][0]; ring.next = values[i][1];
        hardware_wptr = ring.cur;
        old_at_write = peer_attempting = peer_done = 0;
        race = true;
        assert(!pthread_create(&old, NULL, old_writer, NULL));
        assert(!pthread_create(&newer, NULL, new_submit, NULL));
        assert(!pthread_join(old, NULL)); assert(!pthread_join(newer, NULL));
        assert(hardware_wptr == values[i][FIXED ? 1 : 0]);
    }
    race = false;
    hardware_wptr = 7;
    update_wptr(&gpu, NULL); assert(hardware_wptr == 7);
    a5xx.preempt = true; ring.next = 8;
    a5xx_flush(&gpu, &ring, true); assert(hardware_wptr == 7);
    a5xx.preempt = false; a5xx.cur_ring = NULL;
    a5xx_flush(&gpu, &ring, false); assert(hardware_wptr == 7);
    a5xx.cur_ring = &ring;
    a5xx_flush(&gpu, &ring, true); assert(hardware_wptr == 8);
    return 0;
}
'''


class WritePointerTests(unittest.TestCase):
    def test_old_race_and_fixed_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp) / 'race.c', Path(tmp) / 'race'
            for fixed in (False, True):
                with self.subTest(fixed=fixed):
                    source.write_text(HARNESS + functions(fixed) + MAIN)
                    subprocess.run(['cc', '-std=c11', '-pthread', '-Wall', '-Wextra',
                                    '-Werror', f'-DFIXED={int(fixed)}', str(source),
                                    '-o', str(binary)], check=True)
                    subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
