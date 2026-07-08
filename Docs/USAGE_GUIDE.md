# iS2ROS 使用指南

## 1. 环境要求
- **本地 (x86)**: Linux (Ubuntu 20.04+ 推荐), Python 3.10+, PyTorch.
- **交叉编译 (ARM)**: 已安装 `aarch64-none-linux-gnu-` 工具链，且 `./mnt` 挂载了目标板 Rootfs。

## 2. 快速启动 (x86 本地测试)
```bash
# 1. 编译
make x86

# 2. 启动 5 个无人机实例
./run_5_iros.sh

# 3. 停止运行
./stop_5_iros.sh
```

## 3. 交叉编译与部署 (ARM)
```bash
# 1. 执行一键编译并打包
make deploy

# 2. 将压缩包拷贝至目标板
scp iS2ROS_deploy_arm.tar.gz root@<arm_ip>:/root/

# 3. 在目标板上运行
tar -xzvf iS2ROS_deploy_arm.tar.gz
cd iS2ROS_deploy_arm
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:.
./IROS 8888 1
```

## 4. 调试建议
- **日志查看**: 运行 `./run_5_iros.sh` 后，日志存放在 `./logs/iros_uavX.log`。
- **插件报错**: 若看到 `Failed to load .so`，请检查 `LD_LIBRARY_PATH` 是否包含插件路径。
- **IP 修改**: 若需更改通信目标，请参考 `IP_ADDRESS_LIST.md` 修改源码后重新 `make`。
