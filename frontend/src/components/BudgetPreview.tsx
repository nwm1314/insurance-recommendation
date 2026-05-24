import { Card, Progress, Row, Col, Statistic } from 'antd';

interface Props {
  annualIncome: number;
  totalBudget: number;
  allocation: { medical: number; accident: number; critical_illness: number; life: number };
}

export default function BudgetPreview({ annualIncome, totalBudget, allocation }: Props) {
  const pct = (v: number) => Math.round(v * 100);
  return (
    <Card title="预算分析" size="small">
      <Row gutter={16}>
        <Col span={8}><Statistic title="年收入" value={annualIncome} prefix="¥" /></Col>
        <Col span={8}><Statistic title="推荐预算" value={totalBudget} prefix="¥" precision={0} /></Col>
        <Col span={8}><Statistic title="占比" value={((totalBudget / annualIncome) * 100).toFixed(1)} suffix="%" /></Col>
      </Row>
      <div style={{ marginTop: 16 }}>
        <div>医疗险 <Progress percent={pct(allocation.medical)} size="small" /></div>
        <div>意外险 <Progress percent={pct(allocation.accident)} size="small" /></div>
        <div>重疾险 <Progress percent={pct(allocation.critical_illness)} size="small" /></div>
        <div>寿　险 <Progress percent={pct(allocation.life)} size="small" /></div>
      </div>
    </Card>
  );
}
