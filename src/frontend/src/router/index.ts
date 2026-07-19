import { createRouter, createWebHistory } from "vue-router"
import type { RouteRecordRaw } from "vue-router"
import { useAuthStore } from "../stores/auth"
import Layout from "../views/Layout.vue"

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "Login",
    component: () => import("../views/Login.vue"),
  },
  {
    path: "/",
    component: Layout,
    redirect: "/dashboard",
    children: [
      {
        path: "dashboard",
        name: "Dashboard",
        component: () => import("../views/Dashboard.vue"),
      },
      {
        path: "cameras",
        name: "Cameras",
        component: () => import("../views/cameras/Index.vue"),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from) => {
  const auth = useAuthStore()
  if (to.name !== "Login" && !auth.isAuthenticated) {
    return { name: "Login" }
  }
})

export default router
