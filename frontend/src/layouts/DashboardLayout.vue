<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-title">腹膜透析模拟器</div>
        <div class="brand-sub">PD Simulator</div>
      </div>

      <nav class="nav">
        <RouterLink class="nav-item" to="/app/user" active-class="active">
          用户基本信息
        </RouterLink>
        <RouterLink class="nav-item" to="/app/patient" active-class="active">
          患者信息
        </RouterLink>
        <RouterLink class="nav-item" to="/app/regimen-sim" active-class="active">
          方案模拟
        </RouterLink>
        <RouterLink class="nav-item" to="/app/optimizer-sim" active-class="active">
          优化算法模拟
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <button class="btn-logout" @click="logout">退出登录</button>
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const logout = () => {
  localStorage.removeItem('pd_token')
  localStorage.removeItem('pd_username')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: radial-gradient(1200px 800px at 10% 0%, #e7ecff 0%, #f7f7fb 50%, #ffffff 100%);
  display: grid;
  grid-template-columns: 260px 1fr;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 18px 16px;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(10px);
  border-right: 1px solid rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.brand {
  padding: 14px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.18), rgba(118, 75, 162, 0.12));
  border: 1px solid rgba(102, 126, 234, 0.15);
}

.brand-title {
  font-weight: 800;
  color: #1f2340;
  letter-spacing: 0.2px;
}

.brand-sub {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(31, 35, 64, 0.65);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 6px;
}

.nav-item {
  text-decoration: none;
  color: rgba(31, 35, 64, 0.9);
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: 0.2s ease;
  font-weight: 650;
}

.nav-item:hover {
  background: rgba(102, 126, 234, 0.10);
  border-color: rgba(102, 126, 234, 0.15);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.22), rgba(118, 75, 162, 0.16));
  border-color: rgba(102, 126, 234, 0.22);
}

.sidebar-footer {
  margin-top: auto;
  padding: 8px 6px;
}

.btn-logout {
  width: 100%;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: white;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: 0.2s ease;
  font-weight: 650;
}

.btn-logout:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(31, 35, 64, 0.10);
}

.content {
  padding: 20px 22px;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    height: auto;
    position: relative;
  }
}
</style>

