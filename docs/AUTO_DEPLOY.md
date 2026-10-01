# GitHub Actions 自动部署到腾讯云 Lighthouse

合并 `.github/workflows/deploy-production.yml` 后，`main` 每次推送会触发 GitHub Actions。工作流通过 SSH 登录服务器，先运行 `lighthouse_ops.py backup`，再运行 `lighthouse_ops.py update`，最后核对提交和公网健康接口。也可以在 Actions 页面手动运行。

## 一次性设置

1. 在自己的电脑上创建**专用** Ed25519 SSH 密钥，不复用个人登录密钥。Windows PowerShell 示例：

   ```powershell
   ssh-keygen -t ed25519 -C "ft-research-actions" -f "$env:USERPROFILE\.ssh\ft-research-actions" -N ""
   Get-Content "$env:USERPROFILE\.ssh\ft-research-actions.pub"
   ```

2. 将输出的**公钥**加入腾讯云服务器 `ubuntu` 用户的 `/home/ubuntu/.ssh/authorized_keys`。如果当前腾讯云终端显示 `root@...`，可用 `sudo nano /home/ubuntu/.ssh/authorized_keys` 粘贴一整行公钥，再运行 `sudo chown -R ubuntu:ubuntu /home/ubuntu/.ssh && sudo chmod 700 /home/ubuntu/.ssh && sudo chmod 600 /home/ubuntu/.ssh/authorized_keys`。不要把私钥放在服务器仓库或聊天中。
3. 在服务器运行 `sudo cat /etc/ssh/ssh_host_ed25519_key.pub`，记下**主机公钥**。GitHub secret `DEPLOY_KNOWN_HOSTS` 的内容须为 `服务器公网IP ssh-ed25519 AAAA...`，其中后两段来自这条命令。这个 IP 必须与 `DEPLOY_HOST` 完全一致。
4. 在 GitHub 仓库 Settings → Secrets and variables → Actions 中创建以下 **repository secrets**：

   | 名称 | 内容 |
   | --- | --- |
   | `DEPLOY_HOST` | 服务器公网 IP，不带 `https://` |
   | `DEPLOY_USER` | `ubuntu` |
   | `DEPLOY_SSH_KEY` | 本机 `ft-research-actions` 私钥文件的 Base64 编码，生成方法见下方 |
   | `DEPLOY_KNOWN_HOSTS` | 第 3 步形成的完整一行 |

   在本机 Windows PowerShell 运行以下命令，将私钥文件直接编码到剪贴板；命令不会在终端显示密钥。随后粘贴到 `DEPLOY_SSH_KEY` 的 Secret 输入框。该编码仍属于敏感凭据，不要发到聊天或提交到仓库。

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\.ssh\ft-research-actions")) | Set-Clipboard
   ```

5. 从自己电脑用新密钥测试 SSH 登录 `ubuntu@服务器公网IP`，并在该连接里运行 `sudo -n docker ps`，确认无需交互密码。若测试失败，先修复密钥配置，不改 SSH 服务设置。
6. 密钥登录测试成功后，在腾讯云网页终端创建 `/etc/ssh/sshd_config.d/00-ft-research-hardening.conf`，内容为 `PasswordAuthentication no`、`KbdInteractiveAuthentication no`、`PermitRootLogin no`、`PubkeyAuthentication yes`，每项单独一行。运行 `sudo sshd -t` 确认配置有效，再运行 `sudo systemctl reload ssh`。重新开一个终端再次用密钥登录 `ubuntu`，确认成功；`sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin) '` 应显示 `passwordauthentication no`、`kbdinteractiveauthentication no`、`pubkeyauthentication yes`、`permitrootlogin no`。若结果不符，先不要开放防火墙。
7. 完成以上测试后，确认腾讯云轻量服务器防火墙允许 TCP 22 从 GitHub 托管运行器访问。运行器 IP 会变化；如使用 `0.0.0.0/0`，密钥登录和禁用密码登录的核对必须先完成。开放端口只允许连接尝试，不会绕过 SSH 身份验证。
8. 完成以上设置后合并自动部署 PR。合并本身会触发第一次部署；到 GitHub Actions → Deploy production 查看结果。

## 发布行为与排障

- `main` 推送自动触发；Actions 页面也可手动运行。并发部署排队执行，避免同时修改同一台服务器。
- 更新脚本要求服务器 `/opt/ft-research` 位于 `main` 且工作区干净，仅允许快进更新。检查失败时停止，不覆盖服务器文件。
- 备份只包含管理员数据库，不是整个 `/data` 的完整备份；重大更新仍应按 [Lighthouse 部署说明](../deploy/tencent-lighthouse/README.md)创建云硬盘快照。
- 构建或健康检查失败时，Actions 会标红；查看对应运行日志。工作流不会自动回滚，需要人工诊断。

