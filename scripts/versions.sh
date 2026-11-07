# shellcheck shell=bash
# Sourced by the build scripts from the repository root. Package versions
# live only in config/device.json.
read -r TABS3_BASE_VERSION KERNEL_PACKAGE_VERSION DESKTOP_VERSION SENSORS_VERSION DASHBOARD_VERSION < <(python3 -c '
import json
d = json.load(open("config/device.json"))
print(d["project_version"], d["kernel_package_version"], d["desktop_version"], d["sensors_version"], d["dashboard_version"])')
export TABS3_BASE_VERSION KERNEL_PACKAGE_VERSION DESKTOP_VERSION SENSORS_VERSION DASHBOARD_VERSION
# Kernel source directory under work/, from config/sources.json.
KERNEL_DIR=$(python3 -c 'import json; print(json.load(open("config/sources.json"))["kernel"]["directory"])')
export KERNEL_DIR
