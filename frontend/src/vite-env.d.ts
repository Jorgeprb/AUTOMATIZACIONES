/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_ADMIN_API_KEY: string;
  readonly VITE_ENABLE_DEV_FALLBACKS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
