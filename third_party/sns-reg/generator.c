// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * Qualcomm Sensor Registry Generator
 *
 * Generates a plain-text registry with individual key-value pairs
 * from a binary sns.reg file.
 *
 * Copyright (C) 2023 Yassine Oudjana
 */

#include <argp.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "map.h"

struct arguments {
	char *filename;
};

static char args_doc[] = "FILE";
static char doc[] = "Generate plain-text sensor registry from sns.reg binary registry";

/* Addresses are stored here instead of key IDs. */
static struct key key_map[KEY_MAX] = { };

void generate_map()
{
	const struct group *group = NULL;
	const struct map_entry *entry;
	struct key key;
	int group_index = 0;
	int key_index;
	size_t size = 0;

	while ((group = &groups[group_index++])->id != -1) {
		size = 0;
		key_index = 0;

		entry = group_map_entry_by_id(group->id);
		if (!entry)
			continue;

		while ((key = group->keys[key_index++]).len) {
			if (key.id != -1)
				key_map[key.id].id = entry->addr + size;
				key_map[key.id].len = key.len;

			size += key.len;
		}
	}
}

void print_registry(int reg_fd)
{
	unsigned long value;
	int key;
	int ret;

	printf(
		"#\n"
		"# Qualcomm Sensor Registry\n"
		"# Generated from sns.reg by sns-reg-generator\n"
		"#\n"
		"# Each line contains a unique key-value pair\n"
		"#\n\n"
	);

	for (key = 0; key < KEY_MAX; key++) {
		if (!key_map[key].len)
			continue;

		ret = lseek(reg_fd, key_map[key].id, SEEK_SET);
		if (ret < 0) {
			fprintf(stderr, "Failed to seek to address of key %d: %s\n", key,
				strerror(errno));
			continue;
		}

		value = 0;
		ret = read(reg_fd, &value, key_map[key].len);
		if (ret < 0) {
			fprintf(stderr, "Failed to read from address of key %d: %s\n", key,
				strerror(errno));
			continue;
		}

		printf("%u\t%lu\n", key, value);
	}
}

static int parse_opt(int key, char *arg, struct argp_state *state)
{
	char **filename = state->input;

	switch (key)
	{
	case ARGP_KEY_NO_ARGS:
		argp_usage(state);
		break;
	case ARGP_KEY_ARG:
		*filename = arg;
		break;
	default:
		return ARGP_ERR_UNKNOWN;
	}

	return 0;
}

int main(int argc, char **argv)
{
	struct argp argp = { 0, parse_opt, args_doc, doc };
	char *filename;
	int fd;
	int ret;

	ret = argp_parse (&argp, argc, argv, 0, 0, &filename);
	if (ret < 0)
		return ret;

	fd = open(filename, O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "Failed to open binary registry: %s\n", strerror(errno));
		return errno;
	}

	generate_map();
	print_registry(fd);

	return 0;
}
