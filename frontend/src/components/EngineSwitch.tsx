import { Switch, Space, Typography } from 'antd';
import { ThunderboltOutlined, RobotOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface Props {
  enabled: boolean;
  onChange: (v: boolean) => void;
}

export default function EngineSwitch({ enabled, onChange }: Props) {
  return (
    <Space>
      <ThunderboltOutlined style={{ color: enabled ? '#999' : '#1890ff' }} />
      <Text type={enabled ? 'secondary' : undefined}>极速模式</Text>
      <Switch checked={enabled} onChange={onChange} />
      <Text type={enabled ? undefined : 'secondary'}>AI 精排模式</Text>
      <RobotOutlined style={{ color: enabled ? '#1890ff' : '#999' }} />
    </Space>
  );
}
