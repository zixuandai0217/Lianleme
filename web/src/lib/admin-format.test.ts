/* 管理端展示用的时间/数值格式化：纯函数，页面只负责摆放。 */
import { describe, expect, it } from "vitest"

import { formatAdminDate, formatAdminDateTime, formatAdminNumber } from "./admin-format"

describe("formatAdminDateTime", () => {
  it("缺失或空串显示占位符，不显示 undefined/Invalid Date", () => {
    expect(formatAdminDateTime(null)).toBe("—")
    expect(formatAdminDateTime(undefined)).toBe("—")
    expect(formatAdminDateTime("")).toBe("—")
  })

  it("解析失败时原样回显，方便定位脏数据而不是假装没有", () => {
    expect(formatAdminDateTime("not-a-date")).toBe("not-a-date")
  })

  it("合法时间输出本地时间文本（含日期与时间字段）", () => {
    const text = formatAdminDateTime("2026-06-01T09:30:00Z")
    expect(text).not.toBe("—")
    expect(text).toMatch(/2026/)
    expect(text).toMatch(/\d{1,2}:\d{2}/)
  })
})

describe("formatAdminDate", () => {
  it("缺失显示占位符，合法日期输出 2026 年的日期文本", () => {
    expect(formatAdminDate(null)).toBe("—")
    expect(formatAdminDate("2026-06-01")).toMatch(/2026/)
  })
})

describe("formatAdminNumber", () => {
  it("区分 0 与缺失，避免把 0 当成没有数据", () => {
    expect(formatAdminNumber(0)).toBe("0")
    expect(formatAdminNumber(null)).toBe("—")
    expect(formatAdminNumber(undefined)).toBe("—")
    expect(formatAdminNumber(1.25)).toBe("1.25")
  })
})
