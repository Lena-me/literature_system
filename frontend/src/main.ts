import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import './styles/theme.css'
import './styles/animation.css'
import App from './App.vue'
import router from './router'
import { startHeartbeat } from './utils/heartbeat'

const app = createApp(App)
Object.entries(ElementPlusIconsVue).forEach(([key, component]) => app.component(key, component))
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

if (localStorage.getItem('access_token')) {
  startHeartbeat()
}

app.mount('#app')
