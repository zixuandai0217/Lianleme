/* 体重趋势解读接口封装：只在本特性内使用，不改动 api/index.ts 的既有导出。 */
import client from "./client"
import type { WeightInsights } from "@/lib/weight-insight"

export type { WeightInsights }

/** 读取锚点窗口、带日期极值与四周训练对照的体重趋势解读 */
export const getWeightInsights = (userId: number) =>
  client.get<unknown, WeightInsights>(`/api/weight/${userId}/insights`)
