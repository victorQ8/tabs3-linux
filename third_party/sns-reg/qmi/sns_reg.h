/* SPDX-License-Identifier: GPL-3.0-or-later */

#pragma once

#include <libqrtr.h>

#define SNS_REG_QMI_SVC_ID		0x010f
#define SNS_REG_QMI_SVC_V1		2
#define SNS_REG_QMI_INS_ID		0

#define SNS_REG_GROUP_MSG_ID		0x4
#define SNS_REG_GROUP_DATA_MAX_LEN	0x100

struct sns_reg_group_req {
	unsigned short id;
};

struct sns_reg_group_resp {
	unsigned short result;
	unsigned short id;
	unsigned short data_len;
	unsigned char data[SNS_REG_GROUP_DATA_MAX_LEN];
};

extern struct qmi_elem_info sns_reg_group_req_ei[];
extern struct qmi_elem_info sns_reg_group_resp_ei[];
