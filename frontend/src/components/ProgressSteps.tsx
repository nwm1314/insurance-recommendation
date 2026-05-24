import { Steps } from 'antd';

const steps = [
  { title: '基本信息' },
  { title: '职业与收入' },
  { title: '健康告知' },
  { title: '偏好确认' },
];

interface Props {
  current: number;
}

export default function ProgressSteps({ current }: Props) {
  return <Steps current={current} items={steps} style={{ marginBottom: 32 }} />;
}
