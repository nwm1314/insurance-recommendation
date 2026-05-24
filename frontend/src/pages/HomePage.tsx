import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, InputNumber, Select, Radio, Checkbox, Slider, Button, Card, Space, Typography, Row, Col } from 'antd';
import ProgressSteps from '../components/ProgressSteps';
import EngineSwitch from '../components/EngineSwitch';
import type { UserProfile } from '../types';

const { Title } = Typography;

export default function HomePage() {
  const [step, setStep] = useState(0);
  const [aiMode, setAiMode] = useState(false);
  const [income, setIncome] = useState(200000);
  const [budgetRatio, setBudgetRatio] = useState(0.08);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const onFinish = (values: Record<string, unknown>) => {
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
      budget_ratio: budgetRatio,
      enable_llm_engine: aiMode,
    };
    navigate('/result', { state: { profile } });
  };

  return (
    <Card style={{ maxWidth: 720, margin: '40px auto' }}>
      <Title level={3} style={{ textAlign: 'center' }}>智能保险推荐</Title>
      <ProgressSteps current={step} />

      <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{
        gender: 'male', life_stage: 'single', family_burden: 'none',
        health_status: 'standard', job_class: 2,
      }}>
        {step === 0 && (
          <>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="age" label="年龄" rules={[{ required: true }]}>
                  <InputNumber min={0} max={120} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
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
              ]} />
            </Form.Item>
            <Form.Item name="family_burden" label="家庭负担">
              <Select options={[
                { label: '无负担', value: 'none' }, { label: '需赡养父母', value: 'parents' },
                { label: '需抚养子女', value: 'children' }, { label: '双重负担', value: 'dual' },
              ]} />
            </Form.Item>
          </>
        )}

        {step === 1 && (
          <>
            <Form.Item label="年收入（元）">
              <InputNumber value={income} onChange={(v) => setIncome(v || 0)}
                min={10000} max={10000000} step={10000} style={{ width: '100%' }}
                formatter={(v) => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
            </Form.Item>
            <Form.Item name="job_class" label="职业类别" rules={[{ required: true }]}>
              <Select options={[
                { label: '1类（低风险·室内办公）', value: 1 }, { label: '2类（较轻·外勤文职）', value: 2 },
                { label: '3类（一般·轻体力劳动）', value: 3 }, { label: '4类（中等·制造业）', value: 4 },
                { label: '5类（较高·建筑运输）', value: 5 }, { label: '6类（高风险·高空矿下）', value: 6 },
              ]} />
            </Form.Item>
            <Form.Item name="existing_coverage" label="已有保障">
              <Checkbox.Group options={[
                { label: '社保', value: 'social' }, { label: '已有商业保险', value: 'commercial' },
              ]} />
            </Form.Item>
            <Form.Item label={`预算占比：${(budgetRatio * 100).toFixed(0)}%（≈ ¥${(income * budgetRatio).toLocaleString()}/年）`}>
              <Slider min={3} max={10} step={0.5} value={budgetRatio * 100}
                onChange={(v) => setBudgetRatio((v as number) / 100)} />
            </Form.Item>
          </>
        )}

        {step === 2 && (
          <>
            <Form.Item name="health_status" label="健康状态" rules={[{ required: true }]}>
              <Radio.Group>
                <Radio.Button value="standard">标准体（无异常）</Radio.Button>
                <Radio.Button value="substandard">次标准体（结节/三高等）</Radio.Button>
                <Radio.Button value="history">有病史（住院/手术史）</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item name="health_issues" label="具体异常项（可多选）">
              <Checkbox.Group options={[
                { label: '甲状腺/乳腺/肺结节', value: 'nodule' },
                { label: '高血压', value: 'hypertension' },
                { label: '高血糖/糖尿病', value: 'diabetes' },
                { label: '住院史', value: 'hospitalization' },
                { label: '手术史', value: 'surgery' },
              ]} />
            </Form.Item>
          </>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center' }}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <EngineSwitch enabled={aiMode} onChange={setAiMode} />
              <Card size="small">
                <p>您的推荐预算约为 <strong>¥{(income * budgetRatio).toLocaleString()}/年</strong></p>
                <p>将为您匹配医疗险 + 意外险 + 重疾险 + 定期寿险方案</p>
              </Card>
              {aiMode && (
                <Card size="small" style={{ background: '#e6f7ff' }}>
                  AI 模式将为您全网比对产品，生成个性化推荐语
                </Card>
              )}
            </Space>
          </div>
        )}

        <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
          <Button htmlType="button" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>上一步</Button>
          {step < 3 ? (
            <Button htmlType="button" type="primary" onClick={() => setStep((s) => s + 1)}>下一步</Button>
          ) : (
            <Button type="primary" htmlType="submit">开始推荐</Button>
          )}
        </div>
      </Form>
    </Card>
  );
}
