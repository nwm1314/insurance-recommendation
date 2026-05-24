import { Tag, Tooltip } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import type { RiskWarning } from '../types';

interface Props {
  warnings: RiskWarning[];
}

export default function RiskBadge({ warnings }: Props) {
  if (!warnings.length) return null;
  return (
    <Tooltip title={warnings.map((w) => w.message).join('；')}>
      <Tag color="error" icon={<ExclamationCircleOutlined />}>需关注</Tag>
    </Tooltip>
  );
}
