import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const appMode = import.meta.env.VITE_APP_MODE || 'user'

const userRoutes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: () => import('@/views/auth/LoginView.vue') },
  { path: '/find-pwd-1', component: () => import('@/views/auth/FindPwd1View.vue') },
  { path: '/find-pwd-2', component: () => import('@/views/auth/FindPwd2View.vue') },
  {
    path: '',
    component: () => import('@/layouts/NotebookLayout.vue'),
    children: [
      { path: '/dashboard', component: () => import('@/views/research/DashboardView.vue') },
      { path: '/profile', component: () => import('@/views/research/ProfileView.vue') },
      { path: '/notebook', component: () => import('@/views/research/NotebookView.vue') },
      { path: '/notebook/session/:id', component: () => import('@/views/research/NotebookView.vue') },
      { path: '/library', component: () => import('@/views/research/LibraryView.vue') },
      { path: '/compare', component: () => import('@/views/research/CompareView.vue') },
      { path: '/reports', component: () => import('@/views/research/ReportsView.vue') },
      { path: '/archive', component: () => import('@/views/research/LearningArchiveView.vue') },
      { path: '/graph', component: () => import('@/views/research/GraphView.vue') },
    ],
  },
]

const adminRoutes = [
  { path: '/', redirect: '/admin/login' },
  { path: '/admin/login', component: () => import('@/views/admin/AdminLoginView.vue') },
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
]

const router = createRouter({
  history: createWebHistory(),
  routes: appMode === 'admin' ? adminRoutes : userRoutes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const publicPaths = appMode === 'admin' 
    ? ['/admin/login'] 
    : ['/login', '/find-pwd-1', '/find-pwd-2']

  if (!publicPaths.includes(to.path) && !auth.isAuthed) {
    return appMode === 'admin' ? '/admin/login' : '/login'
  }
  if (auth.isAuthed && !auth.user) {
    try {
      await auth.loadMe()
    } catch {
      auth.logout()
      return appMode === 'admin' ? '/admin/login' : '/login'
    }
  }
  if (appMode === 'admin' && auth.isAuthed && auth.user?.role !== 'admin') {
    auth.logout()
    return '/admin/login'
  }
  if (to.path.startsWith('/admin') && !publicPaths.includes(to.path) && auth.user?.role !== 'admin') {
    return appMode === 'admin' ? '/admin/login' : '/dashboard'
  }
  if ((to.path === '/login' || to.path === '/admin/login') && auth.isAuthed) {
    return auth.user?.role === 'admin' ? '/admin' : '/dashboard'
  }
})

export default router
