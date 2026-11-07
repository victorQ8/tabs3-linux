// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * Qualcomm Sensor Registry (SNS_REG) Server
 * 
 * Copyright (C) 2023 Yassine Oudjana
 */

#include <errno.h>
#include <fcntl.h>
#include <libqrtr.h>
#include <linux/qrtr.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "map.h"
#include "qmi/sns_reg.h"

#define LINE_SIZE	0x100
#define BUFFER_LEN	0x1000

struct qmi_header {
	unsigned char type;
	unsigned short txn_id;
	unsigned short msg_id;
	unsigned short msg_len;
} __attribute__((packed));

static unsigned long registry[KEY_MAX] = { };

unsigned long *parse_registry(int fd)
{
	FILE *file = fdopen(fd, "r");
	char line[LINE_SIZE];
	unsigned short key;
	unsigned long value;

	if (!file) {
		fprintf(stderr, "Failed to open registry file: %s\n", strerror(errno));
		return NULL;
	}

	while (fgets(line, LINE_SIZE, file)) {
		if (sscanf(line, "%hu %lu", &key, &value) != 2)
			continue;

		registry[key] = value;
	}

	return registry;
}

int handle_group_request(int sock, struct qrtr_packet *packet, unsigned long *registry)
{
	unsigned int txn_id;
	struct sns_reg_group_req request;
	struct sns_reg_group_resp response = { };
	const struct group *group = NULL;
	size_t index = 0;
	size_t size = 0;
	struct key key;
	struct qrtr_packet out_packet;
	int ret;

	ret = qmi_decode_message(
				&request,
				&txn_id,
				packet,
				QMI_REQUEST,
				SNS_REG_GROUP_MSG_ID,
				sns_reg_group_req_ei
			);
	if (ret < 0) {
		fprintf(stderr, "Failed to decode request\n");
		return ret;
	}

	group = group_by_id(request.id);

	printf("Requested group %04d%s\n", request.id, !group ? " unmapped!" : "");

	response.id = request.id;

	if (!group) {
		response.result = QMI_RESULT_FAILURE_V01;
	} else {
		response.result = QMI_RESULT_SUCCESS_V01;

		index = 0;

		while ((key = group->keys[index++]).len) {
			if (key.id != -1)
				memcpy(response.data + size, &registry[key.id], key.len);

			size += key.len;
		}

		response.data_len = size;
	}

	out_packet.data = malloc(BUFFER_LEN);
	out_packet.data_len = BUFFER_LEN;

	ret = qmi_encode_message(
		&out_packet,
		QMI_RESPONSE,
		SNS_REG_GROUP_MSG_ID,
		txn_id,
		&response,
		sns_reg_group_resp_ei
	);
	if (ret < 0) {
		fprintf(stderr, "Failed to encode response: %d\n", ret);
		goto out;
	}

	ret = qrtr_sendto(sock, packet->node, packet->port, out_packet.data, out_packet.data_len);
	if (ret)
		fprintf(stderr, "Failed to send response: %d\n", ret);

out:
	free(out_packet.data);

	return ret;
}

int main(int argc, const char **argv)
{
	int fd;
	struct stat stat;
	unsigned long *registry;
	int sock;
	int pollfds;
	struct sockaddr_qrtr sq;
	unsigned char buffer[BUFFER_LEN];
	struct qrtr_packet packet;
	struct qmi_header *header;
	struct sns_reg_group_req request;
	int ret;

	fd = open("/etc/sns-reg.d/registry.conf", O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "Failed to open registry: %s\n", strerror(errno));
		return 1;
	}
	registry = parse_registry(fd);
	close(fd);
	if (!registry) {
		fprintf(stderr, "Failed to parse registry\n");
		return 1;
	}

	sock = socket(AF_QIPCRTR, SOCK_DGRAM, 0);
	if (sock < 0) {
		fprintf(stderr, "Failed to create QRTR socket: %s\n", strerror(errno));
		return 1;
	}

	ret = qrtr_publish(sock, SNS_REG_QMI_SVC_ID, SNS_REG_QMI_SVC_V1, SNS_REG_QMI_INS_ID);
	if (ret) {
		fprintf(stderr, "Failed to publish service: %d\n", ret);
		return 1;
	}

	while (true) {
		pollfds = qrtr_poll(sock, -1);
		if (!pollfds)
			continue;

		ret = qrtr_recvfrom(
			sock,
			buffer,
			BUFFER_LEN,
			&sq.sq_node,
			&sq.sq_port
		);
		if (ret < 0) {
			fprintf(stderr, "Failed to receive QRTR packet\n");
			continue;
		}

		ret = qrtr_decode(&packet, buffer, BUFFER_LEN, &sq);
		if (ret < 0) {
			fprintf(stderr, "Failed to decode QRTR packet\n");
			continue;
		}

		if (packet.type != QRTR_TYPE_DATA)
			continue;

		header = (struct qmi_header *)packet.data;
		packet.data_len = sizeof(struct qmi_header) + header->msg_len;

		if (header->msg_id == SNS_REG_GROUP_MSG_ID)
			handle_group_request(sock, &packet, registry);
	}

	return 0;
}
