# 前端开发规范

管理后台采用**单体HTML**架构，所有前端代码在 `admin/index.html` 一个文件中。

## 文件结构

```
static/
├── CLAUDE.md              # 本规范文件
└── admin/
    └── index.html         # 管理后台（HTML + CSS + JS 单文件）
```

---

## 开发规则

### 1. 语法检查（必须）

修改 `index.html` 后，**必须**运行语法检查：

```bash
# 检查 JavaScript 语法
node -e "const fs=require('fs'); const html=fs.readFileSync('backend/static/admin/index.html','utf8'); const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1]; if(script) { try { new Function(script); console.log('✓ JS 语法正确'); } catch(e) { console.error('✗ JS 语法错误:', e.message); process.exit(1); } }"

# 检查文件完整性
node -e "const fs=require('fs'); const html=fs.readFileSync('backend/static/admin/index.html','utf8'); console.log('文件大小:', html.length, 'bytes'); console.log('包含 showToast:', html.includes('showToast')); console.log('包含 toast-container:', html.includes('toast-container'));"
```

### 2. 提交前检查清单

- [ ] JavaScript 无语法错误
- [ ] HTML 标签正确闭合
- [ ] CSS 大括号匹配
- [ ] 函数调用时括号完整
- [ ] 字符串引号匹配

### 3. 代码风格

#### JavaScript

```javascript
// ✅ 正确：使用 const/let
const message = '操作成功';
let count = 0;

// ✅ 正确：async/await
async function saveUser() {
    const res = await api('/admin/users', { method: 'POST', body: JSON.stringify(data) });
    if (res && res.success) {
        showToast('保存成功', 'success');
    }
}

// ❌ 错误：遗留多余的括号
function foo() {
    return bar();
}  }  // ← 多余的括号会导致语法错误
```

#### Toast 通知（统一使用）

```javascript
// 成功提示
showToast('操作成功', 'success');

// 错误提示（显示后端错误）
showError(res, '操作失败');

// 警告提示
showToast('请输入必填项', 'warning');

// 信息提示
showToast('正在处理...', 'info');

// 确认对话框
showConfirm('确定删除吗？', async () => {
    // 确认后执行
});
```

### 4. 禁止事项

- ❌ 使用 `alert()` - 使用 `showToast()` 替代
- ❌ 使用 `confirm()` - 使用 `showConfirm()` 替代
- ❌ 内联事件处理中写复杂逻辑
- ❌ 直接操作 DOM 而不检查元素存在

### 5. 错误处理模板

```javascript
async function apiAction() {
    const res = await api('/endpoint', { method: 'POST' });
    if (res && res.success) {
        showToast('操作成功', 'success');
        // 刷新数据
        loadData();
    } else {
        showError(res, '操作失败');
    }
}
```

---

## 后端错误格式

后端返回统一格式：
```json
{
    "code": "ERROR_CODE",
    "message": "错误消息",
    "detail": { "field": "value" }
}
```

`showError()` 函数会自动解析并显示。

---

## 常见错误排查

| 错误 | 原因 | 解决 |
|------|------|------|
| `Unexpected token '}'` | 多余的括号 | 检查函数/代码块闭合 |
| `is not defined` | 变量未声明 | 添加 `const`/`let` |
| `Cannot read property` | 对象为 null | 添加空值检查 `obj?.prop` |
| Toast 不显示 | 容器未加载 | 检查 `toast-container` 元素 |

---

## 调试技巧

```javascript
// 在浏览器控制台测试
showToast('测试消息', 'success');
showConfirm('测试确认', () => console.log('确认'));

// 检查 API 响应
const res = await api('/admin/users');
console.log(res);
```
