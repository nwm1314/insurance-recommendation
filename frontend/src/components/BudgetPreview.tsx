import { Card, Row, Col, Typography } from 'antd';

const { Text } = Typography;

interface Props {
  annualIncome: number;
  totalBudget: number;
  allocation: { medical: number; accident: number; critical_illness: number; life: number; cancer: number };
  quoteMin?: number | null;
  quoteMax?: number | null;
  quoteUnknownMax?: boolean;
}

const ALLOCATION_ITEMS = [
  { key: 'medical' as const, label: '医疗险', color: '#1677ff', note: '打底·报销大病住院费' },
  { key: 'accident' as const, label: '意外险', color: '#52c41a', note: '杠杆·意外身故/伤残' },
  { key: 'critical_illness' as const, label: '重疾险', color: '#faad14', note: '核心·填补大病收入损失' },
  { key: 'life' as const, label: '定期寿险', color: '#722ed1', note: '责任·家庭支柱身故保障' },
  { key: 'cancer' as const, label: '防癌险', color: '#eb2f96', note: '补充·高龄或体况异常优选' },
];

function formatQuote(quoteMin: number | null | undefined, quoteMax: number | null | undefined): string {
  if (quoteMin == null) return '候选池不足，暂无产品报价';
  if (quoteMax != null && quoteMax > quoteMin) {
    return `¥${quoteMin.toLocaleString()}~¥${quoteMax.toLocaleString()}/年`;
  }
  return `¥${quoteMin.toLocaleString()}起/年`;
}

export default function BudgetPreview({ annualIncome, totalBudget, allocation, quoteMin, quoteMax, quoteUnknownMax }: Props) {
  const ratioPct = ((totalBudget / annualIncome) * 100).toFixed(1);
  const pct = (v: number) => Math.round(v * 100);
  const budgetMin = Math.round(totalBudget * 0.85);
  const budgetMax = Math.round(totalBudget * 1.15);
  const quoteOverBudget = quoteMax != null && quoteMax > totalBudget;

  return (
    <Card title="预算与报价分析" size="small">
      <Row gutter={8} style={{ marginBottom: 12 }}>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>年收入</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>¥{(annualIncome / 10000).toFixed(0)}<span style={{ fontSize: 12, fontWeight: 400 }}>万</span></div>
        </Col>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>预算建议（估算）</Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#1677ff' }}>约¥{totalBudget.toLocaleString()}</div>
          <Text type="secondary" style={{ fontSize: 10 }}>建议区间 ¥{budgetMin.toLocaleString()}-¥{budgetMax.toLocaleString()}（估算）</Text>
        </Col>
        <Col xs={24} sm={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>占比</Text>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{ratioPct}<span style={{ fontSize: 12, fontWeight: 400 }}>%</span></div>
        </Col>
      </Row>
      <div style={{ marginBottom: 12, padding: '8px 10px', background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>产品报价区间（真实产品报价）</Text>
        <div style={{ fontWeight: 700, fontSize: 16, color: quoteOverBudget ? '#ff4d4f' : '#389e0d' }}>
          {formatQuote(quoteMin, quoteMax)}
        </div>
        <Text type="secondary" style={{ fontSize: 10 }}>
          {quoteOverBudget
            ? '方案最高价超出预算建议，请谨慎投保或调整预算'
            : quoteUnknownMax
              ? '部分产品未披露保费上限，展示区间下限，最终价格以核保为准'
              : '最终保费以保险公司核保结论与官方条款为准'}
        </Text>
      </div>
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
