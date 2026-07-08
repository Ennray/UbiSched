# iS2ROS ARM (AArch64) 稳定版工具链 - 插件链接优化版

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# 基础路径
set(TOOLCHAIN_PATH /opt/arm-gnu-toolchain-11.3.rel1-x86_64-aarch64-none-linux-gnu/bin)
set(CMAKE_C_COMPILER ${TOOLCHAIN_PATH}/aarch64-none-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER ${TOOLCHAIN_PATH}/aarch64-none-linux-gnu-g++)

# SYSROOT 指向挂载好的 mnt
set(CMAKE_SYSROOT ${CMAKE_CURRENT_LIST_DIR}/mnt)

# 强制标记有效
set(CMAKE_C_COMPILER_WORKS 1)
set(CMAKE_CXX_COMPILER_WORKS 1)

# 策略设置
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# 关键：定义库和启动文件搜索路径
set(ARM_LIB_DIR "${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu")
set(ARM_LIB_DIR_ALT "${CMAKE_SYSROOT}/lib/aarch64-linux-gnu")

# --- 编译标志优化 ---
# 使用 -isystem 解决 features.h/bits/wordsize.h 问题
# 使用 -B 告知编译器 crti.o 等启动文件的位置 (解决插件链接失败的关键)
set(COMMON_FLAGS "-pthread -g -ggdb --sysroot=${CMAKE_SYSROOT} -isystem ${CMAKE_SYSROOT}/usr/include/aarch64-linux-gnu -B${ARM_LIB_DIR} -B${ARM_LIB_DIR_ALT}")
set(CMAKE_CXX_FLAGS "${COMMON_FLAGS}" CACHE STRING "" FORCE)
set(CMAKE_C_FLAGS "${COMMON_FLAGS}" CACHE STRING "" FORCE)

# --- 链接标志优化 ---
# 显式告知链接器库路径
set(COMMON_LINK_FLAGS "--sysroot=${CMAKE_SYSROOT} -L${ARM_LIB_DIR} -L${ARM_LIB_DIR_ALT}")
set(CMAKE_EXE_LINKER_FLAGS "${COMMON_LINK_FLAGS}" CACHE STRING "" FORCE)
set(CMAKE_SHARED_LINKER_FLAGS "${COMMON_LINK_FLAGS}" CACHE STRING "" FORCE)
set(CMAKE_MODULE_LINKER_FLAGS "${COMMON_LINK_FLAGS}" CACHE STRING "" FORCE)

# 项目所需变量
set(PYTHON_INCLUDE_DIR ${CMAKE_SYSROOT}/usr/include/python3.12)
set(PYTHON_LIBRARY ${ARM_LIB_DIR}/libpython3.12.so.1.0)
set(ZLIB_LIBRARY ${ARM_LIB_DIR}/libz.so)
set(EXPAT_LIBRARY ${ARM_LIB_DIR}/libexpat.so)
