import type { ScoreDetail } from '../types';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/messages';

interface Props {
  detail: ScoreDetail;
}

const DIMENSIONS: { key: keyof ScoreDetail; label: MessageKey; note: MessageKey; maxScore: number }[] = [
  { key: 'coverage', label: 'score.coverage', note: 'score.coverageNote', maxScore: 20 },
  { key: 'price', label: 'score.price', note: 'score.priceNote', maxScore: 18 },
  { key: 'flexibility', label: 'score.flexibility', note: 'score.flexibilityNote', maxScore: 15 },
  { key: 'waiting', label: 'score.waiting', note: 'score.waitingNote', maxScore: 10 },
  { key: 'waiver', label: 'score.waiver', note: 'score.waiverNote', maxScore: 10 },
  { key: 'adequacy', label: 'score.adequacy', note: 'score.adequacyNote', maxScore: 10 },
  { key: 'brand', label: 'score.brand', note: 'score.brandNote', maxScore: 10 },
  { key: 'service', label: 'score.service', note: 'score.serviceNote', maxScore: 7 },
];

export default function ScoreRadar({ detail }: Props) {
  const { t } = useI18n();
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 12px', fontSize: 12, lineHeight: '20px' }}>
      {DIMENSIONS.map((d) => {
        const v = detail[d.key] || 0;
        const pct = v / d.maxScore;
        const color = pct >= 0.8 ? '#52c41a' : pct >= 0.6 ? '#faad14' : '#ff4d4f';
        return (
          <span key={d.key} title={t(d.note)} style={{ cursor: 'help' }}>
            {t(d.label)}
            <span style={{ fontWeight: 600, color, margin: '0 2px' }}>{v.toFixed(0)}</span>
            <span style={{ color: '#bbb', fontSize: 10 }}>/ {d.maxScore}</span>
          </span>
        );
      })}
    </div>
  );
}
