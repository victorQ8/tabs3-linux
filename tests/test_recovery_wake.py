"""A wake gesture must never reach the menu as a button press."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RecoveryWakeTests(unittest.TestCase):
    def test_complete_wake_gesture_is_consumed_including_failed_wake(self):
        text = (ROOT / "recovery-ui/main.c").read_text()
        start = text.index("static void touch_read_cb(")
        end = text.index("\n}", start) + 2
        source = r'''
#include <assert.h>
#include <stdbool.h>
enum { LV_INDEV_STATE_RELEASED, LV_INDEV_STATE_PRESSED };
typedef struct { int unused; } lv_indev_t;
typedef struct { int state; } lv_indev_data_t;
static bool screen_on, consuming_wake_touch, wake_fails;
static int next_state;
static void touch_read_original(lv_indev_t *i, lv_indev_data_t *d) {
    (void)i; d->state = next_state;
}
static void set_screen(bool on) { if (!wake_fails) screen_on = on; }
''' + text[start:end] + r'''
int main(void) {
    lv_indev_t input = {0}; lv_indev_data_t data;
    next_state = LV_INDEV_STATE_PRESSED;
    touch_read_cb(&input, &data);
    assert(screen_on && data.state == LV_INDEV_STATE_RELEASED);
    touch_read_cb(&input, &data);
    assert(data.state == LV_INDEV_STATE_RELEASED);
    next_state = LV_INDEV_STATE_RELEASED;
    touch_read_cb(&input, &data);
    assert(!consuming_wake_touch && data.state == LV_INDEV_STATE_RELEASED);
    next_state = LV_INDEV_STATE_PRESSED;
    touch_read_cb(&input, &data);
    assert(data.state == LV_INDEV_STATE_PRESSED);
    screen_on = false; wake_fails = true;
    touch_read_cb(&input, &data);
    assert(!screen_on && data.state == LV_INDEV_STATE_RELEASED);
    touch_read_cb(&input, &data);
    assert(!screen_on && data.state == LV_INDEV_STATE_RELEASED);
    next_state = LV_INDEV_STATE_RELEASED;
    touch_read_cb(&input, &data);
    assert(!screen_on && !consuming_wake_touch);
    wake_fails = false; next_state = LV_INDEV_STATE_PRESSED;
    touch_read_cb(&input, &data);
    assert(screen_on && data.state == LV_INDEV_STATE_RELEASED);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            program = pathlib.Path(tmp) / "wake.c"
            binary = pathlib.Path(tmp) / "wake"
            program.write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(program), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
