# build
rm -rf build
mkdir build
cd build
cmake ..
make -j8

# run
# 清理iS2ROS需要监听的端口，这两个端口用于接收远程服务器的airsim脚本发来的数据
kill -9 $(lsof -t -i:8889)
kill -9 $(lsof -t -i:8888)
./IROS