import type { ScoreDetail } from '../types';

interface Props {
  detail: ScoreDetail;
}

const DIMENSIONS: { key: keyof ScoreDetail; label: string; maxScore: number; note: string }[] = [
  { key: 'coverage', label: '保障全面性', maxScore: 20, note: '病种/轻中症/多次赔付' },
  { key: 'price', label: '保费竞争力', maxScore: 18, note: '同类型价格百分位' },
  { key: 'flexibility', label: '投保宽松度', maxScore: 15, note: '健康告知·职业限制' },
  { key: 'waiting', label: '等待期', maxScore: 10, note: '≤90天满分' },
  { key: 'waiver', label: '豁免条款', maxScore: 10, note: '被保人/投保人豁免' },
  { key: 'adequacy', label: '保额充足度', maxScore: 10, note: '保额÷建议保额' },
  { key: 'brand', label: '品牌', maxScore: 10, note: '公司梯队：T1=85/T2=75/T3=65' },
  { key: 'service', label: '服务', maxScore: 7, note: '就医绿通/二次诊疗/特药配送' },
];

export default function ScoreRadar({ detail }: Props) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 12px', fontSize: 12, lineHeight: '20px' }}>
      {DIMENSIONS.map((d) => {
        const v = detail[d.key] || 0;
        const pct = v / d.maxScore;
        const color = pct >= 0.8 ? '#52c41a' : pct >= 0.6 ? '#faad14' : '#ff4d4f';
        return (
          <span key={d.key} title={d.note} style={{ cursor: 'help' }}>
            {d.label}
            <span style={{ fontWeight: 600, color, margin: '0 2px' }}>{v.toFixed(0)}</span>
            <span style={{ color: '#bbb', fontSize: 10 }}>/ {d.maxScore}</span>
          </span>
        );
      })}
    </div>
  );
}
