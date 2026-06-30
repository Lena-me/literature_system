import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: () => import('@/views/auth/LoginView.vue') },
    { path: '/find-pwd-1', component: () => import('@/views/auth/FindPwd1View.vue') },
    { path: '/find-pwd-2', component: () => import('@/views/auth/FindPwd2View.vue') },

    // ===== 统一 NotebookLayout (三层架构：GlobalNav + SessionSidebar + Content) =====
    {
      path: '',
      component: () => import('@/layouts/NotebookLayout.vue'),
      children: [
        { path: '/dashboard', component: () => import('@/views/research/DashboardView.vue') },
        { path: '/profile', component: () => import('@/views/research/ProfileView.vue') },
        { path: '/notebook', component: () => import('@/views/research/NotebookView.vue') },
        { path: '/notebook/session/:id', component: () => import('@/views/research/NotebookView.vue') },
        { path: '/library', component: () => import('@/views/research/LibraryView.vue') },
        { path: '/reports', component: () => import('@/views/research/ReportsView.vue') },
        { path: '/legacy', component: () => import('@/views/research/WorkbenchView.vue') },
        { path: '/archive', component: () => import('@/views/research/LearningArchiveView.vue') },
        { path: '/graph', component: () => import('@/views/research/GraphView.vue') },
      ],
    },

    // ===== Admin =====
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      children: [
        { path: '', component: () => import('@/views/admin/AdminDashboard.vue') },
        { path: 'users', component: () => import('@/views/admin/UserAdminView.vue') },
        { path: 'models', component: () => import('@/views/admin/ModelAdminView.vue') },
        { path: 'tasks', component: () => import('@/views/admin/TaskAdminView.vue') },
        { path: 'ops', component: () => import('@/views/admin/OpsAdminView.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // 登录、注册页面和忘记密码页面无需登录
  const publicPaths = ['/login', '/find-pwd-1', '/find-pwd-2']
  if (!publicPaths.includes(to.path) && !auth.isAuthed) return '/login'
  if (auth.isAuthed && !auth.user) await auth.loadMe().catch(() => auth.logout())
  if (to.path.startsWith('/admin') && auth.user?.role !== 'admin') return '/dashboard'
  if (to.path === '/login' && auth.isAuthed) return auth.user?.role === 'admin' ? '/admin' : '/dashboard'
})
export default router
