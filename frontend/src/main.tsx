import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import antdZhCN from 'antd/locale/zh_CN';
import antdEnUS from 'antd/locale/en_US';
import App from './App';
import { I18nProvider, useI18n } from './i18n';

/** Ant Design 自带组件（分页、空态、日期等）的语言跟随界面语言。 */
function Shell() {
  const { locale } = useI18n();
  return (
    <ConfigProvider locale={locale === 'en-US' ? antdEnUS : antdZhCN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <Shell />
    </I18nProvider>
  </React.StrictMode>
);
