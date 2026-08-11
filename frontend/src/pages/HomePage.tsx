import { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Form, InputNumber, Select, Radio, Checkbox, Slider, Button, Card, Space, Typography, Row, Col, Divider, Tag, Tooltip, Alert, message } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import ProgressSteps from '../components/ProgressSteps';
import EngineSwitch from '../components/EngineSwitch';
import { fetchProfileDetail } from '../api/auth';
import type { UserProfile } from '../types';

const { Title, Text } = Typography;

// 健康异常项分级：level 1=轻度(智能核保可过), 2=中度(可能除外/加费), 3=重度(可能拒保)
interface HealthOption {
  label: string;
  value: string;
  level: 1 | 2 | 3;
  group: string;
  tip?: string;
}

const HEALTH_OPTIONS: HealthOption[] = [
  // 心血管与代谢
  { label: '高血压（1级/轻度·140-159）', value: 'hypertension_l1', level: 1, group: '心血管与代谢', tip: '多数产品可标准承保' },
  { label: '高血压（2级及以上·≥160）', value: 'hypertension_l2', level: 2, group: '心血管与代谢', tip: '可能加费或除外' },
  { label: '高血脂/高胆固醇', value: 'hyperlipidemia', level: 1, group: '心血管与代谢' },
  { label: '冠心病/心肌缺血', value: 'chd', level: 3, group: '心血管与代谢', tip: '重疾险通常拒保' },
  { label: '心律失常（房颤/早搏/传导阻滞）', value: 'arrhythmia', level: 2, group: '心血管与代谢' },
  { label: '心脏瓣膜疾病（含反流/狭窄）', value: 'valve_disease', level: 2, group: '心血管与代谢' },
  { label: '先天性心脏病（已手术/未手术）', value: 'congenital_heart', level: 2, group: '心血管与代谢' },
  { label: '动脉硬化/颈动脉斑块', value: 'atherosclerosis', level: 2, group: '心血管与代谢' },

  // 内分泌与代谢
  { label: '糖尿病（2型/控制良好）', value: 'diabetes_l1', level: 2, group: '内分泌与代谢', tip: '空腹血糖<7、无并发症' },
  { label: '糖尿病（1型/伴并发症）', value: 'diabetes_l2', level: 3, group: '内分泌与代谢', tip: '常规重疾/医疗险通常拒保' },
  { label: '糖耐量异常/空腹血糖受损', value: 'glucose_impaired', level: 1, group: '内分泌与代谢' },
  { label: '甲状腺结节（TI-RADS 1-3类）', value: 'thyroid_nodule_l1', level: 1, group: '内分泌与代谢', tip: '多数产品可标准或除外承保' },
  { label: '甲状腺结节（TI-RADS 4a及以上）', value: 'thyroid_nodule_l2', level: 2, group: '内分泌与代谢', tip: '可能延期或除外' },
  { label: '甲亢/甲减（含桥本氏甲状腺炎）', value: 'thyroid_dysfunction', level: 1, group: '内分泌与代谢', tip: '控制稳定可标体' },
  { label: '乳腺结节（BI-RADS 1-3类）', value: 'breast_nodule_l1', level: 1, group: '内分泌与代谢' },
  { label: '乳腺结节（BI-RADS 4a及以上）', value: 'breast_nodule_l2', level: 2, group: '内分泌与代谢' },
  { label: '高尿酸血症/痛风', value: 'gout', level: 1, group: '内分泌与代谢', tip: '无关节变形/肾损伤可标体' },

  // 消化系统（含IBD）
  { label: '炎症性肠病IBD·克罗恩病', value: 'crohns_disease', level: 3, group: '消化系统', tip: '重疾/医疗险通常拒保，可考虑惠民保' },
  { label: '炎症性肠病IBD·溃疡性结肠炎', value: 'ulcerative_colitis', level: 3, group: '消化系统', tip: '重疾/医疗险通常拒保' },
  { label: '慢性胃炎/胃溃疡', value: 'gastritis_ulcer', level: 1, group: '消化系统', tip: '幽门螺杆菌阴性、无肠化可标体' },
  { label: '胃食管反流病（GERD）', value: 'gerd', level: 1, group: '消化系统' },
  { label: '脂肪肝（轻度·无肝功能异常）', value: 'fatty_liver_l1', level: 1, group: '消化系统' },
  { label: '脂肪肝（中重度/伴肝功能异常）', value: 'fatty_liver_l2', level: 2, group: '消化系统' },
  { label: '乙肝（病毒携带/小三阳）', value: 'hepatitis_b_l1', level: 2, group: '消化系统', tip: '肝功能正常、DNA阴性部分产品可投' },
  { label: '乙肝（大三阳/活动期）', value: 'hepatitis_b_l2', level: 3, group: '消化系统', tip: '常规产品通常拒保' },
  { label: '丙肝/自身免疫性肝病', value: 'hepatitis_other', level: 3, group: '消化系统' },
  { label: '肝硬化', value: 'cirrhosis', level: 3, group: '消化系统', tip: '所有健康险拒保' },
  { label: '胆囊息肉（<1cm）', value: 'gallbladder_polyp', level: 1, group: '消化系统' },
  { label: '胆囊息肉（≥1cm/多发）', value: 'gallbladder_polyp_l2', level: 2, group: '消化系统' },
  { label: '胰腺炎（急性/慢性）', value: 'pancreatitis', level: 2, group: '消化系统' },
  { label: '肝囊肿/肝血管瘤', value: 'liver_cyst', level: 1, group: '消化系统' },

  // 呼吸系统
  { label: '肺结节（微小结节≤5mm）', value: 'lung_nodule_l1', level: 1, group: '呼吸系统', tip: '首次发现需延期6-12月' },
  { label: '肺结节（>5mm/多发/磨玻璃）', value: 'lung_nodule_l2', level: 2, group: '呼吸系统', tip: '可能延期或除外' },
  { label: '哮喘（轻度/间歇性）', value: 'asthma_l1', level: 1, group: '呼吸系统' },
  { label: '哮喘（中重度/持续用药）', value: 'asthma_l2', level: 2, group: '呼吸系统' },
  { label: '慢性支气管炎/慢阻肺', value: 'copd', level: 2, group: '呼吸系统' },
  { label: '睡眠呼吸暂停综合征', value: 'sleep_apnea', level: 1, group: '呼吸系统' },
  { label: '肺结核/肺炎史', value: 'pulmonary_history', level: 1, group: '呼吸系统', tip: '已治愈无后遗症可标体' },

  // 泌尿与生殖系统
  { label: '肾结石（单发/无积水）', value: 'kidney_stone_l1', level: 1, group: '泌尿与生殖', tip: '无肾功能异常可标体' },
  { label: '肾结石（多发/伴积水）', value: 'kidney_stone_l2', level: 2, group: '泌尿与生殖' },
  { label: '肾炎/IgA肾病/肾功能异常', value: 'nephritis', level: 3, group: '泌尿与生殖', tip: '重疾/寿险通常拒保' },
  { label: '肾囊肿/多囊肾', value: 'kidney_cyst', level: 1, group: '泌尿与生殖' },
  { label: '前列腺增生/前列腺炎', value: 'prostate', level: 1, group: '泌尿与生殖' },
  { label: '子宫肌瘤/卵巢囊肿（良性）', value: 'gyn_benign', level: 1, group: '泌尿与生殖' },
  { label: '宫颈上皮内瘤变（CIN）', value: 'cin', level: 2, group: '泌尿与生殖', tip: 'CIN1-2术后可标体，CIN3需观察' },
  { label: '子宫内膜异位症', value: 'endometriosis', level: 1, group: '泌尿与生殖' },

  // 骨骼与神经系统
  { label: '腰椎/颈椎间盘突出', value: 'disc_herniation', level: 1, group: '骨骼与神经' },
  { label: '类风湿关节炎/强直性脊柱炎', value: 'rheumatic', level: 2, group: '骨骼与神经' },
  { label: '骨质疏松/骨折史', value: 'osteoporosis', level: 1, group: '骨骼与神经' },
  { label: '癫痫（已控制/未控制）', value: 'epilepsy', level: 2, group: '骨骼与神经' },
  { label: '脑卒中/脑梗/TIA史', value: 'stroke', level: 3, group: '骨骼与神经', tip: '重疾/寿险通常拒保' },
  { label: '帕金森病/阿尔茨海默病', value: 'neurodegenerative', level: 3, group: '骨骼与神经' },
  { label: '偏头痛（频繁发作）', value: 'migraine', level: 1, group: '骨骼与神经' },

  // 肿瘤与血液
  { label: '良性肿瘤（已切除/病理良性）', value: 'benign_tumor', level: 1, group: '肿瘤与血液', tip: '术后满一定期限无复发可标体' },
  { label: '恶性肿瘤/癌症（已治愈≥5年）', value: 'cancer_remission', level: 3, group: '肿瘤与血液', tip: '部分产品可考虑，需个案核保' },
  { label: '恶性肿瘤/癌症（近5年/治疗中）', value: 'cancer_active', level: 3, group: '肿瘤与血液', tip: '健康险通常拒保' },
  { label: '肿瘤标志物异常', value: 'tumor_marker', level: 2, group: '肿瘤与血液' },
  { label: '贫血（轻度/缺铁性）', value: 'anemia_l1', level: 1, group: '肿瘤与血液' },
  { label: '贫血（中重度/再生障碍性）', value: 'anemia_l2', level: 2, group: '肿瘤与血液' },
  { label: '白细胞/血小板异常', value: 'blood_abnormal', level: 2, group: '肿瘤与血液' },
  { label: '淋巴结肿大（未明确诊断）', value: 'lymphadenopathy', level: 2, group: '肿瘤与血液' },

  // 就医与手术史
  { label: '近2年住院史（非体检/分娩）', value: 'hospitalization', level: 2, group: '就医与手术史', tip: '需提供出院小结' },
  { label: '手术史（良性/已痊愈≥5年）', value: 'surgery_old', level: 1, group: '就医与手术史' },
  { label: '手术史（近5年内/重大手术）', value: 'surgery_recent', level: 2, group: '就医与手术史', tip: '需提供病理报告核保' },
  { label: '器官移植史', value: 'organ_transplant', level: 3, group: '就医与手术史', tip: '健康险通常拒保' },
  { label: '精神心理疾病（抑郁/焦虑/双相）', value: 'mental_health', level: 2, group: '就医与手术史', tip: '部分产品询问5年内就诊史' },
  { label: '长期服用药物（处方药）', value: 'long_term_medication', level: 1, group: '就医与手术史' },
  { label: 'BMI异常（肥胖≥30/过轻<17）', value: 'bmi_abnormal', level: 1, group: '就医与手术史', tip: 'BMI≥30可能加费' },
  { label: '吸烟史（≥20支/天·≥10年）', value: 'smoking', level: 1, group: '就医与手术史' },
  { label: '饮酒史（≥40g酒精/天）', value: 'alcohol', level: 1, group: '就医与手术史' },
];

const LEVEL_COLORS: Record<number, string> = { 1: 'green', 2: 'orange', 3: 'red' };
const LEVEL_LABELS: Record<number, string> = { 1: '轻度', 2: '中度', 3: '重度' };

// 保险公司按梯队分组（与后端种子数据一致）
interface CompanyOption { label: string; value: string; tier: number; }
const COMPANY_OPTIONS: CompanyOption[] = [
  // Tier 1: 老牌大厂
  { label: '中国平安 / 平安人寿 / 平安健康 / 平安财险', value: '中国平安', tier: 1 },
  { label: '中国人寿', value: '中国人寿', tier: 1 },
  { label: '太平洋保险 / 太平洋人寿 / 太保寿险', value: '太平洋保险', tier: 1 },
  { label: '人保财险 / 人保健康 / 人保寿险', value: '人保财险', tier: 1 },
  { label: '泰康人寿 / 泰康在线', value: '泰康人寿', tier: 1 },
  { label: '新华保险', value: '新华保险', tier: 1 },
  { label: '阳光人寿', value: '阳光人寿', tier: 1 },
  // Tier 2: 合资/特色险企
  { label: '同方全球人寿', value: '同方全球人寿', tier: 2 },
  { label: '中意人寿', value: '中意人寿', tier: 2 },
  { label: '复星联合健康', value: '复星联合健康', tier: 2 },
  { label: '光大永明', value: '光大永明', tier: 2 },
  { label: '工银安盛', value: '工银安盛', tier: 2 },
  { label: '招商信诺', value: '招商信诺', tier: 2 },
  { label: '安盛天平', value: '安盛天平', tier: 2 },
  // Tier 3: 互联网/高性价比
  { label: '众安保险', value: '众安保险', tier: 3 },
  { label: '瑞泰人寿', value: '瑞泰人寿', tier: 3 },
  { label: '和泰人寿', value: '和泰人寿', tier: 3 },
  { label: '华贵人寿', value: '华贵人寿', tier: 3 },
  { label: '信泰人寿', value: '信泰人寿', tier: 3 },
  { label: '国富人寿', value: '国富人寿', tier: 3 },
];

const TIER_COLORS: Record<number, string> = { 1: 'blue', 2: 'purple', 3: 'orange' };
const TIER_LABELS: Record<number, string> = { 1: '老牌大厂', 2: '合资险企', 3: '互联网/高性价比' };
const STEP_FIELDS = [
  ['age', 'gender', 'life_stage', 'family_burden'],
  ['job_class', 'existing_coverage'],
  ['health_status', 'health_issues'],
] as const;

// Map user-facing brand to DB company names (includes subsidiaries)
const BRAND_TO_DB_COMPANIES: Record<string, string[]> = {
  '中国平安': ['中国平安', '平安人寿', '平安健康', '平安财险'],
  '太平洋保险': ['太平洋保险', '太平洋人寿', '太保寿险'],
  '人保财险': ['人保财险', '人保健康', '人保寿险'],
  '泰康人寿': ['泰康人寿', '泰康在线'],
};

export default function HomePage() {
  const [step, setStep] = useState(0);
  const [aiMode, setAiMode] = useState(false);
  const [income, setIncome] = useState(200000);
  const [budgetRatio, setBudgetRatio] = useState(0.08);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // 已选健康项中未被后端识别的项：显式提示，不静默忽略（仅作记录，不作承保判断）
  const healthIssues: string[] = Form.useWatch('health_issues', form) || [];
  const unknownHealthItems = healthIssues.filter(
    (v: string) => !HEALTH_OPTIONS.some((o) => o.value === v)
  );

  const fillProfile = (profile: Record<string, unknown>) => {
    form.setFieldsValue({
      age: typeof profile.age === 'number' ? profile.age : undefined,
      gender: profile.gender,
      life_stage: profile.life_stage,
      family_burden: profile.family_burden,
      job_class: typeof profile.job_class === 'number' ? profile.job_class : undefined,
      existing_coverage: Array.isArray(profile.existing_coverage) ? profile.existing_coverage : [],
      health_status: profile.health_status,
      health_issues: Array.isArray(profile.health_issues) ? profile.health_issues : [],
      preferred_companies: Array.isArray(profile.preferred_companies) ? profile.preferred_companies : [],
      preferred_type: typeof profile.preferred_type === 'string' ? profile.preferred_type : undefined,
    });
    if (typeof profile.annual_income === 'number') {
      setIncome(profile.annual_income);
    }
    if (typeof profile.budget_ratio === 'number') {
      setBudgetRatio(profile.budget_ratio);
    }
    if (typeof profile.enable_llm_engine === 'boolean') {
      setAiMode(profile.enable_llm_engine);
    }
  };

  useEffect(() => {
    const stateProfile = location.state?.profile as Record<string, unknown> | undefined;
    if (stateProfile) {
      fillProfile(stateProfile);
      message.info('已加载保存的画像，请确认后提交');
      return;
    }
    const profileId = searchParams.get('profileId');
    if (!profileId) return;
    (async () => {
      try {
        const detail = await fetchProfileDetail(Number(profileId));
        fillProfile(detail.profile);
        message.info(`已加载画像“${detail.name}”，请确认后提交`);
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) {
          message.error('画像不存在或已被删除');
        } else if (status === 403) {
          message.error('您无权访问该画像');
        } else {
          message.error('画像加载失败，请稍后重试');
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      // Expand brand selections to actual DB company names
      const brandSelections: string[] = (values.preferred_companies as string[]) || [];
      const dbCompanies: string[] = [];
      for (const brand of brandSelections) {
        const mapped = BRAND_TO_DB_COMPANIES[brand];
        if (mapped) {
          dbCompanies.push(...mapped);
        } else {
          dbCompanies.push(brand);
        }
      }
      const profile: UserProfile = {
        age: values.age as number,
        gender: values.gender as 'male' | 'female',
        annual_income: income,
        job_class: values.job_class as number,
        life_stage: values.life_stage as string,
        family_burden: values.family_burden as string,
        health_status: values.health_status as string,
        health_issues: (values.health_issues as string[]) || [],
        existing_coverage: (values.existing_coverage as string[]) || [],
        preferred_type: (values.preferred_type as string) || undefined,
        budget_ratio: budgetRatio,
        preferred_companies: dbCompanies,
        enable_llm_engine: aiMode,
      };
      navigate('/result', { state: { profile } });
    } catch {
      // Validation failed — Ant Design will show field errors
    }
  };

  const handleNext = async () => {
    try {
      await form.validateFields([...STEP_FIELDS[step]]);
      setStep((s) => s + 1);
    } catch {
      // Validation failed, field-level messages are displayed by Ant Design.
    }
  };

  return (
    <Card style={{ maxWidth: 760, margin: '32px auto' }}>
      <Title level={3} style={{ textAlign: 'center', marginBottom: 4 }}>智能保险推荐</Title>
      <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginBottom: 16 }}>
        1分钟填写 · 3套方案 · 规则引擎按年龄、职业与预算筛选
      </Text>
      <ProgressSteps current={step} />

      <Form form={form} layout="vertical"
        initialValues={{
          gender: 'male', life_stage: 'single', family_burden: 'none',
          health_status: 'standard', job_class: 2,
        }}>
        {/* Step 0: Basic info */}
        <div style={{ display: step === 0 ? 'block' : 'none' }}>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="age" label="年龄" rules={[{ required: true, message: '请输入年龄' }]}>
                <InputNumber min={0} max={120} style={{ width: '100%' }} placeholder="0-120" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="gender" label="性别" rules={[{ required: true }]}>
                <Radio.Group>
                  <Radio.Button value="male">男</Radio.Button>
                  <Radio.Button value="female">女</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="life_stage" label="人生阶段" rules={[{ required: true }]}>
            <Select options={[
              { label: '单身', value: 'single' }, { label: '已婚无孩', value: 'married' },
              { label: '已婚有孩', value: 'married_with_kids' }, { label: '空巢', value: 'empty_nest' },
              { label: '退休', value: 'retired' },
            ]} placeholder="选择人生阶段" />
          </Form.Item>
          <Form.Item name="family_burden" label="家庭负担">
            <Select options={[
              { label: '无负担', value: 'none' }, { label: '需赡养父母', value: 'parents' },
              { label: '需抚养子女', value: 'children' }, { label: '双重负担', value: 'dual' },
            ]} />
          </Form.Item>
        </div>

        {/* Step 1: Income & Occupation */}
        <div style={{ display: step === 1 ? 'block' : 'none' }}>
          <Form.Item label="年收入（元）">
            <InputNumber value={income} onChange={(v) => setIncome(v || 0)}
              min={10000} max={10000000} step={10000} style={{ width: '100%' }}
              formatter={(v) => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
          </Form.Item>
          <Form.Item name="job_class" label="职业类别" rules={[{ required: true, message: '请选择职业类别' }]}>
            <Select options={[
              { label: '1类（低风险·室内办公）', value: 1 }, { label: '2类（较轻·外勤文职）', value: 2 },
              { label: '3类（一般·轻体力劳动）', value: 3 }, { label: '4类（中等·制造业）', value: 4 },
              { label: '5类（较高·建筑运输）', value: 5 }, { label: '6类（高风险·高空矿下）', value: 6 },
            ]} placeholder="选择职业风险等级" />
          </Form.Item>
          <Form.Item name="existing_coverage" label="已有保障">
            <Checkbox.Group options={[
              { label: '社保', value: 'social' }, { label: '已有商业保险', value: 'commercial' },
            ]} />
          </Form.Item>
          <Form.Item label={`预算占比：${(budgetRatio * 100).toFixed(0)}%（≈ ¥${(income * budgetRatio).toLocaleString()}/年）`}>
            <Slider min={3} max={10} step={0.5} value={budgetRatio * 100}
              onChange={(v) => setBudgetRatio((v as number) / 100)}
              marks={{ 3: '3%', 5: '5%', 8: '8%', 10: '10%' }}
              tooltip={{ formatter: (v) => `${v}%` }} />
          </Form.Item>
        </div>

        {/* Step 2: Health disclosure with severity grading */}
        <div style={{ display: step === 2 ? 'block' : 'none' }}>
          <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f0f5ff', borderRadius: 6, border: '1px solid #d6e4ff' }}>
            <Text strong style={{ fontSize: 13 }}>
              <Tag color="green" style={{ marginRight: 4 }}>轻度</Tag>大多
              <Tag color="orange" style={{ marginLeft: 8, marginRight: 4 }}>中度</Tag>可能除外/加费
              <Tag color="red" style={{ marginLeft: 8, marginRight: 4 }}>重度</Tag>可能拒保
            </Text>
            <Tooltip title="等级基于保险行业通用核保规则，具体以产品健康告知及智能核保结论为准">
              <QuestionCircleOutlined style={{ marginLeft: 8, color: '#999' }} />
            </Tooltip>
          </div>

          <Form.Item name="health_status" label="健康状态" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value="standard">标准体（无异常）</Radio.Button>
              <Radio.Button value="substandard">次标准体（有异常但可控）</Radio.Button>
              <Radio.Button value="history">有病史（住院/手术/重疾史）</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="health_issues" label={
            <span>具体异常项 <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>（搜索并选择，支持多选）</Text></span>
          }>
            <Select
              mode="multiple"
              showSearch
              placeholder="输入疾病/症状关键词搜索，如：高血压、结节、IBD..."
              filterOption={(input, option) => {
                if (!option) return false;
                const label = option.label as unknown as string;
                const groupName = option['data-group'] as string || '';
                return label.toLowerCase().includes(input.toLowerCase()) ||
                       groupName.toLowerCase().includes(input.toLowerCase());
              }}
              maxTagCount={6}
              optionLabelProp="label"
              style={{ width: '100%' }}
              options={HEALTH_OPTIONS.map((opt) => ({
                value: opt.value,
                label: opt.label,
                'data-group': opt.group,
                title: opt.tip || '',
                key: opt.value,
              }))}
              optionRender={(option) => {
                const opt = HEALTH_OPTIONS.find((o) => o.value === option.value);
                if (!opt) return <span>{option.label}</span>;
                return (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 0' }}>
                    <span style={{ flex: 1 }}>
                      <Tag color="default" style={{ fontSize: 10, marginRight: 6 }}>{opt.group}</Tag>
                      {opt.label}
                      <Tag color={LEVEL_COLORS[opt.level]} style={{ marginLeft: 6, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                        {LEVEL_LABELS[opt.level]}
                      </Tag>
                    </span>
                    {opt.tip && (
                      <Tooltip title={opt.tip}>
                        <QuestionCircleOutlined style={{ color: '#bbb', fontSize: 11, flexShrink: 0 }} />
                      </Tooltip>
                    )}
                  </div>
                );
              }}
            />
          </Form.Item>
          {unknownHealthItems.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="以下健康项暂未被系统识别"
              description={`${unknownHealthItems.join('、')}：该健康项本次仅作记录展示，不参与规则筛选，也不构成承保判断；如需核保结论，请以产品健康告知和保险公司核保为准。`}
            />
          )}
        </div>

        {/* Step 3: Preference confirm */}
        {step === 3 && (
          <div style={{ textAlign: 'center' }}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Text type="secondary">最后一步：选择推荐模式并确认偏好</Text>
              <EngineSwitch enabled={aiMode} onChange={setAiMode} />

              <Form.Item name="preferred_type" label={
                <span>偏好险种 <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>（可选，优先配置该险种，不改变硬性规则）</Text></span>
              } style={{ textAlign: 'left' }}>
                <Select
                  allowClear
                  placeholder="选择优先考虑的险种（可选）"
                  options={[
                    { label: '医疗险', value: '医疗险' },
                    { label: '意外险', value: '意外险' },
                    { label: '重疾险', value: '重疾险' },
                    { label: '定期寿险', value: '定期寿险' },
                    { label: '防癌险', value: '防癌险' },
                  ]}
                />
              </Form.Item>

              <Form.Item name="preferred_companies" label={
                <span>偏好保险公司 <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>（可选，选择后优先推荐该公司产品）</Text></span>
              } style={{ textAlign: 'left' }}>
                <Select
                  mode="multiple"
                  showSearch
                  placeholder="输入公司名称搜索，如：平安、泰康、众安..."
                  filterOption={(input, option) => {
                    if (!option) return false;
                    const label = option.label as unknown as string;
                    return label.includes(input);
                  }}
                  maxTagCount={4}
                  style={{ width: '100%' }}
                  options={COMPANY_OPTIONS.map((c) => ({
                    value: c.value,
                    label: c.label,
                    key: c.value,
                  }))}
                  optionRender={(option) => {
                    const comp = COMPANY_OPTIONS.find((c) => c.value === option.value);
                    if (!comp) return <span>{option.label}</span>;
                    return (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span>{comp.label}</span>
                        <Tag color={TIER_COLORS[comp.tier]} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                          {TIER_LABELS[comp.tier]}
                        </Tag>
                      </div>
                    );
                  }}
                />
              </Form.Item>

              <Card size="small" style={{ textAlign: 'left' }}>
                <Row gutter={16}>
                  <Col xs={24} sm={12}>
                    <Text strong>预算概况</Text>
                    <p style={{ margin: '4px 0' }}>年收入：<Text strong>¥{income.toLocaleString()}</Text></p>
                    <p style={{ margin: '4px 0' }}>保费预算：<Text strong style={{ color: '#1890ff' }}>¥{(income * budgetRatio).toLocaleString()}/年</Text>（占比 {(budgetRatio * 100).toFixed(0)}%）</p>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Text strong>保障范围</Text>
                    <p style={{ margin: '4px 0' }}>参考险种：医疗险 / 意外险 / 重疾险 / 定期寿险 / 防癌险</p>
                    <p style={{ margin: '4px 0' }}>（按年龄、职业与预算动态组合，以推荐结果为准）</p>
                    <p style={{ margin: '4px 0' }}>
                      推荐模式：
                      <Tag color={aiMode ? 'blue' : 'green'}>{aiMode ? 'AI 解释' : '极速规则'}</Tag>
                    </p>
                  </Col>
                </Row>
              </Card>
              {aiMode && (
                <Card size="small" style={{ background: '#e6f7ff', border: '1px solid #91d5ff' }}>
                  <Text style={{ fontSize: 13 }}>
                    AI 模式将调用大模型，解释规则引擎已选出的方案（AI 不参与选品与排序），响应时间约 10-30 秒
                  </Text>
                </Card>
              )}
            </Space>
          </div>
        )}

        <Divider style={{ margin: '20px 0 12px' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button htmlType="button" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>上一步</Button>
          {step < 3 ? (
            <Button
              htmlType="button"
              type="primary"
              onClick={handleNext}
            >下一步</Button>
          ) : (
            <Button type="primary" size="large" onClick={handleSubmit}>开始推荐</Button>
          )}
        </div>
      </Form>
    </Card>
  );
}
