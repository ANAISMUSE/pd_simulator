import { createRouter, createWebHistory } from 'vue-router'

import Login from '../pages/Login.vue'
import Register from '../pages/Register.vue'
import DashboardLayout from '../layouts/DashboardLayout.vue'
import UserProfile from '../pages/UserProfile.vue'
import Patient from '../pages/Patient.vue'
import RegimenSim from '../pages/RegimenSim.vue'
import OptimizerSim from '../pages/OptimizerSim.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/app/regimen-sim' },
    { path: '/login', component: Login, meta: { public: true } },
    { path: '/register', component: Register, meta: { public: true } },
    {
      path: '/app',
      component: DashboardLayout,
      children: [
        { path: '', redirect: '/app/regimen-sim' },
        { path: 'user', component: UserProfile },
        { path: 'patient', component: Patient },
        { path: 'regimen-sim', component: RegimenSim },
        { path: 'optimizer-sim', component: OptimizerSim },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/app/regimen-sim' },
  ],
})

router.beforeEach((to) => {
  if (to.meta?.public) return true
  const token = localStorage.getItem('pd_token')
  if (!token && to.path.startsWith('/app')) return { path: '/login' }
  return true
})

export default router

