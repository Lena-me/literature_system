/// <reference types="vite/client" />

// neovis.js 没有 exports 字段，无法解析子路径的类型 → 手动声明
declare module 'neovis.js/dist/neovis.js' {
  export * from 'neovis.js'
  export { default } from 'neovis.js'
}
