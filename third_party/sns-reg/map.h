/* SPDX-License-Identifier: GPL-3.0-or-later */

#pragma once

#define KEY_MAX			7000

#define GROUP_KEY_NUM_MAX	0x100

struct key {
	short id;
	unsigned char len;
};

struct group {
	short id;
	struct key keys[GROUP_KEY_NUM_MAX];
};

struct map_entry {
	unsigned short id;
	unsigned short addr;
	size_t size;
};

extern const struct group groups[];

const struct group *group_by_id(short id);
const struct map_entry *group_map_entry_by_id(short id);
