# 2026-09-11 发布前依赖补丁

M2 发布前额外执行依赖扫描发现漏洞，因此暂缓提交交付。没有利用这些漏洞测试真实站点，没有读取用户文件或学生数据。

## 修复范围

| 依赖 | 原锁定版本 | 修复版本 | 依据 |
| --- | --- | --- | --- |
| Next.js / eslint-config-next | 16.3.0 / 16.2.12 | 16.3.3 | [Windows 托管风险](https://github.com/advisories/GHSA-p293-qw3h-jr36)、[图片优化风险](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4) |
| sharp（间接） | 0.35.3 | 0.35.4 | [libheif 漏洞修复](https://github.com/advisories/GHSA-rgj7-g3m4-5g8c) |
| js-yaml（间接） | 4.3.1 | 4.3.2 | [合并键资源消耗](https://github.com/advisories/GHSA-2883-xcg3-v3hh) |
| nanoid（间接） | 3.3.16 | 3.3.18 | [零长度自定义生成循环](https://github.com/advisories/GHSA-2v37-7h3g-55p8) |
| Vitest / mocker | 4.1.10 | 4.1.11 | [开发测试文件读取风险](https://github.com/advisories/GHSA-82fw-gwwq-j7x9) |
| pypdf | 6.14.2 | 6.16.1 | pip-audit 的修复版本提示与[官方安全发布](https://github.com/py-pdf/pypdf/releases/tag/6.16.1) |

明确提高直接依赖的最低/固定版本，并更新两个锁文件；pnpm overrides 保证间接依赖不会继续锁回本次已知漏洞版本。未升级大版本，未更换框架或数据库。

## 已执行与边界

- 首轮 pnpm 扫描：7 条报告（2 严重、3 高危、2 中危）；Python 扫描指向 pypdf，包含重复上游报告，不把它们当作8个不同漏洞。
- 修复后 `pnpm security:dependencies` 退出码 0：pnpm 与 pip-audit 均报告没有已知漏洞。
- 无已知依赖漏洞不等于应用无安全风险。业务权限、注册防滥用、备份和公网部署仍需按路线验收。
- 新锁文件的完整构建/测试和 Edge/PostgreSQL 复测在 M2 验收记录中记载。
- 原运行容器不会因更新锁文件自动升级；集成部署与健康检查完成前，不声称运行站点已经安装补丁。
