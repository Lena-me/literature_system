/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_APP_TITLE: string
  /** Neo4j bolt 连接地址（neovis.js 前端直连） */
  readonly VITE_NEO4J_URI: string
  /** Neo4j 用户名 */
  readonly VITE_NEO4J_USER: string
  /** Neo4j 密码 */
  readonly VITE_NEO4J_PASSWORD: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** neovis.js CDN 全局类型 */
declare global {
  interface Window {
    NeoVis: any
  }
}
