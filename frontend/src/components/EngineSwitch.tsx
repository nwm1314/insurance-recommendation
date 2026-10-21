import { Switch, Space, Typography } from 'antd';
import { ThunderboltOutlined, RobotOutlined } from '@ant-design/icons';
import { useI18n } from '../i18n';

const { Text } = Typography;

interface Props {
  enabled: boolean;
  onChange: (v: boolean) => void;
}

export default function EngineSwitch({ enabled, onChange }: Props) {
  const { t } = useI18n();
  return (
    <Space>
      <ThunderboltOutlined style={{ color: enabled ? '#999' : '#1890ff' }} />
      <Text type={enabled ? 'secondary' : undefined}>{t('home.modeRule')}</Text>
      <Switch checked={enabled} onChange={onChange} />
      <Text type={enabled ? undefined : 'secondary'}>{t('home.modeAi')}</Text>
      <RobotOutlined style={{ color: enabled ? '#1890ff' : '#999' }} />
    </Space>
  );
}
