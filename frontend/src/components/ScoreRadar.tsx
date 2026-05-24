import type { ScoreDetail } from '../types';

interface Props {
  detail: ScoreDetail;
}

const DIMENSIONS: { key: keyof ScoreDetail; label: string }[] = [
  { key: 'coverage', label: '保障全面性' },
  { key: 'price', label: '保费竞争力' },
  { key: 'flexibility', label: '投保宽松度' },
  { key: 'waiting', label: '等待期' },
  { key: 'waiver', label: '豁免条款' },
  { key: 'adequacy', label: '保额充足度' },
];

export default function ScoreRadar({ detail }: Props) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12 }}>
      {DIMENSIONS.map((d) => (
        <span key={d.key}>
          {d.label}: <strong>{detail[d.key]}</strong>
        </span>
      ))}
    </div>
  );
}
