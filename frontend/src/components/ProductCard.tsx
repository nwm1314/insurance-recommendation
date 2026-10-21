import { Card, Tag, Typography } from 'antd';
import ScoreRadar from './ScoreRadar';
import RiskBadge from './RiskBadge';
import type { ProductItem } from '../types';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/messages';

const { Text } = Typography;

const LAYER_COLORS: Record<string, string> = {
  basic: 'blue',
  core: 'gold',
  supplement: 'green',
};

const LAYER_LABEL_KEYS: Record<string, MessageKey> = {
  basic: 'layer.basic',
  core: 'layer.core',
  supplement: 'layer.supplement',
};

function formatPremium(min: number, max: number | null, fromSuffix: string): string {
  if (max != null && max > min) {
    return `¥${min.toLocaleString()}-¥${max.toLocaleString()}`;
  }
  // 上限未披露（max 为 null）时保留「起」：结果页顶部的口径说明正是以「起」告知
  // 用户该数字不是精确报价，单个产品卡也必须一致，否则会被读成确定价格。
  return `¥${min.toLocaleString()}${max == null ? fromSuffix : ''}`;
}

interface Props {
  product: ProductItem;
}

export default function ProductCard({ product }: Props) {
  const { t } = useI18n();
  const scoreColor = product.score >= 80 ? '#52c41a' : product.score >= 60 ? '#faad14' : '#ff4d4f';

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      title={
        <span>
          <Text strong>{product.name}</Text>
          <Tag color={LAYER_COLORS[product.layer]} style={{ marginLeft: 8, fontSize: 11 }}>
            {t(LAYER_LABEL_KEYS[product.layer])}
          </Tag>
          {product.official_verified && (
            <Tag color="green" style={{ fontSize: 11 }}>{t('common.officialVerified')}</Tag>
          )}
          {product.dual_source_verified && (
            <Tag color="geekblue" style={{ fontSize: 11 }}>{t('common.dualVerified')}</Tag>
          )}
          {product.data_stale && (
            <Tag color="orange" style={{ fontSize: 11 }}>{t('common.stale')}</Tag>
          )}
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
                {product.source_type === 'aggregator' ? t('common.sourceAggregator') : t('common.sourceOfficial')}
              </a>
            </>
          )}
          {product.third_party_review_url && (
            <>
              {' · '}
              <a href={product.third_party_review_url} target="_blank" rel="noopener noreferrer">
                {t('common.reviewLink')}
              </a>
            </>
          )}
        </Text>
        <span>
          <Text style={{ fontSize: 13 }}>{t('product.annualPremium')}</Text>
          <Text strong style={{ fontSize: 15, color: '#1677ff' }}>
            {formatPremium(product.premium, product.premium_max, t('common.fromSuffix'))}
          </Text>
        </span>
        {product.deductible != null && product.deductible > 0 && (
          <span>
            <Text style={{ fontSize: 13 }}>{t('product.deductible')}</Text>
            <Text strong>{product.deductible.toLocaleString()}{t('common.unitYuan')}</Text>
          </span>
        )}
        <span>
          <Text style={{ fontSize: 13 }}>{t('product.sumInsured')}</Text>
          <Text strong>{product.sum_insured > 0 ? `${product.sum_insured}${t('common.unitWan')}` : '-'}</Text>
        </span>
        <span>
          <Text style={{ fontSize: 13 }}>{t('product.score')}</Text>
          <span style={{ fontWeight: 700, fontSize: 15, color: scoreColor }}>
            {product.score.toFixed(0)}<span style={{ fontSize: 10, color: '#999' }}>{t('common.scoreOutOf')}</span>
          </span>
        </span>
      </div>
      <div style={{ marginTop: 10 }}>
        <ScoreRadar detail={product.score_detail} />
      </div>
    </Card>
  );
}
