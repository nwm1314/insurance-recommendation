import { Alert } from 'antd';

export default function Disclaimer() {
  return (
    <Alert
      type="info"
      showIcon
      message="免责声明"
      description="本方案由算法生成，仅供参考，最终承保以保险公司官方条款为准。投保前请仔细阅读产品条款和健康告知。"
      style={{ marginTop: 24 }}
    />
  );
}
