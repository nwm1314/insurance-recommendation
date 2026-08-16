import { Card, Tag, Typography } from 'antd';
import ScoreRadar from './ScoreRadar';
import RiskBadge from './RiskBadge';
import type { ProductItem } from '../types';

const { Text } = Typography;

const LAYER_COLORS: Record<string, string> = {
  basic: 'blue',
  core: 'gold',
  supplement: 'green',
};

const LAYER_LABELS: Record<string, string> = {
  basic: '基础层（必备）',
  core: '核心层（建议）',
  supplement: '补充层（按需）',
};

function formatPremium(min: number, max: number | null): string {
  if (max && max > min) {
    return `¥${min.toLocaleString()}-¥${max.toLocaleString()}`;
  }
  return `¥${min.toLocaleString()}`;
}

interface Props {
  product: ProductItem;
}

export default function ProductCard({ product }: Props) {
  const scoreColor = product.score >= 80 ? '#52c41a' : product.score >= 60 ? '#faad14' : '#ff4d4f';

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      title={
        <span>
          <Text strong>{product.name}</Text>
          <Tag color={LAYER_COLORS[product.layer]} style={{ marginLeft: 8, fontSize: 11 }}>
            {LAYER_LABELS[product.layer]}
          </Tag>
        </span>
      }
      extra={<RiskBadge warnings={product.risk_warnings} />}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Text type="secondary">
          {product.company} · {product.type}
          {product.source_url && (
            <>
              {' · '}
              {/* official=承保公司官网；aggregator=聚合站真实产品详情页 */}
              <a href={product.source_url} target="_blank" rel="noopener noreferrer">
                {product.source_type === 'aggregator' ? '产品页' : '官网'}
              </a>
            </>
          )}
        </Text>
        <span>
          <Text style={{ fontSize: 13 }}>年保费 </Text>
          <Text strong style={{ fontSize: 15, color: '#1677ff' }}>{formatPremium(product.premium, product.premium_max)}</Text>
        </span>
        {product.deductible != null && product.deductible > 0 && (
          <span>
            <Text style={{ fontSize: 13 }}>免赔额 </Text>
            <Text strong>{product.deductible.toLocaleString()}元</Text>
          </span>
        )}
        <span>
          <Text style={{ fontSize: 13 }}>保额 </Text>
          <Text strong>{product.sum_insured > 0 ? `${product.sum_insured}万` : '-'}</Text>
        </span>
        <span>
          <Text style={{ fontSize: 13 }}>综合评分 </Text>
          <span style={{ fontWeight: 700, fontSize: 15, color: scoreColor }}>
            {product.score.toFixed(0)}<span style={{ fontSize: 10, color: '#999' }}>/100</span>
          </span>
        </span>
      </div>
      <div style={{ marginTop: 10 }}>
        <ScoreRadar detail={product.score_detail} />
      </div>
    </Card>
  );
}