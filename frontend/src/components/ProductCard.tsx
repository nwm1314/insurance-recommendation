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
  basic: '基础层',
  core: '核心层',
  supplement: '补充层',
};

interface Props {
  product: ProductItem;
}

export default function ProductCard({ product }: Props) {
  return (
    <Card
      size="small"
      title={
        <span>
          {product.source_url ? (
            <a href={product.source_url} target="_blank" rel="noopener noreferrer">
              {product.name}
            </a>
          ) : (
            product.name
          )}
          <Tag color={LAYER_COLORS[product.layer]} style={{ marginLeft: 8 }}>
            {LAYER_LABELS[product.layer]}
          </Tag>
        </span>
      }
      extra={<RiskBadge warnings={product.risk_warnings} />}
    >
      <Text type="secondary">{product.company} · {product.type}</Text>
      <div style={{ marginTop: 8 }}>
        <Text strong>¥{product.premium.toLocaleString()}/年</Text>
        <Text style={{ marginLeft: 16 }}>保额 {product.sum_insured.toLocaleString()}</Text>
        <Tag color="orange" style={{ marginLeft: 8 }}>评分 {product.score}</Tag>
      </div>
      <div style={{ marginTop: 8 }}>
        <ScoreRadar detail={product.score_detail} />
      </div>
    </Card>
  );
}
