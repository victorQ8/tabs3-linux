"""Exercise shared-buffer lifetime policy without a GPU or device ioctls."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'kernel/patches/0014-drm-msm-keep-shared-global-vm-mappings-until-the-last-user.patch'


def patched_function(name):
    text = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                     if line.startswith((' ', '+')) and not line.startswith('+++'))
    start = text.index('void ' + name + '(')
    opening = text.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class GpuCleanupTests(unittest.TestCase):
    def test_shared_references_and_final_cleanup_with_and_without_kms(self):
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
struct drm_gpuvm { int id; };
struct gpu { struct drm_gpuvm *vm; };
struct kms { struct drm_gpuvm *vm; };
struct msm_drm_private { struct gpu *gpu; struct kms *kms; };
struct drm_device { struct msm_drm_private *dev_private; };
struct bo { int vma_ref; };
struct drm_gem_object { struct drm_device *dev; struct bo *bo; void *resv; };
struct drm_exec { int unused; };
#define to_msm_bo(obj) ((obj)->bo)
#define atomic_inc(p) (++*(p))
#define atomic_dec_return(p) (--*(p))
#define DMA_RESV_USAGE_BOOKKEEP 4
#define MAX_SCHEDULE_TIMEOUT 123456
static struct drm_gpuvm gpu_vm = {1}, kms_vm = {2};
static unsigned waits, gpu_cleanup, kms_cleanup;
static bool locked;
static void dma_resv_wait_timeout(void *resv, int usage, bool interruptible, long timeout) {
    assert(resv && usage == DMA_RESV_USAGE_BOOKKEEP && !interruptible);
    assert(timeout == MAX_SCHEDULE_TIMEOUT && !locked);
    waits++;
}
static void msm_gem_lock_vm_and_obj(struct drm_exec *exec, struct drm_gem_object *obj,
                                   struct drm_gpuvm *vm) {
    (void)exec;
    assert(obj && vm && !locked);
    locked = true;
}
static void put_iova_spaces(struct drm_gem_object *obj, struct drm_gpuvm *vm,
                            bool close, const char *reason) {
    assert(locked && close && reason && obj->bo->vma_ref == 0);
    if (vm == &gpu_vm) {
        assert(waits == gpu_cleanup + 1);
        gpu_cleanup++;
    } else {
        assert(vm == &kms_vm);
        kms_cleanup++;
    }
}
static void drm_exec_fini(struct drm_exec *exec) {
    (void)exec;
    assert(locked);
    locked = false;
}
'''
        source += patched_function('msm_gem_vma_get') + '\n'
        source += patched_function('msm_gem_vma_put') + '\n'
        source += r'''
static void reset_counts(void) { waits = gpu_cleanup = kms_cleanup = 0; locked = false; }
int main(void) {
    struct gpu gpu = {&gpu_vm};
    struct kms kms = {&kms_vm};
    struct msm_drm_private priv = {&gpu, &kms};
    struct drm_device dev = {&priv};
    struct bo bo = {0};
    struct drm_gem_object obj = {&dev, &bo, &bo};
    /* Two handles, an exported dma-buf and a framebuffer all keep it live. */
    for (int i = 0; i < 4; i++) msm_gem_vma_get(&obj);
    for (int i = 0; i < 3; i++) {
        msm_gem_vma_put(&obj);
        assert(!waits && !gpu_cleanup && !kms_cleanup);
    }
    msm_gem_vma_put(&obj);
    assert(waits == 1 && gpu_cleanup == 1 && bo.vma_ref == 0 && !locked);
#ifdef CONFIG_DRM_MSM_KMS
    assert(kms_cleanup == 1);
#else
    assert(kms_cleanup == 0);
#endif
    /* A render-only device must still release the global GPU mapping. */
    reset_counts(); priv.kms = NULL;
    msm_gem_vma_get(&obj); msm_gem_vma_put(&obj);
    assert(waits == 1 && gpu_cleanup == 1 && !kms_cleanup);
    /* Display-only operation must not dereference an unloaded GPU. */
    reset_counts(); priv.gpu = NULL; priv.kms = &kms;
    msm_gem_vma_get(&obj); msm_gem_vma_put(&obj);
    assert(!waits && !gpu_cleanup);
#ifdef CONFIG_DRM_MSM_KMS
    assert(kms_cleanup == 1);
#endif
    reset_counts(); priv.gpu = &gpu; gpu.vm = NULL;
    msm_gem_vma_get(&obj); msm_gem_vma_put(&obj);
    assert(!waits && !gpu_cleanup && !locked);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            program, binary = directory / 'cleanup.c', directory / 'cleanup'
            program.write_text(source)
            for kms in (False, True):
                with self.subTest(kms=kms):
                    flags = ['-DCONFIG_DRM_MSM_KMS=1'] if kms else []
                    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    *flags, str(program), '-o', str(binary)], check=True)
                    subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
