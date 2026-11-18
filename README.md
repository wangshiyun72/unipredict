# 通用模型预测服务平台（UniPredict）

**项目**：基于服务器端通用模型的可访问式深度学习预测服务设计（重庆理工大学 2025 年本科生交叉创新培育项目 2025JCCX099）

这是一个以服务器为核心的预测服务。服务器端训练和部署一组通用模型与轻量模型，通过 REST API 和网页界面为外部终端提供预测服务。平台内置化工/环境数据模板、自动归一化、模型适配器和可解释性模块。用户只需要上传数据、选择目标列，就能一键完成预测；同时平台提供并发访问控制和结果可视化。

## 在线体验

- 网页地址：`http://<服务器公网IP>/`（用邮箱注册即可，无需验证码）
- 接口文档：`http://<服务器公网IP>/docs`

## 云服务器部署（Ubuntu，一条命令）

```bash
git clone https://github.com/wangshiyun72/unipredict.git /opt/unipredict && bash /opt/unipredict/deploy/install.sh
```

详见 `docs/云服务器部署.md`。

## 本机开发（Windows）

| 步骤 | 操作 |
|---|---|
| 1 | 安装 Node.js 22 LTS（见 `docs/部署说明.md` 第 1 步） |
| 2 | 在 Anaconda Prompt 中运行 `setup_backend.bat` |
| 3 | 运行 `setup_frontend.bat` |
| 4 | 运行 `start_backend.bat`，再运行 `start_frontend.bat`，浏览器打开 http://localhost:5173 |
| 5 | 用管理员账号 `admin` 登录（初始密码见 `docs/部署说明.md`）→「数据模板」→ 任选一个模板点「一键演示训练」 |

演示或正式使用时，运行 `build_and_deploy.bat`，网页和 API 统一在 http://本机IP:8000 提供。

## 文档

- `docs/部署说明.md`：本机安装、启动、局域网访问、配置项、压测、常见问题
- `docs/云服务器部署.md`：阿里云免费 ECS 部署步骤
- `docs/系统设计说明.md`：架构，以及项目简介各项要求对应的实现（可作为结题报告素材）
- `docs/模型接入指南.md`：如何接入新模型（写适配器插件，或导入 ONNX/joblib 模型）
- 接口文档：后端启动后访问 http://localhost:8000/docs

## 功能一览

- **模型**：TabPFN 通用表格基础模型、FT-Transformer、深度残差 MLP、梯度提升树、随机森林、线性模型、SVM、KNN、XGBoost、LightGBM，以及外部 ONNX/joblib 模型
- **数据模板**：新污染物水生毒性、废水处理出水水质、化合物溶解度、反应条件→收率
- **一键预测**：上传 → 自动识别字段 → 自动归一化 → 多模型训练与比较 → 自动发布最优模型 → 批量预测
- **API**：API Key 鉴权；支持 JSON 预测、文件批量预测、字段查询；提供 Python/curl/MATLAB/JS 调用示例
- **并发访问控制**：令牌桶限流、预测并发闸门、训练任务队列、GPU 并发锁、模型缓存
- **可解释性与可视化**：模型排行榜、预测值 vs 真实值、残差、混淆矩阵、置换重要性、单样本贡献、训练曲线、调用趋势、实时并发监控
- **团队协作**：多用户、团队共享、管理员管理
