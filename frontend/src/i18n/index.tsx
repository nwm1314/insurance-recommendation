import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY, type Locale, type MessageKey, messages } from './messages';

interface TranslateVars {
  [name: string]: string | number;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: MessageKey, vars?: TranslateVars) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value === 'zh-CN' || value === 'en-US';
}

/**
 * 语言优先级：URL 参数 > 本地存储 > 浏览器语言 > 中文。
 *
 * `?lang=en` 让英文用户可以直接拿到可分享的英文入口，而不必先找到切换器。
 * 浏览器语言只在明确是英文时生效，其余一律回落到中文（产品目录是中文的）。
 */
function initialLocale(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE;
  const fromQuery = new URLSearchParams(window.location.search).get('lang');
  if (fromQuery === 'en' || fromQuery === 'en-US') return 'en-US';
  if (fromQuery === 'zh' || fromQuery === 'zh-CN') return 'zh-CN';

  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // localStorage 在隐私模式下可能抛错，忽略即可
  }

  const browser = (navigator.language || '').toLowerCase();
  return browser.startsWith('en') ? 'en-US' : DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // 存不了就只在本次会话生效，不影响渲染
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: MessageKey, vars?: TranslateVars) => {
      const table = messages[locale] as Record<string, string>;
      const fallback = messages[DEFAULT_LOCALE] as Record<string, string>;
      let text = table[key] ?? fallback[key] ?? key;
      if (vars) {
        for (const [name, value] of Object.entries(vars)) {
          text = text.split(`{${name}}`).join(String(value));
        }
      }
      return text;
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      toggleLocale: () => setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN'),
      t,
    }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used inside <I18nProvider>');
  }
  return ctx;
}
