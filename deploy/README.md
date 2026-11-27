# 宁跃官网与考试平台：ECS 部署文件

部署目标为阿里云 ECS `101.200.134.123`，域名为 `ningyue.xyz`。本目录负责生成静态站点和提供独立虚拟主机配置示例；不会自动登录服务器、修改 DNS、申请证书或覆盖服务器已有站点。

## 构建

在仓库根目录执行：

```sh
python3 deploy/prepare_release.py
```

生成脚本只使用 Python 标准库，并调用本机 Node.js 检查 JavaScript 语法，无需安装 npm 依赖。默认考试源目录是 `local-backups/exam-practice/`；更新源后可重新构建，也可指定 `--exam-source /absolute/path/to/Exam-Practice`。

输出均在已忽略的 `deploy/dist/`：

- `site/`：可直接提供 HTTP 服务的站点目录。
- `ningyue-site.tar.gz`：仅包含网站运行文件的发布包，解压后直接得到 `index.html`、`exam/` 等文件。
- `SHA256SUMS`：发布包 SHA-256 校验值。
- `SITE-SHA256SUMS`：逐个站点文件的 SHA-256 校验值。
- `release.json`：构建时间、官网源码提交、文件数和检查结果。

脚本检查 HTML 与 CSS 中的本地资源、所有英语题图、内嵌 JSON 和 JavaScript 语法；名单仅接受当前已加盐的校验值格式。只复制明确列出的运行代码和图片，不复制 `.git`、原始名单、维护工具、扫描 PDF、导入报告或本地备份说明。原有 `home.html`、仓库根 `index.html` 和考试源文件不被修改。

## 访问路径

当前 `ningyue.xyz` 的公开站点由独立仓库 `ningyue-tech/ningyue-website` 的 `main` 分支通过 GitHub Pages 发布。该仓库已同步本构建的 `home.html`、同内容的 `index.html` 和 `exam/`，发布提交为 `aed9773506b06e5d3b86d559b58d3b6331b9d2e2`。本仓库 `home.html` 是官网源文件；更新它后，还需同步实际发布仓库。下面的 ECS 备案及未开放状态只描述阿里云服务器，不代表当前 GitHub Pages 域名站点。

| 路径 | 内容 |
| --- | --- |
| `/`、`/home.html` | 官网，默认直接使用仓库 `home.html` 的部署副本 |
| `/index.html` | 同一版官网的兼容副本 |
| `/exam/`、`/exam/index.html#subjects` | 三科考试平台与科目选择 |
| `/exam/login.html` | 原分科名单验证 |
| `/exam/auto-exam.html` | 汽车考试 |
| `/exam/marketing-exam.html` | 市场营销考试 |
| `/exam/english-exam.html` | 英语练习与模拟 |
| `/exam/guide.html` | 原考试须知 |
| `/privacy.html`、`/boxIndex.html` | 现有隐私说明页面 |
| `/app-icon.png` | 现有应用图标 |

构建副本中的官网考试链接使用 `exam/index.html#subjects`，因此访问官网和考试均停留在同一域名。六个考试页面顶部增加“返回宁跃官网”，原科目首页、考试须知及登录链接不改。官网八个栏目仍由原 `#/...` 路由处理，不需要 Nginx 重写为其他页面。

## 本地验收

```sh
python3 -m http.server 8767 --bind 127.0.0.1 --directory deploy/dist/site
```

打开 `http://127.0.0.1:8767/`，点击官网“进入在线考试”，确认进入 `/exam/index.html#subjects`；点击“返回宁跃官网”回到 `/`。各科仍使用原名单独立验证。线上考试验证依赖 Web Crypto，需要 HTTPS；本地可通过 localhost 或 127.0.0.1 检查。

迁移后来源域名及考试目录改变，旧 GitHub Pages 下的浏览器会话和成绩不会自动转移。原答题、计时、评分和保存逻辑保持不变，学生在新域名重新验证即可使用。

## 服务器预部署与本机验收

本次核查时尚无网站备案。先仅在服务器本机验收，不开放公网 IP 或域名的网站访问，不修改 DNS，不监听公网 80/443，也不自动添加备案号。正式上线须先完成网站备案和接入核验。

`nginx-ningyue-staging.conf` 是完整独立配置，只监听 `127.0.0.1:8080`，使用单独 PID 与日志文件。安装 Nginx 后，确认 `/srv/ningyue/current/` 已指向本次站点目录，再以实际绝对配置路径执行：

```sh
nginx -t -c /srv/ningyue/config/nginx-staging.conf
nginx -c /srv/ningyue/config/nginx-staging.conf
curl --fail --head http://127.0.0.1:8080/
curl --fail --head http://127.0.0.1:8080/exam/
```

确认实际监听仅为 `127.0.0.1:8080`。需要关闭这个预部署实例时使用相同配置路径：

```sh
nginx -c /srv/ningyue/config/nginx-staging.conf -s quit
```

不要运行不带 `-c` 的启动命令，也不要为本机预部署放行公网端口。`nginx-ningyue-http.conf` 仅为正式阶段的虚拟主机示例，此时不要激活。

## 备案完成后的正式发布

1. 先确认服务器现有监听端口、Nginx 配置、站点目录和业务用途，备份要改动的配置。不要覆盖已有默认站点。
2. 将发布包及校验清单上传到独立发布目录，例如 `/srv/ningyue/releases/<release-id>/`。在放置发布包的目录运行 `sha256sum -c SHA256SUMS`；解压后在站点根运行 `sha256sum -c SITE-SHA256SUMS`。
3. 使用独立站点根目录；示例 `nginx-ningyue-http.conf` 指向 `/srv/ningyue/current/`。`current` 可作为指向已验证发布目录的符号链接，便于回滚。
4. 网站备案完成后，将正式配置示例按实际环境调整后加入现有 Nginx。先运行 `nginx -t`，通过后 reload。首次检查可使用指定 Host 的本机请求，避免提前切换线上域名。
5. 核对实际网站备案号及接入状态，按已批准的信息设置页脚。确认域名解析、证书、80/443 入口和 HTTPS 实测结果后，再切换域名。域名现有邮箱相关解析必须保留。
6. HTTPS 配置应使用已实际签发的证书路径；此处 HTTP 示例只适用于初步检查及 ACME 验证，不能代替考试平台的 HTTPS。启用 HTTPS 后将普通 HTTP 请求重定向到 HTTPS，并保留 ACME 验证路径。

构建文件不代表公网上线；实际发布状态以服务器检查和域名访问结果为准。

## 本次预部署记录（服务器内部验收通过）

记录日期：2026-11-27。服务器为 `101.200.134.123`，已从 Alibaba Cloud Linux 官方软件仓库安装 Nginx 1.24.0，发布包已上传至 `/ningyue-site.tar.gz`。通过阿里云 Workbench 执行部署并完成以下服务器本机验收；尚未公网上线。

| 项目 | 本次安排 / 状态 |
| --- | --- |
| 官网源码提交 | `b9a84a1cc3aa65f9acf13f0dcd467e40cef147d4` |
| 考试源码提交 | `145093f03286b267f8b01d448661a40448ce4268` |
| 服务器发布目录 | `/srv/ningyue/releases/20261127-b9a84a1`，已解压 374 个文件 |
| 当前版本链接 | `/srv/ningyue/current`，已验证指向上述目录 |
| 实际 Nginx 配置 | `/srv/ningyue/config/nginx-staging.conf`，语法及启动检查通过 |
| 本机预部署入口 | `http://127.0.0.1:8080/` 与 `http://127.0.0.1:8080/exam/`，均返回 HTTP 200 |
| 计划官网地址 | `https://ningyue.xyz/`，尚未公网上线 |
| 计划考试地址 | `https://ningyue.xyz/exam/`，尚未公网上线 |
| 网站备案 | 尚未通过，完成网站备案和接入核验后才推进公网开放 |
| DNS 与公网端口 | 本次不修改 DNS，不开放公网 80/443 |

已上传发布包大小为 `28,999,850` bytes，SHA-256 为：

```text
b5c3912922873d46167e140a8e35e40bc6d9b670bb566fee11b6b2a33a1250cd
```

验收结果：服务器压缩包 SHA-256 与上值一致；374 个文件逐一通过本机 HTTP 读取，并与磁盘文件 SHA-256 比较一致。官网、考试首页、登录页及汽车、市场营销、英语页面均返回 HTTP 200；隐藏路径返回 403，不存在页面返回 404。`ss -lntp` 确认 Nginx 仅监听 `127.0.0.1:8080`，原 SSH 22 端口不变，未启用默认 Nginx 系统服务。服务器报告保存在 `/srv/ningyue/verification-20261127.json`。

该实例没有设置开机启动；服务器重启后需使用上面的独立配置重新启动。本次没有修改 DNS、安全组、证书或备案资料。以上结果只表明服务器内部静态资源可用，正式域名、HTTPS 和新域名下的完整登录答题流程仍须在备案完成后另行验收。

随后按用户指定，将默认首页显式设置为 `index home.html index.html;`。服务器配置已备份到 `/srv/ningyue/config/nginx-staging.before-home.conf`，语法检查通过后已重载。再次验收确认根路径响应与 `/home.html` 完全一致，`/exam/` 返回 HTTP 200。官网页面源文件始终是仓库根目录的 `home.html`。

追溯说明：当前 `release.json` 记录官网源码提交，考试来源版本已在上表补充。后续构建可在 manifest 增加 `exam_source_commit`，值为本次考试输入版本 `145093f03286b267f8b01d448661a40448ce4268`，并保留考试输入文件摘要及 `SITE-SHA256SUMS`。此次仅补文档，不重建已上传包，不改变归档内容或上述 SHA-256。
