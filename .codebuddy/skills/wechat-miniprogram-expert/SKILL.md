---
name: "wechat-miniprogram-expert"
description: "Expert guidance for WeChat Mini Program development in wujieShop. Invoke when working on pages, components, API calls, or configuration."
---

# 微信小程序开发专家 (WeChat Mini Program Expert)

本技能汇集了 wujieShop 项目的开发规范、技术栈特性及小程序最佳实践。

## 什么时候使用
- 创建或修改页面 (`Page`) 与组件 (`Component`)
- 编写业务逻辑与接口调用 (`api/`, `utils/`)
- 处理 `app.json` 配置与分包策略
- 解决 WXML/WXSS 布局与渲染问题
- 优化小程序性能 (`setData`)

## 核心开发规范 (Project Standards)

### 1. 接口调用
- **强制使用封装**：必须通过 `api/request.js` 发起请求，严禁直接使用 `wx.request`。
- **Service 层架构**：
  - 业务逻辑按模块分离到 `api/*Service.js`。
  - 页面仅负责 UI 交互与 Service 调用。
  - 示例：
    ```javascript
    const goodsService = require('../../api/goodsService.js')
    
    // In Page
    goodsService.getGoodsDetail(id).then(res => {
      this.setData({ goods: res.data })
    })
    ```

### 2. 目录结构与命名
- **页面文件**：`pages/module/pageName/index.{js,json,wxml,wxss}`
  - 必须包含 `index` 文件名（项目约定）。
- **组件文件**：`components/component-name/component-name.{js,json,wxml,wxss}`
  - 组件名使用 kebab-case。
- **路径引用**：使用相对路径，或者参考 `utils/` 下的路径工具。

### 3. 分包策略 (Subpackages)
项目采用分包加载，新增页面时需确认归属：
- `mallModule`: 商城核心（订单、商品、活动）
- `creationModule`: AI 创作相关
- `memberModule`: 会员中心
- `goods`: 商品详情等
- *注意：Tabbar 页面（首页、创作、我的）必须在主包中。*

## 最佳实践 (Best Practices)

### 性能优化
1. **setData 优化**：
   - 避免频繁调用：合并多次 `setData`。
   - 避免大数据量：单次设置数据不要超过 256KB。
   - **局部更新**：使用路径语法更新数组/对象中的某一项：
     ```javascript
     this.setData({
       'list[0].checked': true
     })
     ```
2. **WXS 使用**：
   - 复杂的格式化逻辑（如价格、时间）应在 `.wxs` 文件中处理，而不是在 JS 中 map 处理后再 setData。

### WXML & WXSS
- **自适应单位**：布局主要使用 `rpx`。
- **样式隔离**：组件默认开启样式隔离，全局样式请在 `app.wxss` 或 `common/` 中定义。
- **资源引用**：本地图片尽量小，大图使用网络路径。

### 常见陷阱
1. **自定义 Tabbar**：项目使用了 `custom-tab-bar`，页面跳转时注意 `getTabBar().setData(...)` 的状态同步。
2. **自定义导航栏**：`navigationStyle: "custom"`，需处理刘海屏适配（使用 `wx.getSystemInfoSync().statusBarHeight`）。
3. **事件传参**：
   - 不要依赖 id，使用 `data-*` 属性：
     ```html
     <view bindtap="onTap" data-id="{{item.id}}">...</view>
     ```
     ```javascript
     onTap(e) {
       const { id } = e.currentTarget.dataset;
     }
     ```

## 调试与工具
- **AppID**: 开发环境应动态获取 AppID，或确保开发者工具配置正确。
- **Console**: 保留关键日志，发布上线前清理 `console.log`。

---
*Skill Version: 1.0 | Created by Skill Creator*
