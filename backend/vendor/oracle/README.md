将 Oracle Instant Client 解压后的目录放到这里，例如：

`backend/vendor/oracle/instantclient_19_27/`

构建后端镜像时，Dockerfile 会自动将该目录复制到镜像中的 `/opt/oracle/`，
并在检测到 `instantclient_*` 目录时创建 `/opt/oracle/instantclient` 软链接并刷新动态库缓存。

生产环境连接 Oracle 11.2 时，建议同时设置：

`ORACLE_DRIVER_MODE=thick`

说明：

- Linux 容器中通常不需要设置 `ORACLE_CLIENT_LIB_DIR`，只要 Instant Client 已进入系统库搜索路径即可。
- 如果你不想把客户端目录放进仓库，也可以在自定义镜像或宿主机中安装 Instant Client，然后通过环境变量和系统库路径暴露给容器。
