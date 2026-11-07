// SPDX-License-Identifier: GPL-3.0-or-later

#include <libqrtr.h>

#include "sns_reg.h"

struct qmi_elem_info sns_reg_group_req_ei[] = {
	{
		.data_type  = QMI_UNSIGNED_2_BYTE,
		.elem_len   = 1,
		.elem_size  = sizeof(unsigned short),
		.array_type = NO_ARRAY,
		.tlv_type   = 0x01,
		.offset     = offsetof(struct sns_reg_group_req, id),
	},
	{
		.data_type = QMI_EOTI,
	},
};

struct qmi_elem_info sns_reg_group_resp_ei[] = {
	{
		.data_type  = QMI_UNSIGNED_2_BYTE,
		.elem_len   = 1,
		.elem_size  = sizeof(unsigned short),
		.array_type = NO_ARRAY,
		.tlv_type   = 0x02,
		.offset     = offsetof(struct sns_reg_group_resp, result),
	},
	{
		.data_type  = QMI_UNSIGNED_2_BYTE,
		.elem_len   = 1,
		.elem_size  = sizeof(unsigned short),
		.array_type = NO_ARRAY,
		.tlv_type   = 0x03,
		.offset     = offsetof(struct sns_reg_group_resp, id),
	},
	{
		.data_type  = QMI_DATA_LEN,
		.elem_len   = 1,
		.elem_size  = sizeof(unsigned short),
		.array_type = NO_ARRAY,
		.tlv_type   = 0x04,
		.offset     = offsetof(struct sns_reg_group_resp, data_len),
	},
	{
		.data_type  = QMI_UNSIGNED_1_BYTE,
		.elem_len   = SNS_REG_GROUP_DATA_MAX_LEN,
		.elem_size  = sizeof(unsigned char),
		.array_type = VAR_LEN_ARRAY,
		.tlv_type   = 0x04,
		.offset     = offsetof(struct sns_reg_group_resp, data),
	},
	{
		.data_type = QMI_EOTI,
	},
};
