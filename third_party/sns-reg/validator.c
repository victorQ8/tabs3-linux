// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * Qualcomm Sensor Registry Map Validator
 *
 * Validates groups defined in the group map in map.c
 *
 * Copyright (C) 2023 Yassine Oudjana
 */

#include <stdbool.h>
#include <stdio.h>

#include "map.h"

int sizeof_group(int id)
{
	const struct group *group = group_by_id(id);
	const struct map_entry *entry;
	struct key key;
	int index = 0;
	int size = 0;

	size = 0;
	while ((key = group->keys[index++]).len)
		size += key.len;

	return size;
}

bool group_is_valid(int id)
{
	const struct map_entry *entry;
	int size;

	entry = group_map_entry_by_id(id);
	if (!entry) {
		fprintf(stderr, "Group %d unmapped on binary registry map\n", id);
		return false;
	}

	size = sizeof_group(id);

	if (size != entry->size)
	{
		fprintf(stderr, "Group %d size mismatch\n", id);
		return false;
	}

	return true;
}

int main()
{
	const struct group *group;
	int group_index = 0;
	int errors = 0;

	while ((group = &groups[group_index++])->id != -1)
		if (!group_is_valid(group->id))
			++errors;

	printf("%d error%s in %d groups\n", errors, errors != 1 ? "s" : "", group_index);

	return errors;
}
