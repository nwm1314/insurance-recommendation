import { Tag, Tooltip } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import type { RiskWarning } from '../types';
import { useI18n } from '../i18n';

interface Props {
  warnings: RiskWarning[];
}

export default function RiskBadge({ warnings }: Props) {
  const { t } = useI18n();
  if (!warnings.length) return null;
  return (
    <Tooltip title={warnings.map((w) => w.message).join('；')}>
      <Tag color="error" icon={<ExclamationCircleOutlined />}>{t('risk.needsAttention')}</Tag>
    </Tooltip>
  );
}
