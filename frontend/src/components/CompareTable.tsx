import { Table, Tag, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ProductItem } from '../types';
import { useI18n } from '../i18n';

interface Props {
  products: ProductItem[];
}

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

export default function CompareTable({ products }: Props) {
  const { t } = useI18n();

  if (!products.length) return null;

  const formatPremium = (min: number, max: number | null): string => {
    if (max != null && max > min) {
      return `¥${min.toLocaleString()}-¥${max.toLocaleString()}`;
    }
    // 与 ProductCard.formatPremium 保持同一口径：未披露上限必须带「起」，
    // 否则同一产品在对比表里看起来是精确报价、在产品卡里不是。
    return `¥${min.toLocaleString()}${max == null ? t('common.fromSuffix') : ''}`;
  };

  const columnHelp: Record<string, string> = {
    score: t('compare.helpScore'),
    coverage: t('compare.helpCoverage'),
    price: t('compare.helpPrice'),
    flexibility: t('compare.helpFlexibility'),
    waiting: t('compare.helpWaiting'),
    adequacy: t('compare.helpAdequacy'),
    waiver: t('compare.helpWaiver'),
    brand: t('compare.helpBrand'),
    service: t('compare.helpService'),
  };

  const columns: ColumnsType<ProductItem> = [
    {
      title: t('compare.product'), dataIndex: 'name', key: 'name', fixed: 'left', width: 200,
      render: (v: string, record: ProductItem) => (
        <span>
          {v}
          {record.official_verified && <Tag color="green" style={{ marginLeft: 4, fontSize: 10 }}>{t('common.officialVerified')}</Tag>}
          {record.dual_source_verified && <Tag color="geekblue" style={{ marginLeft: 4, fontSize: 10 }}>{t('common.dualVerified')}</Tag>}
        </span>
      ),
    },
    {
      title: t('compare.company'), dataIndex: 'company', key: 'company', width: 110,
      // official=承保公司官网；aggregator=聚合站真实产品详情页
      render: (v: string, record: ProductItem) => (
        <span>
          {v}
          {record.source_url && (
            <>
              {' '}
              <a href={record.source_url} target="_blank" rel="noopener noreferrer">
                {record.source_type === 'aggregator' ? t('common.sourceAggregator') : t('common.sourceOfficial')}
              </a>
            </>
          )}
          {record.third_party_review_url && (
            <>
              {' '}
              <a href={record.third_party_review_url} target="_blank" rel="noopener noreferrer">{t('common.reviewLinkShort')}</a>
            </>
          )}
        </span>
      ),
    },
    {
      title: t('compare.type'), dataIndex: 'type', key: 'type', width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: t('compare.premium'), dataIndex: 'premium', key: 'premium', width: 120,
      render: (v: number, record: ProductItem) => <span style={{ fontWeight: 500 }}>{formatPremium(v, record.premium_max)}</span>,
      sorter: (a, b) => a.premium - b.premium,
    },
    {
      title: t('compare.deductible'), dataIndex: 'deductible', key: 'deductible', width: 90,
      render: (v: number | null) => v != null && v > 0 ? `${v.toLocaleString()}${t('common.unitYuan')}` : '-',
    },
    {
      title: t('compare.sumInsured'), dataIndex: 'sum_insured', key: 'sum_insured', width: 90,
      render: (v: number) => v > 0 ? `${v.toLocaleString()}${t('common.unitWan')}` : '-',
    },
    {
      title: <Tooltip title={columnHelp.score}><span>{t('compare.score')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: 'score', key: 'score', width: 100,
      render: (v: number) => {
        const color = v >= 80 ? '#52c41a' : v >= 60 ? '#faad14' : '#ff4d4f';
        return <span style={{ fontWeight: 700, color, fontSize: 15 }}>{v.toFixed(0)}<span style={{ fontSize: 10, color: '#999' }}>{t('common.scoreOutOf')}</span></span>;
      },
      sorter: (a, b) => a.score - b.score,
    },
    {
      title: <Tooltip title={columnHelp.coverage}><span>{t('compare.coverage')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'coverage'], key: 'coverage', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={20} tooltip={columnHelp.coverage} />,
    },
    {
      title: <Tooltip title={columnHelp.price}><span>{t('compare.price')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'price'], key: 'price', width: 95,
      render: (v: number) => <ScoreCell value={v} maxScore={18} tooltip={columnHelp.price} />,
    },
    {
      title: <Tooltip title={columnHelp.flexibility}><span>{t('compare.flexibility')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'flexibility'], key: 'flexibility', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={15} tooltip={columnHelp.flexibility} />,
    },
    {
      title: <Tooltip title={columnHelp.waiting}><span>{t('compare.waiting')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'waiting'], key: 'waiting', width: 85,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={columnHelp.waiting} />,
    },
    {
      title: <Tooltip title={columnHelp.waiver}><span>{t('compare.waiver')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'waiver'], key: 'waiver', width: 85,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={columnHelp.waiver} />,
    },
    {
      title: <Tooltip title={columnHelp.adequacy}><span>{t('compare.adequacy')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'adequacy'], key: 'adequacy', width: 90,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={columnHelp.adequacy} />,
    },
    {
      title: <Tooltip title={columnHelp.brand}><span>{t('compare.brand')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'brand'], key: 'brand', width: 80,
      render: (v: number) => <ScoreCell value={v} maxScore={10} tooltip={columnHelp.brand} />,
    },
    {
      title: <Tooltip title={columnHelp.service}><span>{t('compare.service')} <InfoCircleOutlined style={{ fontSize: 11, color: '#999' }}/></span></Tooltip>,
      dataIndex: ['score_detail', 'service'], key: 'service', width: 80,
      render: (v: number) => <ScoreCell value={v} maxScore={7} tooltip={columnHelp.service} />,
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
