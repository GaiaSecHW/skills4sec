/**
 * SecEvo Frontend Configuration
 *
 * API_BASE: 后端 API 基础路径
 *   - 开发环境: http://localhost:8000
 *   - 生产环境: 空字符串（使用相对路径）
 */
const AppConfig = {
  // 根据运行环境自动判断 API 基础路径
  // 生产环境部署时，前端和后端同源，使用相对路径即可
  API_BASE: window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : ''
};
