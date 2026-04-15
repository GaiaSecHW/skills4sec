/**
 * SecEvo Frontend Configuration
 *
 * API_BASE: 后端 API 基础路径
 *   - 开发环境: http://localhost:8000
 *   - 生产环境: 空字符串（使用相对路径）
 *
 * SKILLS_GITEA_URL: 技能 Gitea 组织地址
 *   - 每个技能一个独立仓库，拼接 /{skill-slug} 得到完整仓库 URL
 */
const AppConfig = {
  // 根据运行环境自动判断 API 基础路径
  // 生产环境部署时，前端和后端同源，使用相对路径即可
  API_BASE: window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '',

  // 技能 Gitea 组织地址（每个技能一个独立仓库，拼接 /{skill-slug} 得到完整仓库 URL）
  SKILLS_GITEA_URL: 'http://gitea.ai.icsl.huawei.com/icsl'
};
