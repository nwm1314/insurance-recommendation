import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// react / react-dom / react-router 全家 / axios：应用入口必需的核心运行时，
// 单独成块以获得跨发布稳定缓存；其余 node_modules（antd 及其 rc-*/cssinjs 传递依赖）
// 不强制分组，交给 Rollup 按「入口图 vs 懒加载页面图」自然拆分——
// 量化实验（TASK-026）证明强制合并 antd 会把页面级 Table/Form 等拉回首屏，
// 抵消路由懒加载收益；自然拆分下入口 470 kB / antd 共享块按需加载，构建无告警。
const REACT_VENDOR_RE = /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom|axios)[\\/]|node_modules[\\/]@remix-run[\\/]/;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (REACT_VENDOR_RE.test(id)) return 'react-vendor';
          return undefined;
        },
      },
    },
  },
});
