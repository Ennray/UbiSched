cmake_minimum_required(VERSION 3.10)
project(select)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -pthread -ldl")  

if(NOT PYTHON_INCLUDE_DIR)
    find_package(Python3 COMPONENTS Development REQUIRED)
    set(PYTHON_INCLUDE_DIR ${Python3_INCLUDE_DIRS})
    set(PYTHON_LIBRARY ${Python3_LIBRARIES})
endif()

include_directories(${PYTHON_INCLUDE_DIR})

add_library(select SHARED 
    selectPlugin.cpp 
    PluginImpl.cpp 
    MTCTS.cpp 
)

target_link_libraries(select 
    ${PYTHON_LIBRARY}
    ${ZLIB_LIBRARY}
    ${EXPAT_LIBRARY}
    dl          
)
