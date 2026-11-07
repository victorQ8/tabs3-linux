"""Read-only battery policy labels shared by every dashboard theme."""
import re


def charge_behaviour(text):
    # power_supply exposes all choices; only the bracketed choice is active.
    match = re.search(r'\[([a-z-]+)\]', text or '')
    return match.group(1) if match else None


def keeper_target(config):
    values = {'TABS3_BATTERY_LOW': 65, 'TABS3_BATTERY_HIGH': 80}
    for line in config.splitlines():
        match = re.fullmatch(r'\s*(TABS3_BATTERY_(?:LOW|HIGH))\s*=\s*[\"\']?(\d+)[\"\']?\s*(?:#.*)?', line)
        if match:
            values[match[1]] = int(match[2])
    low, high = values['TABS3_BATTERY_LOW'], values['TABS3_BATTERY_HIGH']
    return high if 20 <= low <= high <= 100 else 80


def battery_status(battery):
    if battery.get('charger') == 1:
        behaviour = battery.get('charge_behaviour')
        if behaviour == 'force-discharge':
            target = battery.get('keeper_target', 80)
            return f'Reducing to {target}%'
        if behaviour == 'inhibit-charge':
            return 'Battery resting'
    return battery.get('status') or 'Unknown'


def power_source(battery):
    if battery.get('charger') is None:
        return 'Power unknown'
    return 'External power connected' if battery['charger'] else 'On battery'
