cmake_minimum_required(VERSION 3.10)
project(IROS)

# ===================== 交叉编译核心配置 =====================
# 如果没有通过 -DCMAKE_TOOLCHAIN_FILE 指定，则在此设置基本项
if(NOT CMAKE_TOOLCHAIN_FILE)
    set(CMAKE_SYSTEM_NAME Linux)
    set(CMAKE_SYSTEM_PROCESSOR aarch64)
    set(TOOLCHAIN_PREFIX aarch64-none-linux-gnu-)
    set(TOOLCHAIN_PATH /opt/arm-gnu-toolchain-11.3.rel1-x86_64-aarch64-none-linux-gnu/bin)
    set(CMAKE_C_COMPILER ${TOOLCHAIN_PATH}/${TOOLCHAIN_PREFIX}gcc)
    set(CMAKE_CXX_COMPILER ${TOOLCHAIN_PATH}/${TOOLCHAIN_PREFIX}g++)
    set(PROJECT_ROOT_DIR ${CMAKE_SOURCE_DIR}/../../..)
    set(CMAKE_SYSROOT ${PROJECT_ROOT_DIR}/mnt)
endif()

# ===================== 原有配置适配 =====================
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 确保链接路径包含 sysroot 中的库
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -pthread -g -ggdb --sysroot=${CMAKE_SYSROOT} -B${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu -B${CMAKE_SYSROOT}/lib/aarch64-linux-gnu")
SET(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} --sysroot=${CMAKE_SYSROOT} -L${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu -L${CMAKE_SYSROOT}/lib/aarch64-linux-gnu")

include_directories(
    ${CMAKE_SYSROOT}/usr/include/python3.12
    ${CMAKE_SYSROOT}/usr/include/aarch64-linux-gnu
    ${CMAKE_SYSROOT}/usr/include
)

# 添加可执行文件
add_executable(IROS 
    ../../main.cpp 
    ../../Cap/Capability.cpp 
    ../../Cap/Parameter.cpp 
    ../../CapInterface/CapInterfaceManager.cpp 
    ../../Utils/Utils.cpp 
    ../../Cap/CapabilityNeed.cpp 
    ../../Cap/CapabilityCanUse.cpp 
    ../../Cap/CapabilityAllocated.cpp 
    ../../CapEngine.cpp 
    ../../Utils/Single_T.cpp 
    ../../core/CapNeedManager.cpp 
    ../../core/ContextRenewManager.cpp 
    ../../core/CapAdaptiveManager.cpp 
    ../../env/Environment.cpp 
    ../../env/Weather.cpp 
    ../../Utils/Global.cpp 
    ../../env/Position.cpp 
    ../../core/CapDispatchManager.cpp 
    ../../plugin/PluginMgr.cpp 
    ../../plugin/PluginMgrImpl.cpp 
    ../../Resource/Resource.cpp
)

# 链接到 mnt 中真实的 ARM Python 库及其依赖
target_link_libraries(IROS 
    ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/libpython3.12.so.1.0 
    ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/libz.so
    ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/libexpat.so
    dl
    m
    pthread
)

set(CMAKE_BUILD_TYPE Debug)
