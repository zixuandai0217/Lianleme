/* 管理端列表 URL 状态：查询串 ↔ 请求对象的双向映射，页面刷新/分享/后退都靠它还原。 */
import { describe, expect, it } from "vitest"

import {
  ADMIN_FLAG_OPTIONS,
  ADMIN_SORT_OPTIONS,
  adminExportAvailability,
  adminFlagLabel,
  adminSortLabel,
  buildAdminExportSearch,
  buildAdminUsersSearch,
  parseAdminUsersSearch,
} from "./admin-query"

describe("parseAdminUsersSearch", () => {
  it("空查询串回到默认请求：第 1 页、每页 20、注册时间倒序", () => {
    expect(parseAdminUsersSearch("")).toEqual({
      sort: "registered_desc",
      page: 1,
      page_size: 20,
    })
    expect(parseAdminUsersSearch("?")).toEqual({
      sort: "registered_desc",
      page: 1,
      page_size: 20,
    })
  })

  it("键名与接口参数一一对应，多选 flag 用重复参数", () => {
    const request = parseAdminUsersSearch(
      "?q=%E5%BC%A0&has_plan=true&is_admin=false&has_api_key=true" +
        "&registered_from=2026-06-01&registered_to=2026-06-30" +
        "&checkins_min=3&checkins_max=9&active_within_days=7" +
        "&flag=new_no_plan&flag=inactive_14d&sort=last_active_asc&page=2&page_size=50",
    )

    expect(request).toEqual({
      q: "张",
      has_plan: true,
      is_admin: false,
      has_api_key: true,
      registered_from: "2026-06-01",
      registered_to: "2026-06-30",
      checkins_min: 3,
      checkins_max: 9,
      active_within_days: 7,
      flag: ["new_no_plan", "inactive_14d"],
      sort: "last_active_asc",
      page: 2,
      page_size: 50,
    })
  })

  it("忽略空值、非法布尔/数字/枚举与重复 flag", () => {
    const request = parseAdminUsersSearch(
      "?q=%20%20&has_plan=1&checkins_min=-1&checkins_max=abc" +
        "&active_within_days=0&sort=random&page=0&page_size=500" +
        "&flag=bogus&flag=new_no_plan&flag=new_no_plan",
    )

    expect(request).toEqual({
      active_within_days: 0,
      flag: ["new_no_plan"],
      sort: "registered_desc",
      page: 1,
      page_size: 20,
    })
  })

  it("页码与每页条数的非法值退回默认，不把 422 带到页面上", () => {
    expect(parseAdminUsersSearch("?page=-3&page_size=0").page).toBe(1)
    expect(parseAdminUsersSearch("?page=-3&page_size=0").page_size).toBe(20)
    expect(parseAdminUsersSearch("?page=2.5&page_size=1000").page).toBe(1)
    expect(parseAdminUsersSearch("?page_size=100").page_size).toBe(100)
  })
})

describe("buildAdminUsersSearch", () => {
  it("默认值不写进 URL（第 1 页、每页 20、默认排序、空筛选）", () => {
    expect(
      buildAdminUsersSearch({ sort: "registered_desc", page: 1, page_size: 20 }),
    ).toBe("")
  })

  it("只写显式筛选并按固定键序输出，可被原样还原", () => {
    const search = buildAdminUsersSearch({
      q: "张三",
      has_plan: true,
      registered_from: "2026-06-01",
      checkins_min: 3,
      active_within_days: 7,
      flag: ["inactive_14d", "new_no_plan"],
      sort: "last_active_desc",
      page: 2,
      page_size: 50,
    })

    expect(search).toBe(
      "q=%E5%BC%A0%E4%B8%89&has_plan=true&registered_from=2026-06-01" +
        "&checkins_min=3&active_within_days=7&flag=new_no_plan&flag=inactive_14d" +
        "&sort=last_active_desc&page=2&page_size=50",
    )
    expect(parseAdminUsersSearch(search)).toEqual({
      q: "张三",
      has_plan: true,
      registered_from: "2026-06-01",
      checkins_min: 3,
      active_within_days: 7,
      flag: ["new_no_plan", "inactive_14d"],
      sort: "last_active_desc",
      page: 2,
      page_size: 50,
    })
  })

  it("flag 按固定枚举顺序排列，同一组筛选永远得到同一个 URL", () => {
    const a = buildAdminUsersSearch({
      flag: ["api_key_missing", "new_no_plan"],
      sort: "registered_desc",
      page: 1,
      page_size: 20,
    })
    const b = buildAdminUsersSearch({
      flag: ["new_no_plan", "api_key_missing"],
      sort: "registered_desc",
      page: 1,
      page_size: 20,
    })
    expect(a).toBe(b)
    expect(a).toBe("flag=new_no_plan&flag=api_key_missing")
  })

  it("导出不接受分页：导出 URL 永远不带 page / page_size", () => {
    expect(
      buildAdminExportSearch({
        q: "李四",
        has_plan: false,
        sort: "last_active_asc",
        page: 3,
        page_size: 100,
      }),
    ).toBe("q=%E6%9D%8E%E5%9B%9B&has_plan=false&sort=last_active_asc")
  })
})

describe("展示文案与导出可用性", () => {
  it("需关注标记有固定枚举顺序与中文文案", () => {
    expect(ADMIN_FLAG_OPTIONS.map((option) => option.value)).toEqual([
      "new_no_plan",
      "planned_no_checkin",
      "inactive_14d",
      "never_analyzed",
      "api_key_missing",
    ])
    expect(adminFlagLabel("new_no_plan")).toBe("注册 7 天无计划")
    expect(adminFlagLabel("planned_no_checkin")).toBe("有计划 7 天无打卡")
    expect(adminFlagLabel("inactive_14d")).toBe("14 天无活跃")
    expect(adminFlagLabel("never_analyzed")).toBe("注册 3 天未分析")
    expect(adminFlagLabel("api_key_missing")).toBe("未配置 API Key")
  })

  it("排序枚举都有可读文案", () => {
    expect(ADMIN_SORT_OPTIONS.map((option) => option.value)).toEqual([
      "registered_desc",
      "registered_asc",
      "last_active_desc",
      "last_active_asc",
    ])
    expect(adminSortLabel("registered_desc")).toBe("注册时间（新→旧）")
    expect(adminSortLabel("last_active_asc")).toBe("最近活跃（远→近）")
  })

  it("0 行时禁用导出并说明原因，有行时可用且没有原因", () => {
    expect(adminExportAvailability(0)).toEqual({
      enabled: false,
      reason: "当前筛选结果为空，暂无可导出的用户",
    })
    expect(adminExportAvailability(1)).toEqual({ enabled: true })
    expect(adminExportAvailability(5000)).toEqual({ enabled: true })
  })
})
