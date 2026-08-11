import { Table, Tag, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ProductItem } from '../types';

interface Props {
  products: ProductItem[];
}

const COLUMN_HELP: Record<string, string> = {
  score: '综合评分（0-100），基于保额全面性、保费竞争力、投保宽松度、等待期、豁免条款、保额充足性、品牌信度、增值服务 8 个维度加权计算，分数越高越好',
  coverage: '保障全面性（满分20）：重疾种类+轻症覆盖+多次赔付+责任条数，越多越好',
  price: '保费竞争力（满分18）：在同一险种产品池中的百分位排名，越靠前越便宜',
  flexibility: '投保宽松度（满分15）：健康告知条款越少+职业限制越宽 → 得分越高',
  waiting: '等待期优惠（满分10）：≤90天满分，180天仅50%',
  adequacy: '保额充足度（满分10）：实际可投保额÷建议保额，越高越好',
  waiver: '豁免条款（满分10）：含被保人豁免+5分，含投保人豁免再+5分',
  brand: '品牌信度（满分10）：T1老牌85起 T2合资75起 T3互联网65起',
  service: '增值服务（满分7）：就医绿通/二次诊疗/特药配送等，越多越好',
};

function ScoreCell({ value, maxScore, tooltip }: { value: number; maxScore: number; tooltip: string }) {
  const pct = value / maxScore;
  const color = pct >= 0.8 ? 'green' : pct >= 0.6 ? 'orange' : 'red';
  return (
    <Tooltip title={tooltip}>
      <span style={{ cursor: 'help' }}>
        <Tag color={color} style={{ margin: 0 }}>{value.toFixed(0)}</Tag>
        <span style={{ fontSize: 10, color: '#999', marginLeft: 2 }}>/ {maxScore}</span>
      </span>
    </Tooltip>
  );
}

function formatPremium(min: number, max: number | null): string {
  if (max && max > min) {
    return `¥${min.toLocaleString()}-¥${max.toLocaleString()}`;
  }
  return `¥${min.toLocaleString()}`;
}

export default function CompareTable({ products }: Props) {
  if (!products.length) return null;

  const columns: ColumnsType<ProductItem> = [
    {
      title: '产品名称', dataIndex: 'name', key: 'name', fixed: 'left', width: 200,
      render: (v: string, record: ProductItem) =>
        record.source_url ? (
          <a href={record.source_url} target="_blank" rel="noopener noreferrer">{v}</a>
        ) : v,
    },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 100 },
    {
      title: '险种', dataIndex: 'type', key: 'type', width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '年保费', dataIndex: 'premium', key: 'premium', width: 120,
      render: (v: number, record: ProductItem) => <span style={{ fontWeight: 500 }}>{formatPremium(v, record.premium_max)}</span>,
      sorter: (a, b) => a.premium - b.premium,
    },
    {
      title: '免赔额', dataIndex: 'deductible', key: 'deductible', width: 90,
      render: (v: number | null) => v != null && v > 0 ? `${v.toLocaleString()}元` : '-',
    },
    {
      title: '保额', dataIndex: 'sum_insured', key: 'sum_insured', width: 90,
      render: (v: number) => v > 0 ? `${v.toLocaleString()}万` : '-',
    },
    {
      title: <Tooltip title={COLUMN_HELP.score}><span>综合评分 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: 'score', key: 'score', width: 100,
      render: (v: number) => {
        const color = v >= 80 ? '#52c41a' : v >= 60 ? '#faad14' : '#ff4d4f';
        return <span style={{ fontWeight: 700, color, fontSize: 15 }}>{v.toFixed(0)}<span style={{ fontSize: 10, color: '#999' }}>/100</span></span>;
      },
      sorter: (a, b) => a.score - b.score,
    },
    {
      title: <Tooltip title={COLUMN_HELP.coverage}><span>保障全面 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'coverage'], key: 'coverage', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={20} tooltip={COLUMN_HELP.coverage} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.price}><span>保费竞争力 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'price'], key: 'price', width: 95,
      render: (v: number) => <ScoreCell value={v} maxScore={18} tooltip={COLUMN_HELP.price} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.flexibility}><span>投保宽松 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'flexibility'], key: 'flexibility', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={15} tooltip={COLUMN_HELP.flexibility} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.waiting}><span>等待期 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'waiting'], key: 'waiting', width: 85,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={COLUMN_HELP.waiting} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.waiver}><span>豁免条款 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'waiver'], key: 'waiver', width: 85,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={COLUMN_HELP.waiver} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.adequacy}><span>保额充足 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'adequacy'], key: 'adequacy', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={COLUMN_HELP.adequacy} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.brand}><span>品牌 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'brand'], key: 'brand', width: 80,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={COLUMN_HELP.brand} />,
    },
    {
      title: <Tooltip title={COLUMN_HELP.service}><span>服务 <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'service'], key: 'service', width: 80,
      render: (v: number) => <ScoreCell value={v} maxScore={7} tooltip={COLUMN_HELP.service} />,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={products}
      rowKey="id"
      scroll={{ x: 1450 }}
      pagination={false}
      size="small"
      bordered
    />
  );
}