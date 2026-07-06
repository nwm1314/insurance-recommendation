import { Card, Row, Col, Typography } from 'antd';

const { Text } = Typography;

interface Props {
  annualIncome: number;
  totalBudget: number;
  allocation: { medical: number; accident: number; critical_illness: number; life: number; cancer: number };
}

const ALLOCATION_ITEMS = [
  { key: 'medical' as const, label: '医疗险', color: '#1677ff', note: '打底·报销大病住院费' },
  { key: 'accident' as const, label: '意外险', color: '#52c41a', note: '杠杆·意外身故/伤残' },
  { key: 'critical_illness' as const, label: '重疾险', color: '#faad14', note: '核心·弥补大病收入损失' },
  { key: 'life' as const, label: '定期寿险', color: '#722ed1', note: '责任·家庭支柱身故保障' },
  { key: 'cancer' as const, label: '防癌险', color: '#eb2f96', note: '补充·高龄或健康异常兜底' },
];

export default function BudgetPreview({ annualIncome, totalBudget, allocation }: Props) {
  const ratioPct = ((totalBudget / annualIncome) * 100).toFixed(1);
  const pct = (v: number) => Math.round(v * 100);

  return (
    <Card title="预算分析" size="small">
      <Row gutter={8} style={{ marginBottom: 12 }}>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>年收入</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>¥{(annualIncome / 10000).toFixed(0)}<span style={{ fontSize: 12, fontWeight: 400 }}>万</span></div>
        </Col>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>建议保费</Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#1677ff' }}>¥{totalBudget.toLocaleString()}</div>
        </Col>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>占比</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{ratioPct}<span style={{ fontSize: 12, fontWeight: 400 }}>%</span></div>
        </Col>
      </Row>
      <div>
        {ALLOCATION_ITEMS.map((item) => {
          const v = pct(allocation[item.key]);
          return (
            <div key={item.key} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                <span style={{ fontSize: 12 }}>
                  <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: item.color, marginRight: 4, verticalAlign: 'middle' }} />
                  {item.label}
                </span>
                <span style={{ fontSize: 12, fontWeight: 500 }}>{v}%</span>
              </div>
              <div style={{ height: 4, borderRadius: 2, background: '#f0f0f0' }}>
                <div style={{ height: 4, borderRadius: 2, background: item.color, width: `${Math.max(v, 2)}%`, transition: 'width 0.3s' }} />
              </div>
              <Text type="secondary" style={{ fontSize: 10 }}>{item.note}</Text>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
