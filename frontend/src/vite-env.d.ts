/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

type RuntimeBranding = {
  platform_name: string
  platform_logo_url: string
}

interface Window {
  __SAGITTA_BRANDING__?: RuntimeBranding
  __SAGITTA_BRANDING_PROMISE__?: Promise<RuntimeBranding>
}
