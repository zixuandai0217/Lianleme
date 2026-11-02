/* 管理端三条路由：数据概览 / 用户列表 / 用户详情。
 *
 * 路由表单独成文件，既让 App 的路由表只做挂载，也让「非管理员访问任意 /admin* 一律
 * 跳走」有一个可整棵挂载的测试入口。 */
import { Route } from "react-router-dom"

import AdminLayout from "@/components/admin-layout"
import { AdminGate } from "@/components/admin-gate"
import AdminOverviewPage from "./index"
import AdminUserDetailPage from "./user-detail"
import AdminUsersPage from "./users"

export const adminRouteTree = (
  <Route
    element={
      <AdminGate>
        <AdminLayout />
      </AdminGate>
    }
  >
    <Route path="/admin" element={<AdminOverviewPage />} />
    <Route path="/admin/users" element={<AdminUsersPage />} />
    <Route path="/admin/users/:id" element={<AdminUserDetailPage />} />
  </Route>
)
