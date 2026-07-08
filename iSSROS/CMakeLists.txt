cmake_minimum_required(VERSION 3.10)
project(IROS)

set(CMAKE_CXX_STANDARD 14)
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -pthread")

add_executable(IROS main.cpp Cap/Capability.cpp Cap/Capability.h Cap/Parameter.cpp Cap/Parameter.h CapInterface/CapInterfaceManager.cpp CapInterface/CapInterfaceManager.h Utils/Utils.cpp Utils/Utils.h Cap/CapabilityNeed.cpp Cap/CapabilityNeed.h Cap/CapabilityCanUse.cpp Cap/CapabilityCanUse.h Cap/CapabilityAllocated.cpp Cap/CapabilityAllocated.h CapEngine.cpp CapEngine.h Utils/Single_T.cpp Utils/Single_T.h core/CapNeedManager.cpp core/CapNeedManager.h core/ContextRenewManager.cpp core/ContextRenewManager.h core/CapAdaptiveManager.cpp core/CapAdaptiveManager.h env/Environment.cpp env/Environment.h env/Weather.cpp env/Weather.h Utils/Global.cpp env/Position.cpp env/Position.h core/CapDispatchManager.cpp core/CapDispatchManager.h plugin/PluginMgr.cpp plugin/PluginMgr.h plugin/PluginMgrImpl.cpp plugin/PluginMgrImpl.h plugin/AssessAPI.h Resource/Resource.cpp Resource/Resource.h plugin/SelectAPI.h)

target_link_libraries(IROS dl)
TARGET_LINK_LIBRARIES(IROS dl)

# 设置编译模式为 Debug（关键）
set(CMAKE_BUILD_TYPE Debug)

# 强制添加调试符号（-g 生成基本调试信息，-ggdb 生成GDB专用符号）
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g -ggdb")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -g -ggdb")
