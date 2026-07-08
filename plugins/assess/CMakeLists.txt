cmake_minimum_required(VERSION 3.10)
project(DemoPlugin)

set(CMAKE_CXX_STANDARD 14)

if(NOT PYTHON_INCLUDE_DIR)
    find_package(Python3 COMPONENTS Development REQUIRED)
    set(PYTHON_INCLUDE_DIR ${Python3_INCLUDE_DIRS})
    set(PYTHON_LIBRARY ${Python3_LIBRARIES})
endif()

include_directories(${PYTHON_INCLUDE_DIR})

add_library(AssessPlugin SHARED AssessPlugin.cpp PluginImpl.cpp PluginImpl.h AssessAPI.h Cap/Capability.h env/Environment.h Cap/Parameter.h env/Weather.h env/Position.h)
target_link_libraries(AssessPlugin ${PYTHON_LIBRARY} ${ZLIB_LIBRARY} ${EXPAT_LIBRARY} dl)
